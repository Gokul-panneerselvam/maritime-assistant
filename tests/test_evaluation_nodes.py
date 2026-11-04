"""
Tests for the node-level evaluators and run-trace capture:
guardrail, entity resolution, planner, tool-execution correctness, and callback propagation.
"""

import asyncio
import uuid
from typing import Any, Dict, List, Optional, TypedDict

import pytest
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph

from ai_agent.src.evaluation.dataset import get_benchmark_question_by_id
from ai_agent.src.evaluation.evaluators.composite_evaluator import CompositeEvaluator
from ai_agent.src.evaluation.evaluators.node_evaluators import (
    ClarificationVerdict,
    GuardrailEvaluator,
    PlannerEvaluator,
    ResolverEvaluator,
    ToolExecutionEvaluator,
)
from ai_agent.src.evaluation.harness import EvaluationHarness
from ai_agent.src.evaluation.trace import (
    RunTrace,
    ToolCallRecord,
    TraceRecorder,
    capture_trace,
    detect_tool_error,
)
from ai_agent.src.schemas.input_guardrail_dto import InputGuardrailResponse


def Q(qid: str):
    return get_benchmark_question_by_id(qid)


def call(name: str, error: Optional[str] = None) -> ToolCallRecord:
    return ToolCallRecord(name=name, args={}, output={}, error=error)


# ------------------------------------------------------------------ tool error detection

@pytest.mark.parametrize("output", [
    {"status": "ERROR", "error": "boom"},
    {"success": False, "error": "DuplicateNodeError"},
    {"error": "Cypher syntax error"},
    '{"status": "ERROR", "error": "db down"}',
    "Error: connection refused",
    "Traceback (most recent call last): ...",
])
def test_detect_tool_error_flags_errors(output):
    assert detect_tool_error(output) is not None


@pytest.mark.parametrize("output", [
    {"status": "NO_DATA", "message": "nothing found"},
    {"status": "NO_DATA_FOUND", "error": None},
    {"voyage_id": "VG-1042", "delay": 55},
    '{"voyage_id": "VG-1042"}',
    "Voyage VG-1042 is delayed",
    None,
])
def test_detect_tool_error_ignores_valid_results(output):
    assert detect_tool_error(output) is None


def test_detect_tool_error_toolmessage_status():
    from langchain_core.messages import ToolMessage
    bad = ToolMessage(content="failed", tool_call_id="1", status="error")
    ok = ToolMessage(content='{"a": 1}', tool_call_id="2")
    assert detect_tool_error(bad)
    assert detect_tool_error(ok) is None


# ------------------------------------------------------------------ tool execution evaluator

def test_tool_execution_all_ok():
    trace = RunTrace(tool_calls=[call("get_voyage_context"), call("search_messages")])
    m = ToolExecutionEvaluator.evaluate(Q("Q1"), trace)
    assert m.score == 1.0 and m.passed


def test_tool_execution_error_fails():
    trace = RunTrace(tool_calls=[call("get_voyage_context"), call("search_messages", error="timeout")])
    m = ToolExecutionEvaluator.evaluate(Q("Q1"), trace)
    assert m.score == 0.5 and not m.passed
    assert m.details["failed_calls"][0]["tool"] == "search_messages"


def test_tool_execution_no_calls_fails_for_approved_query():
    m = ToolExecutionEvaluator.evaluate(Q("Q1"), RunTrace())
    assert m.score == 0.0 and not m.passed


def test_tool_execution_not_applicable_to_guardrail_cases():
    assert ToolExecutionEvaluator.evaluate(Q("Q11"), RunTrace()) is None


# ------------------------------------------------------------------ guardrail evaluator

def blocked_trace(verdict: Optional[str], extra_nodes: Optional[List[str]] = None, tools: int = 0) -> RunTrace:
    return RunTrace(
        node_order=["node_1_guardrail"] + (extra_nodes or []),
        node_updates={"node_1_guardrail": {"validation_status": "BLOCKED_GUARDRAIL"}},
        guardrail_verdict=verdict,
        tool_calls=[call("get_voyage_context") for _ in range(tools)],
    )


