import json
import logging
import re
from typing import Any, Dict, List, Optional
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from knowledge_graph.kg_loader.message_loader.llm_factory import get_chat_llm
from knowledge_graph.kg_loader.message_loader.prompts_loader import get_prompt_template
from knowledge_graph.kg_loader.message_loader.state import MessageLoaderState, ReplacementSpan, DateSpan

logger = logging.getLogger(__name__)

# Pre-compiled canonical reference metadata for prompt context injection
KNOWN_MARITIME_CONTEXT = """
VESSELS:
- MV Ocean Star (IMO 9876543, Class: Meridian 8500)
- MV Ocean Pearl (IMO 9876555, Class: Meridian 8500)
- MV Ocean Starlight (IMO 9654321, Class: Atlas 6000)
- MV Blue Horizon (IMO 9781234, Class: Meridian 8500)
- MV Silver Tern (IMO 9812345, Class: Coastal 1700)
- MV Vesta Dune (IMO 9845678, Class: Atlas 6000)
- MV Kestrel Bay (IMO 9823456, Class: Kestrel 4000)
- MV Amber Coast (IMO 9856789, Class: Atlas 6000)
- MV Celtic Dawn (IMO 9834567, Class: Meridian 8500)
- MV Golden Wake (IMO 9741234, Class: Coastal 1700)
- MV Jade Current (IMO 9742417, Class: Coastal 1700)
- MV Quiet Cove (IMO 9743143, Class: Coastal 1700)
- MV Delta Swan (IMO 9688162, Class: Atlas 6000)
- MV Orca Point (IMO 9751234, Class: Coastal 1700)
- MV Breeze Haven (IMO 9761234, Class: Coastal 1700)
- MV Willow Strait (IMO 9771234, Class: Coastal 1700)

PORTS & TIMEZONES:
- Port of Rotterdam (UN/LOCODE: NLRTM, Country: Netherlands, Timezone: Europe/Amsterdam)
- Port of Singapore (UN/LOCODE: SGSIN, Country: Singapore, Timezone: Asia/Singapore)
- Port of Antwerp (UN/LOCODE: BEANR, Country: Belgium, Timezone: Europe/Brussels)
- Port of Felixstowe (UN/LOCODE: GBFXT, Country: United Kingdom, Timezone: Europe/London)
- Port of Hamburg (UN/LOCODE: DEHAM, Country: Germany, Timezone: Europe/Berlin)
- Port of Santos (UN/LOCODE: BRSSZ, Country: Brazil, Timezone: America/Sao_Paulo)
- Port of Jebel Ali (UN/LOCODE: AEJEA, Country: United Arab Emirates, Timezone: Asia/Dubai)
- Port Said (UN/LOCODE: EGPSE, Country: Egypt, Timezone: Africa/Cairo)
- Port of Shanghai (UN/LOCODE: CNSGH, Country: China, Timezone: Asia/Shanghai)
- Port of Busan (UN/LOCODE: KRPUS, Country: South Korea, Timezone: Asia/Seoul)
- Port of Colombo (UN/LOCODE: LKCMB, Country: Sri Lanka, Timezone: Asia/Colombo)
- Port Klang (UN/LOCODE: MYPKG, Country: Malaysia, Timezone: Asia/Kuala_Lumpur)

ORGANIZATIONS / PORT AGENTS:
- Van Dijk Shipping Agency (org_id: van-dijk-shipping-agency, Port: NLRTM)
- Lion City Agencies (org_id: lion-city-agencies, Port: SGSIN)
- Scheldt Maritime Agency (org_id: scheldt-maritime-agency, Port: BEANR)
- Harwich Port Services (org_id: harwich-port-services, Port: GBFXT)
- Elbe Port Agency (org_id: elbe-port-agency, Port: DEHAM)
- Gulf Marine Agency (org_id: gulf-marine-agency, Port: AEJEA)
- Porto Agência Santos (org_id: porto-agencia-santos, Port: BRSSZ)

TECHNICAL MANAGERS:
- Harbourline Ship Management (manager_id: harbourline-ship-management)
- Nordwave Marine (manager_id: nordwave-marine)
- Eastpoint Technical Services (manager_id: eastpoint-technical-services)
- Bluefin Fleet Services (manager_id: bluefin-fleet-services)
"""

PORT_TIMEZONES_CONTEXT = """
- NLRTM (Rotterdam): Europe/Amsterdam (UTC+1 winter / UTC+2 summer)
- SGSIN (Singapore): Asia/Singapore (UTC+8)
- BEANR (Antwerp): Europe/Brussels (UTC+1 winter / UTC+2 summer)
- GBFXT (Felixstowe): Europe/London (UTC+0 winter / UTC+1 summer)
- DEHAM (Hamburg): Europe/Berlin (UTC+1 winter / UTC+2 summer)
- BRSSZ (Santos): America/Sao_Paulo (UTC-3)
- AEJEA (Jebel Ali): Asia/Dubai (UTC+4)
- EGPSE (Port Said): Africa/Cairo (UTC+2)
- CNSGH (Shanghai): Asia/Shanghai (UTC+8)
"""

