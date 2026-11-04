"""
Run trace capture for the evaluation engine.

Records, for a single graph invocation:
  - which nodes ran, in order, with their state updates (LangGraph stream_mode="updates")
  - the final graph state (stream_mode="values")
  - every tool call made by the researcher (callback handler), with args, output and any error

Nothing here depends on LangSmith. The researcher runs its ReAct agent inside one node, so its
tool calls never appear as graph nodes; they are captured through callbacks, which LangChain
propagates to nested runnables through contextvars.
"""

import json
import time
from typing import Any, Dict, List, Optional
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from pydantic import BaseModel, Field

# State keys too large or irrelevant to keep in the stored trace.
_DROPPED_UPDATE_KEYS = {"db_ground_truth", "clean_messages", "messages", "entity_resolver_messages"}
_MAX_TEXT = 4000


def to_jsonable(obj: Any, depth: int = 0) -> Any:
    """Converts pydantic models, messages, sets and unknown objects into JSON-safe values."""
    if depth > 8:
        return str(obj)[:_MAX_TEXT]
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    if isinstance(obj, str):
        return obj if len(obj) <= _MAX_TEXT else obj[:_MAX_TEXT] + "...[truncated]"
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(v, depth + 1) for v in obj]
    if hasattr(obj, "model_dump"):
        try:
            return to_jsonable(obj.model_dump(), depth + 1)
        except Exception:
            pass
    if hasattr(obj, "content") and hasattr(obj, "type"):
        return {"type": getattr(obj, "type", None), "content": to_jsonable(obj.content, depth + 1)}
    return str(obj)[:_MAX_TEXT]


def detect_tool_error(output: Any) -> Optional[str]:
    """
    Returns an error description if a tool result represents a failure, else None.

    Covers MCP/LangChain error flags (ToolMessage status="error", isError) and the error payloads
    the maritime MCP tools return as normal results ({"status": "ERROR"}, {"success": false, "error": ...}).
    NO_DATA results are not errors: they are a valid "nothing found" answer.
    """
    if output is None:
        return None

    if getattr(output, "status", None) == "error":
        return str(getattr(output, "content", "tool reported status=error"))[:500]
    if getattr(output, "isError", False) or getattr(output, "is_error", False):
        return str(getattr(output, "content", "tool reported isError"))[:500]

    content = getattr(output, "content", output)

    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text", "")))
            else:
                parts.append(str(getattr(block, "text", block)))
        content = "\n".join(p for p in parts if p)

    if isinstance(content, str):
        text = content.strip()
        if text[:1] in "{[":
            try:
                content = json.loads(text)
            except ValueError:
                content = text
        else:
            low = text.lower()
            if low.startswith(("error", "toolexception", "exception")) or "traceback (most recent call last)" in low:
                return text[:500]
            return None

    if isinstance(content, dict):
        status = str(content.get("status", "")).upper()
        if status in {"ERROR", "FAILED", "FAILURE"}:
            return str(content.get("error") or content.get("message") or status)[:500]
        if content.get("success") is False:
            return str(content.get("error") or "success=false")[:500]
        if content.get("isError"):
            return str(content.get("error") or content.get("message") or "isError")[:500]
        if content.get("error") and status not in {"NO_DATA", "NO_DATA_FOUND"}:
            return str(content["error"])[:500]
    return None


class ToolCallRecord(BaseModel):
    """One tool invocation made during the run."""
    name: str
    args: Any = None
    output: Any = None
    error: Optional[str] = Field(default=None, description="Error text if the call raised or returned an error payload")
    duration_sec: float = 0.0


class RunTrace(BaseModel):
    """Everything the node-level evaluators need from one graph run."""
    node_order: List[str] = Field(default_factory=list)
    node_updates: Dict[str, Any] = Field(default_factory=dict)
    node_latency_sec: Dict[str, float] = Field(default_factory=dict)
    tool_calls: List[ToolCallRecord] = Field(default_factory=list)
    guardrail_verdict: Optional[str] = Field(
        default=None,
        description="Verdict from the guardrail LLM call, observed through callbacks (not stored in graph state)"
    )
    resolver_clarification: Optional[str] = Field(
        default=None,
        description=(
            "Clarification question the resolver asked, read from its LLM output via callbacks. "
            "The graph does not keep it in state (the node returns `clarification_response`, AgentState has no such key)."
        )
    )
    final_state: Dict[str, Any] = Field(default_factory=dict)
    total_latency_sec: float = 0.0

    def update_for(self, node: str) -> Dict[str, Any]:
        """Returns the state update a node produced, or {} if it did not run."""
        value = self.node_updates.get(node)
        return value if isinstance(value, dict) else {}