def test_guardrail_out_of_scope_correct():
    m = GuardrailEvaluator.evaluate(Q("Q11"), blocked_trace("OUT_OF_SCOPE"), "OUT_OF_SCOPE_REFUSAL")
    assert m.score == 1.0 and m.passed


def test_guardrail_wrong_verdict_fails():
    m = GuardrailEvaluator.evaluate(Q("Q12"), blocked_trace("OUT_OF_SCOPE"), "OUT_OF_SCOPE_REFUSAL")
    assert not m.passed and m.details["checks"]["verdict_correct"] is False


def test_guardrail_downstream_activity_after_block_fails():
    m = GuardrailEvaluator.evaluate(
        Q("Q11"), blocked_trace("OUT_OF_SCOPE", extra_nodes=["node_2_resolver"], tools=1), "OUT_OF_SCOPE_REFUSAL"
    )
    assert not m.passed
    assert m.details["checks"]["no_downstream_nodes"] is False
    assert m.details["checks"]["no_tool_calls"] is False


def test_guardrail_approved_query_blocked_by_mistake():
    m = GuardrailEvaluator.evaluate(Q("Q1"), blocked_trace("OUT_OF_SCOPE"), "OUT_OF_SCOPE_REFUSAL")
    assert not m.passed and m.details["checks"]["decision_correct"] is False


def test_guardrail_approved_query_passes():
    trace = RunTrace(
        node_order=["node_1_guardrail", "node_2_resolver"],
        node_updates={"node_1_guardrail": {"validation_status": "APPROVED"}},
        guardrail_verdict="APPROVED",
    )
    m = GuardrailEvaluator.evaluate(Q("Q1"), trace, "SUCCESS")
    assert m.passed


def test_guardrail_works_when_verdict_not_observed():
    m = GuardrailEvaluator.evaluate(Q("Q11"), blocked_trace(None), "OUT_OF_SCOPE_REFUSAL")
    assert m.passed and m.details["verdict_observed"] is False


# ------------------------------------------------------------------ resolver evaluator

def entities(vessels=(), ports=(), voyages=(), dates=()) -> Dict[str, Any]:
    return {
        "vessels": [{"vessel_id": v, "name": v} for v in vessels],
        "ports": [{"port_code": p, "name": p} for p in ports],
        "voyages": list(voyages),
        "dates_utc": list(dates),
    }


def test_resolver_exact_match():
    m = ResolverEvaluator.evaluate(Q("Q1"), entities(vessels=["V001"]))
    assert m.score == 1.0 and m.passed


def test_resolver_wrong_vessel():
    m = ResolverEvaluator.evaluate(Q("Q1"), entities(vessels=["V004"]))
    assert m.score == 0.0 and not m.passed


def test_resolver_extra_vessel_lowers_precision():
    m = ResolverEvaluator.evaluate(Q("Q1"), entities(vessels=["V001", "V004"]))
    assert 0.0 < m.score < 1.0


def test_resolver_cross_fleet_allows_extra_vessels():
    # Q2/Q7 ask about "same class or manager": the resolver expands the fleet group, which must not be penalized.
    expanded = entities(vessels=["V001", "V004", "V005", "V012"])
    assert ResolverEvaluator.evaluate(Q("Q2"), expanded).score == 1.0
    assert ResolverEvaluator.evaluate(Q("Q1"), expanded).score < 1.0  # strict elsewhere
    assert ResolverEvaluator.evaluate(Q("Q2"), entities(vessels=["V004"])).score == 0.0  # anchor still required