def _extract_json_from_llm(content: str) -> Any:
    """Extracts JSON from an LLM response string, handling markdown fences."""
    cleaned = content.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if match:
        cleaned = match.group(1).strip()
    return json.loads(cleaned)

def _get_llm(model: Optional[str] = None) -> Any:
    """Instantiates the configured Chat model via factory."""
    return get_chat_llm(model=model, temperature=0.0)

def _resolve_sender(llm: Any, headers: Dict[str, str], body_snippet: str) -> Dict[str, Any]:
    """Resolves sender into message_type, kind, trust_tier, and edge target."""
    prompt_cfg = get_prompt_template("sender_resolution")
    system_prompt = prompt_cfg["system"]
    user_prompt = prompt_cfg["user"].format(
        from_header=headers.get("From", "Unknown"),
        to_header=headers.get("To", "Unknown"),
        date_header=headers.get("Date", "Unknown"),
        subject_header=headers.get("Subject", "Unknown"),
        body_snippet=body_snippet[:400]
    )

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    try:
        resp = llm.invoke(messages)
        data = _extract_json_from_llm(resp.content)
        return {
            "message_type": data.get("message_type", "Agent email"),
            "message_kind": data.get("message_kind", "agent_email"),
            "trust_tier": data.get("trust_tier", "T2"),
            "sender_edge_type": data.get("sender_edge_type", "SENT_BY_ORG"),
            "sender_target_label": data.get("sender_target_label", "Organization"),
            "sender_target_key": data.get("sender_target_key", "org_id"),
            "sender_target_value": data.get("sender_target_value", "unknown")
        }
    except Exception as e:
        logger.warning("LLM sender resolution fallback triggered: %s", e)
        # Heuristic fallback
        from_hdr = headers.get("From", "").lower()
        if "master" in from_hdr:
            return {
                "message_type": "Master's report",
                "message_kind": "noon_report",
                "trust_tier": "T1",
                "sender_edge_type": "SENT_BY_VESSEL",
                "sender_target_label": "Vessel",
                "sender_target_key": "name",
                "sender_target_value": headers.get("From")
            }
        elif "technical" in from_hdr:
            return {
                "message_type": "Technical manager",
                "message_kind": "technical_bulletin",
                "trust_tier": "T2",
                "sender_edge_type": "ISSUED_BY_MANAGER",
                "sender_target_label": "TechnicalManager",
                "sender_target_key": "manager_id",
                "sender_target_value": "harbourline-ship-management"
            }
        elif "officer" in from_hdr or "chief engineer" in from_hdr or "crew" in from_hdr:
            return {
                "message_type": "Crew message",
                "message_kind": "crew_message",
                "trust_tier": "T3",
                "sender_edge_type": "SENT_BY_VESSEL",
                "sender_target_label": "Vessel",
                "sender_target_key": "name",
                "sender_target_value": "Vessel"
            }
        return {
            "message_type": "Port agent",
            "message_kind": "agent_email",
            "trust_tier": "T2",
            "sender_edge_type": "SENT_BY_ORG",
            "sender_target_label": "Organization",
            "sender_target_key": "org_id",
            "sender_target_value": "unknown"
        }

def _resolve_entities(llm: Any, text: str) -> List[ReplacementSpan]:
    """Extracts entity spans to replace with canonical backtick-wrapped names."""
    prompt_cfg = get_prompt_template("entity_normalization")
    system_prompt = prompt_cfg["system"].format(reference_context=KNOWN_MARITIME_CONTEXT)
    user_prompt = prompt_cfg["user"].format(text=text)

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    try:
        resp = llm.invoke(messages)
        data = _extract_json_from_llm(resp.content)
        reps = data.get("replacements") or []
        results: List[ReplacementSpan] = []
        for r in reps:
            raw = r.get("raw_text")
            std = r.get("standardized_name")
            if raw and std and raw in text:
                results.append({"raw_text": raw, "standardized_text": f"`{std}`"})
        return results
    except Exception as e:
        logger.warning("LLM entity resolution failed: %s", e)
        return []

