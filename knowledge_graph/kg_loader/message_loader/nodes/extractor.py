import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple, Optional
from langchain_core.messages import SystemMessage, HumanMessage

from knowledge_graph.kg_loader.message_loader.llm_factory import get_chat_llm
from knowledge_graph.kg_loader.message_loader.prompts_loader import get_prompt_template
from knowledge_graph.kg_loader.message_loader.state import MessageLoaderState

logger = logging.getLogger(__name__)

# Heuristic injection patterns for fallback if LLM is unavailable
INJECTION_PATTERN = re.compile(
    r"(?:NOTE TO ANY AI ASSISTANT|ignore earlier instructions|ignore previous instructions|disregard earlier instructions).*?(?:-- end --|\Z)",
    re.IGNORECASE | re.DOTALL
)

def _extract_json_from_llm(content: str) -> Any:
    """Extracts JSON from an LLM response string, handling markdown fences."""
    cleaned = content.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if match:
        cleaned = match.group(1).strip()
    return json.loads(cleaned)

def _detect_prompt_injection(llm: Any, text: str) -> Dict[str, Any]:
    """
    Uses an LLM to detect adversarial prompt injections, jailbreaks, or instructions
    attempting to override earlier instructions or falsify operational records.
    Falls back to regex heuristic if LLM invocation fails.
    """
    try:
        prompt_cfg = get_prompt_template("prompt_injection_detection")
        system_prompt = prompt_cfg["system"]
        user_prompt = prompt_cfg["user"].format(message_text=text)

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        resp = llm.invoke(messages)
        data = _extract_json_from_llm(resp.content)
        is_malicious = bool(data.get("is_malicious", False))
        injection_text = data.get("injection_text")
        if is_malicious and not injection_text:
            # If LLM flagged as malicious but omitted excerpt, extract via heuristic match
            match = INJECTION_PATTERN.search(text)
            if match:
                injection_text = match.group(0).strip()
        return {
            "is_malicious": is_malicious,
            "injection_text": injection_text,
            "reason": data.get("reason", "")
        }
    except Exception as e:
        logger.warning("LLM prompt injection detection failed, falling back to heuristic: %s", e)
        match = INJECTION_PATTERN.search(text)
        if match:
            return {
                "is_malicious": True,
                "injection_text": match.group(0).strip(),
                "reason": "Regex fallback detected adversarial keywords"
            }
        return {
            "is_malicious": False,
            "injection_text": None,
            "reason": "Clean (heuristic fallback)"
        }

def _parse_rfc_headers(text: str) -> Tuple[Dict[str, str], str]:
    """Separates RFC headers (From, To, Date, Subject) from the message body."""
    lines = text.splitlines()
    headers: Dict[str, str] = {}
    body_lines = []
    in_headers = True

    for line in lines:
        if in_headers:
            if line.strip() == "":
                in_headers = False
                continue
            if ":" in line and any(line.startswith(h) for h in ["From:", "To:", "Date:", "Subject:"]):
                k, v = line.split(":", 1)
                headers[k.strip()] = v.strip()
            else:
                in_headers = False
                body_lines.append(line)
        else:
            body_lines.append(line)

    return headers, "\n".join(body_lines).strip()

def _parse_header_date_to_utc(date_str: Optional[str]) -> str:
    """Parses message Date header (e.g. '2026-10-25 16:20 UTC') to standard ISO 8601 UTC."""
    if not date_str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    cleaned = re.sub(r"\s+UTC$", "Z", date_str.strip(), flags=re.IGNORECASE)
    formats = [
        "%Y-%m-%d %H:%M:%SZ",
        "%Y-%m-%d %H:%MZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%MZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue

    try:
        dt = datetime.fromisoformat(cleaned.rstrip("Z"))
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return cleaned

def extractor_node(state: MessageLoaderState) -> Dict[str, Any]:
    """
    Extractor Node:
    1. Reads raw message text from file_path.
    2. Parses RFC headers (From, To, Date, Subject).
    3. Normalizes sent_at_utc to ISO 8601.
    4. Detects adversarial prompt injections and isolates injection excerpts.
    """
    file_path = state.get("file_path")
    if not file_path or not os.path.exists(file_path):
        raise FileNotFoundError(f"Message file not found at: {file_path}")

    path_obj = Path(file_path)
    filename = path_obj.name
    message_id = path_obj.stem

    with open(file_path, "r", encoding="utf-8") as f:
        raw_message = f.read()

    headers, raw_body = _parse_rfc_headers(raw_message)
    sent_at_utc = _parse_header_date_to_utc(headers.get("Date"))

    # Security scan for prompt injection using LLM (with regex fallback)
    try:
        llm = get_chat_llm(temperature=0.0)
    except Exception as e:
        logger.warning("Could not initialize LLM for prompt injection check, using heuristic: %s", e)
        llm = None

    injection_res = _detect_prompt_injection(llm, raw_message) if llm else {
        "is_malicious": bool(INJECTION_PATTERN.search(raw_message)),
        "injection_text": (INJECTION_PATTERN.search(raw_message).group(0).strip() if INJECTION_PATTERN.search(raw_message) else None)
    }

    is_malicious = injection_res.get("is_malicious", False)
    injection_excerpt = injection_res.get("injection_text")
    if is_malicious:
        logger.warning("Adversarial prompt injection detected in message '%s': %s", message_id, injection_excerpt)

    return {
        "filename": filename,
        "message_id": message_id,
        "headers": headers,
        "raw_body": raw_body,
        "raw_message": raw_message,
        "sent_at_utc": sent_at_utc,
        "is_malicious": is_malicious,
        "injection_excerpt": injection_excerpt,
        "errors": state.get("errors", [])
    }