def test_resolver_relative_date_last_month():
    good = entities(vessels=["V002"], ports=["DEHAM"], dates=["2026-09-01T00:00:00Z", "2026-09-30T23:59:59Z"])
    bad = entities(vessels=["V002"], ports=["DEHAM"], dates=["2026-10-01T00:00:00Z"])
    assert ResolverEvaluator.evaluate(Q("Q3"), good).passed
    m = ResolverEvaluator.evaluate(Q("Q3"), bad)
    assert not m.passed and m.details["dates"]["matched"] == {"last month": False}


def test_resolver_next_week_without_vessels():
    m = ResolverEvaluator.evaluate(
        Q("Q5"), entities(ports=["NLRTM"], dates=["2026-11-02T00:00:00Z", "2026-11-08T23:59:59Z"])
    )
    assert m.score == 1.0


def test_resolver_port_local_day_within_tolerance():
    # 25 Oct port-local day starts 24 Oct 22:00Z (CEST): inside the 2h tolerance.
    m = ResolverEvaluator.evaluate(
        Q("Q8"), entities(vessels=["V012"], ports=["NLRTM"], dates=["2026-10-24T22:00:00Z", "2026-10-25T22:59:59Z"])
    )
    assert m.score == 1.0


def test_resolver_unexpected_clarification_fails():
    m = ResolverEvaluator.evaluate(Q("Q1"), {}, needs_clarification=True)
    assert m.score == 0.0 and "clarification" in m.reason


def test_resolver_not_applicable_to_guardrail_cases():
    assert ResolverEvaluator.evaluate(Q("Q11"), {}) is None


def test_resolver_did_not_run():
    m = ResolverEvaluator.evaluate(Q("Q1"), {}, resolver_ran=False)
    assert m.score == 0.0


# ------------------------------------------------------------------ planner evaluator

def test_planner_judge_full_coverage_with_tools():
    q = Q("Q4")
    plan = "Use get_cargo_exposure, get_voyage_context and track_booking."
    m = PlannerEvaluator.evaluate(q, plan, coverage_fn=lambda question, p: [1.0] * len(question.expected_plan_elements))
    assert m.score == 1.0 and m.details["method"] == "llm_judge"


def test_planner_partial_coverage_and_missing_tools():
    q = Q("Q4")
    n = len(q.expected_plan_elements)
    m = PlannerEvaluator.evaluate(q, "Look at the voyage.", coverage_fn=lambda question, p: [0.5] * n)
    assert m.score == pytest.approx(0.7 * 0.5)
    assert not m.passed


def test_planner_heuristic_fallback_when_judge_unavailable():
    q = Q("Q6")
    plan = (
        "Find Arctic Fern's current voyage VG-1088 with original and revised ETA, berth window and recorded delay. "
        "Retrieve incidents on VG-1088 including hull fouling speed loss INC-221 with status and attributed delay. "
        "Check Rotterdam congestion and the agent's queue outlook. Tools: get_voyage_context, get_vessel_context, "
        "search_incident_history, get_port_context."
    )
    m = PlannerEvaluator.evaluate(q, plan, use_llm=False)
    assert m.details["method"] == "heuristic_keyword"
    assert m.passed


def test_planner_empty_plan_scores_zero():
    assert PlannerEvaluator.evaluate(Q("Q1"), "", use_llm=False).score == 0.0


def test_planner_not_applicable_to_guardrail_cases():
    assert PlannerEvaluator.evaluate(Q("Q11"), "anything", use_llm=False) is None


# ------------------------------------------------------------------ callback + trace capture

def test_recorder_reads_guardrail_verdict():
    rec = TraceRecorder()
    rec.on_chain_end(InputGuardrailResponse(is_allowed=False, verdict="TOXIC_CONTENT", reason="abuse"))
    assert rec.guardrail_verdict == "TOXIC_CONTENT"


class _S(TypedDict, total=False):
    q: str
    out: str


@tool
def ok_tool(x: str) -> dict:
    """Returns data."""
    return {"voyage_id": x}


@tool
def bad_tool(x: str) -> dict:
    """Returns an error payload."""
    return {"status": "ERROR", "error": "graph unavailable"}