def _resolve_dates(llm: Any, text: str, sent_at_utc: str) -> List[DateSpan]:
    """Extracts date/time expressions to replace with standardized UTC timestamps."""
    prompt_cfg = get_prompt_template("date_resolution")
    system_prompt = prompt_cfg["system"].format(
        sent_at_utc=sent_at_utc,
        port_timezones=PORT_TIMEZONES_CONTEXT
    )
    user_prompt = prompt_cfg["user"].format(text=text)

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    try:
        resp = llm.invoke(messages)
        data = _extract_json_from_llm(resp.content)
        dates = data.get("dates") or []
        results: List[DateSpan] = []
        for d in dates:
            raw = d.get("raw_text")
            iso = d.get("inferred_iso_utc")
            dtype = d.get("date_type", "timestamp")
            if raw and iso and raw in text:
                results.append({
                    "raw_text": raw,
                    "inferred_iso_utc": f"`{iso}`",
                    "date_type": dtype
                })
        return results
    except Exception as e:
        logger.warning("LLM date resolution failed: %s", e)
        return []

def _safe_replace_outside_backticks(text: str, raw: str, replacement: str) -> str:
    """Replaces raw substring with replacement only in regions outside of backtick pairs."""
    prefix = r"\b" if re.match(r"^\w", raw) else ""
    suffix = r"\b" if re.search(r"\w$", raw) else ""
    pattern = re.compile(rf"{prefix}{re.escape(raw)}{suffix}")

    parts = re.split(r"(`[^`]*`)", text)
    for i in range(0, len(parts), 2):  # even indices are outside backticks
        parts[i] = pattern.sub(replacement, parts[i])
    return "".join(parts)

def _apply_replacements(text: str, replacements: List[Dict[str, str]], target_key: str) -> str:
    """Safely applies string replacements in order of decreasing substring length outside backticks."""
    # Sort replacements by raw_text length descending to avoid partial clobbering
    sorted_reps = sorted(replacements, key=lambda x: len(x["raw_text"]), reverse=True)
    result = text
    for item in sorted_reps:
        raw = item["raw_text"]
        new_val = item[target_key]
        result = _safe_replace_outside_backticks(result, raw, new_val)
    return result

def _remove_injection_text(body: str, injection_text: Optional[str]) -> str:
    """
    Completely removes adversarial prompt injection text and surrounding delimiters/banners.
    Ensures that the cleaned message is completely devoid of the adversarial injection.
    """
    cleaned = body
    if injection_text:
        # 1. Exact match removal
        if injection_text in cleaned:
            cleaned = cleaned.replace(injection_text, "")
        else:
            # 2. Flexible whitespace regex removal to handle formatting variations
            words = [re.escape(w) for w in injection_text.split() if w]
            if words:
                flex_pattern = re.compile(r"\s+".join(words), re.IGNORECASE)
                cleaned = flex_pattern.sub("", cleaned)

    # 3. Strip any adversarial banner wrappers (e.g. forwarded note markers)
    cleaned = re.sub(
        r"--\s*forwarded note pasted from our system\s*--",
        "",
        cleaned,
        flags=re.IGNORECASE
    )
    cleaned = re.sub(r"--\s*end\s*--", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"--\s*begin\s*--", "", cleaned, flags=re.IGNORECASE)

    # 4. Secondary sweep for any remaining prompt injection directives
    cleaned = re.sub(
        r"(?:NOTE TO ANY AI ASSISTANT|ignore earlier instructions|ignore previous instructions|disregard earlier instructions).*?(?:-- end --|\n\n|\Z)",
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL
    )

    # 5. Normalize whitespace and multiple blank lines
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()

def entity_resolver_node(state: MessageLoaderState) -> Dict[str, Any]:
    """
    Entity Resolver Node:
    1. Resolves sender into standardized message_type, kind, trust_tier, and sender edge target.
    2. Identifies maritime entity mentions and replaces them programmatically with `CanonicalName`.
    3. Identifies date expressions, converts local/relative times to UTC, and replaces with `UTC_TIMESTAMP`.
    4. Produces the final standardized cleaned_body with injection text completely removed.
    """
    headers = state.get("headers", {})
    raw_body = state.get("raw_body", "")
    sent_at_utc = state.get("sent_at_utc", "")

    # Completely remove quarantined prompt injection from cleaned body if flagged
    body_to_clean = raw_body
    if state.get("is_malicious"):
        body_to_clean = _remove_injection_text(body_to_clean, state.get("injection_excerpt"))


    llm = _get_llm()

    # Sub-step 2A: Sender & Role Resolution
    sender_info = _resolve_sender(llm, headers, body_to_clean)

    # Sub-step 2B: Maritime Entity Normalization
    entity_reps = _resolve_entities(llm, body_to_clean)
    body_with_entities = _apply_replacements(body_to_clean, entity_reps, "standardized_text")

    # Sub-step 2C: Temporal & Date Resolution
    date_reps = _resolve_dates(llm, body_with_entities, sent_at_utc)
    cleaned_body = _apply_replacements(body_with_entities, date_reps, "inferred_iso_utc")

    return {
        **sender_info,
        "entity_replacements": entity_reps,
        "date_replacements": date_reps,
        "cleaned_body": cleaned_body,
    }