def _clarification_question(outputs: Any) -> Optional[str]:
    """Returns the clarification question from an EntityResolutionResponse-shaped output, if it is ambiguous."""
    ambiguous = outputs.get("is_ambiguous") if isinstance(outputs, dict) else getattr(outputs, "is_ambiguous", None)
    if ambiguous is not True:
        return None
    needed = outputs.get("clarification_needed") if isinstance(outputs, dict) else getattr(outputs, "clarification_needed", None)
    question = needed.get("question") if isinstance(needed, dict) else getattr(needed, "question", None)
    return question if isinstance(question, str) and question.strip() else None


class TraceRecorder(BaseCallbackHandler):
    """Collects tool calls and the guardrail verdict from LangChain callbacks."""

    run_inline = True

    def __init__(self) -> None:
        self.tool_calls: List[ToolCallRecord] = []
        self.guardrail_verdict: Optional[str] = None
        self.resolver_clarification: Optional[str] = None
        self._open: Dict[UUID, Dict[str, Any]] = {}

    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, *, run_id: UUID, inputs: Optional[Dict[str, Any]] = None, **kwargs: Any) -> None:
        name = (serialized or {}).get("name") or kwargs.get("name") or "unknown_tool"
        self._open[run_id] = {"name": name, "args": inputs if inputs is not None else input_str, "t0": time.time()}

    def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        started = self._open.pop(run_id, None)
        if started is None:
            return
        self.tool_calls.append(ToolCallRecord(
            name=started["name"],
            args=to_jsonable(started["args"]),
            output=to_jsonable(output),
            error=detect_tool_error(output),
            duration_sec=round(time.time() - started["t0"], 3),
        ))

    def on_tool_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        started = self._open.pop(run_id, None)
        if started is None:
            return
        self.tool_calls.append(ToolCallRecord(
            name=started["name"],
            args=to_jsonable(started["args"]),
            output=None,
            error=f"{type(error).__name__}: {error}"[:500],
            duration_sec=round(time.time() - started["t0"], 3),
        ))

    def on_chain_end(self, outputs: Any, **kwargs: Any) -> None:
        # Neither the guardrail verdict nor the resolver's question is kept in graph state;
        # read them off the structured LLM outputs.
        question = _clarification_question(outputs)
        if question is not None:
            self.resolver_clarification = question
        if self.guardrail_verdict is not None:
            return
        verdict = getattr(outputs, "verdict", None)
        if verdict is None and isinstance(outputs, dict) and "is_allowed" in outputs:
            verdict = outputs.get("verdict")
        if isinstance(verdict, str) and verdict in {"APPROVED", "OUT_OF_SCOPE", "PROMPT_INJECTION", "TOXIC_CONTENT"}:
            self.guardrail_verdict = verdict


async def capture_trace(graph: Any, inputs: Dict[str, Any], config: Dict[str, Any]) -> RunTrace:
    """
    Runs the graph once and returns its RunTrace.

    `config` must carry the thread_id; recorder callbacks are added to it. Use a fresh thread_id per
    run, because the checkpointer persists state (including a pending clarification) across runs.
    """
    recorder = TraceRecorder()
    run_config = dict(config)
    run_config["callbacks"] = list(run_config.get("callbacks") or []) + [recorder]

    trace = RunTrace()
    start = time.time()
    last_tick = start
    last_values: Dict[str, Any] = {}

    async for mode, chunk in graph.astream(inputs, run_config, stream_mode=["updates", "values"]):
        if mode == "updates":
            now = time.time()
            for node, update in (chunk or {}).items():
                if node.startswith("__"):
                    continue
                trace.node_order.append(node)
                trace.node_latency_sec[node] = round(trace.node_latency_sec.get(node, 0.0) + (now - last_tick), 3)
                if isinstance(update, dict):
                    kept = {k: v for k, v in update.items() if k not in _DROPPED_UPDATE_KEYS}
                elif hasattr(update, "model_dump"):
                    kept = {k: v for k, v in update.model_dump().items() if k not in _DROPPED_UPDATE_KEYS}
                else:
                    kept = {"value": update}
                trace.node_updates[node] = to_jsonable(kept)
            last_tick = now
        elif mode == "values" and isinstance(chunk, dict):
            last_values = chunk

    trace.total_latency_sec = round(time.time() - start, 3)
    trace.tool_calls = recorder.tool_calls
    trace.guardrail_verdict = recorder.guardrail_verdict
    trace.resolver_clarification = recorder.resolver_clarification
    trace.final_state = to_jsonable({k: v for k, v in last_values.items() if k not in _DROPPED_UPDATE_KEYS})
    return trace