@tool
def raising_tool(x: str) -> str:
    """Raises."""
    raise ValueError("kaboom")


def _build_graph():
    async def node_a(state: _S):
        return {"q": state["q"] + "!"}

    async def node_b(state: _S):
        # Mirrors researcher_node: no config argument, tools invoked inside the node.
        await ok_tool.ainvoke({"x": "VG-1"})
        await bad_tool.ainvoke({"x": "VG-1"})
        try:
            await raising_tool.ainvoke({"x": "VG-1"})
        except ValueError:
            pass
        return {"out": "done"}

    g = StateGraph(_S)
    g.add_node("node_a", node_a)
    g.add_node("node_b", node_b)
    g.add_edge(START, "node_a")
    g.add_edge("node_a", "node_b")
    g.add_edge("node_b", END)
    return g.compile()


def test_capture_trace_records_nodes_and_nested_tool_calls():
    trace = asyncio.run(capture_trace(_build_graph(), {"q": "hi"}, {"configurable": {"thread_id": uuid.uuid4().hex}}))
    assert trace.node_order == ["node_a", "node_b"]
    assert trace.update_for("node_a")["q"] == "hi!"
    assert trace.final_state["out"] == "done"

    by_name = {c.name: c for c in trace.tool_calls}
    assert set(by_name) == {"ok_tool", "bad_tool", "raising_tool"}
    assert by_name["ok_tool"].error is None
    assert "graph unavailable" in by_name["bad_tool"].error
    assert "kaboom" in by_name["raising_tool"].error

    metric = ToolExecutionEvaluator.evaluate(Q("Q1"), trace)
    assert metric.score == pytest.approx(1 / 3, abs=1e-3) and not metric.passed


# ------------------------------------------------------------------ composite integration

def test_composite_attaches_node_metrics_and_rescores():
    q = Q("Q1")
    resp = EvaluationHarness.get_mock_response("Q1")
    trace = RunTrace(
        node_order=["node_1_guardrail", "node_2_resolver", "node_3_planner", "node_4_researcher", "node_5_validator"],
        node_updates={
            "node_1_guardrail": {"validation_status": "APPROVED"},
            "node_2_resolver": {"resolved_entities": entities(vessels=["V001"]), "needs_clarification": False},
            "node_3_planner": {"research_plan": "VG-1042 incidents INC-201 INC-203 Rotterdam queue messages"},
        },
        guardrail_verdict="APPROVED",
        tool_calls=[call("get_voyage_context"), call("search_incident_history")],
    )
    result = CompositeEvaluator.evaluate_turn(q, resp, trace=trace, enable_llm_judge=False)
    assert {"guardrail_correctness", "entity_resolution", "planner_accuracy", "tool_execution"} <= set(result.metrics)
    assert result.metrics["tool_execution"].passed
    assert result.node_trace["node_order"][0] == "node_1_guardrail"


def test_composite_without_trace_is_unchanged():
    result = CompositeEvaluator.evaluate_turn(Q("Q1"), EvaluationHarness.get_mock_response("Q1"))
    assert "tool_execution" not in result.metrics and result.node_trace is None


# ------------------------------------------------------------------ valid clarification handling

from ai_agent.src.schemas.entity_resolver_dto import ClarificationNeeded, EntityResolutionResponse


def test_recorder_captures_resolver_clarification_question():
    rec = TraceRecorder()
    rec.on_chain_end(EntityResolutionResponse(
        normalized_query="", is_ambiguous=True,
        clarification_needed=ClarificationNeeded(question="Which voyage do you mean?"),
    ))
    assert rec.resolver_clarification == "Which voyage do you mean?"


def test_recorder_ignores_unambiguous_resolution():
    rec = TraceRecorder()
    rec.on_chain_end(EntityResolutionResponse(normalized_query="q", is_ambiguous=False))
    assert rec.resolver_clarification is None


def _verdict(valid: bool):
    return lambda question, clarification: ClarificationVerdict(valid=valid, reason="judged")


def test_valid_clarification_is_accepted():
    m = ResolverEvaluator.evaluate(
        Q("Q1"), {}, needs_clarification=True,
        clarification_question="Do you mean the delayed voyage VG-1042 or the upcoming VG-1107?",
        clarification_judge=_verdict(True),
    )
    assert m.score == 1.0 and m.passed
    assert m.details["clarification_valid"] is True


def test_invalid_clarification_is_penalized():
    m = ResolverEvaluator.evaluate(
        Q("Q1"), {}, needs_clarification=True,
        clarification_question="Which vessel is Ocean Star?",
        clarification_judge=_verdict(False),
    )
    assert m.score == 0.0 and m.details["clarification_valid"] is False


def test_clarification_without_judge_verdict_is_penalized_and_unverified():
    m = ResolverEvaluator.evaluate(
        Q("Q1"), {}, needs_clarification=True, clarification_question="Which voyage?", use_llm=False,
    )
    assert m.score == 0.0 and m.details["clarification_valid"] is None


def test_composite_skips_planner_and_tools_after_valid_clarification(monkeypatch):
    from ai_agent.src.evaluation.evaluators import node_evaluators
    from ai_agent.src.evaluation.evaluators.rule_evaluator import RuleBasedEvaluator
    monkeypatch.setattr(
        node_evaluators, "_llm_clarification_verdict",
        lambda question, clarification: ClarificationVerdict(valid=True, reason="two active voyages"),
    )
    trace = RunTrace(
        node_order=["node_1_guardrail", "node_2_resolver"],
        node_updates={
            "node_1_guardrail": {"validation_status": "APPROVED"},
            "node_2_resolver": {"resolved_entities": {}, "needs_clarification": True},
        },
        guardrail_verdict="APPROVED",
        resolver_clarification="Which voyage do you mean?",
    )
    q = Q("Q1")
    result = RuleBasedEvaluator.evaluate(q, {"status": "DATA_UNAVAILABLE", "executive_summary": "No final response produced."})
    result = CompositeEvaluator.attach_node_metrics(result, q, trace, use_llm=True)
    assert result.metrics["entity_resolution"].details["clarification_valid"] is True
    assert "planner_accuracy" not in result.metrics
    assert "tool_execution" not in result.metrics
    assert "guardrail_correctness" in result.metrics


def test_composite_still_scores_planner_and_tools_after_invalid_clarification(monkeypatch):
    from ai_agent.src.evaluation.evaluators import node_evaluators
    from ai_agent.src.evaluation.evaluators.rule_evaluator import RuleBasedEvaluator
    monkeypatch.setattr(
        node_evaluators, "_llm_clarification_verdict",
        lambda question, clarification: ClarificationVerdict(valid=False, reason="vessel is in the roster"),
    )
    monkeypatch.setattr(node_evaluators, "_llm_coverage", lambda question, plan: None)  # no network in tests
    trace = RunTrace(
        node_order=["node_1_guardrail", "node_2_resolver"],
        node_updates={
            "node_1_guardrail": {"validation_status": "APPROVED"},
            "node_2_resolver": {"resolved_entities": {}, "needs_clarification": True},
        },
        guardrail_verdict="APPROVED",
        resolver_clarification="Which vessel is Ocean Star?",
    )
    q = Q("Q1")
    result = RuleBasedEvaluator.evaluate(q, {"status": "DATA_UNAVAILABLE", "executive_summary": "No final response produced."})
    result = CompositeEvaluator.attach_node_metrics(result, q, trace, use_llm=True)
    assert result.metrics["entity_resolution"].details["clarification_valid"] is False
    assert result.metrics["entity_resolution"].score == 0.0
    assert result.metrics["planner_accuracy"].score == 0.0
    assert result.metrics["tool_execution"].score == 0.0
