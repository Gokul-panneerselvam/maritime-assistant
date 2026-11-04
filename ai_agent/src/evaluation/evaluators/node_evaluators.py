"""
Node-level evaluators driven by a RunTrace.

  - GuardrailEvaluator      : was the query blocked/approved correctly, and did nothing run after a block?
  - ResolverEvaluator       : do resolved vessels, ports, voyages and dates match the expected resolution?
  - PlannerEvaluator        : does the research plan cover what the question needs (LLM judge, heuristic fallback)?
  - ToolExecutionEvaluator  : did any researcher tool call raise or return an error?

Each returns a MetricScore, or None when the metric does not apply to the question.
"""

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from ai_agent.src.evaluation.schemas import BenchmarkQuestion, DateWindow, MetricScore
from ai_agent.src.evaluation.trace import RunTrace
from ai_agent.src.utilities.logger import get_logger

logger = get_logger(__name__)

PASS_THRESHOLD = 0.8

DOWNSTREAM_NODES = {"node_2_resolver", "node_3_planner", "node_4_researcher", "node_5_validator"}


def _metric(name: str, score: float, reason: str, details: Dict[str, Any], threshold: float = PASS_THRESHOLD) -> MetricScore:
    score = max(0.0, min(1.0, round(score, 3)))
    return MetricScore(metric_name=name, score=score, passed=score >= threshold, weight=1.0, reason=reason, details=details)


# =============================================================================
# 1. Guardrail correctness
# =============================================================================

class GuardrailEvaluator:
    """Checks the guardrail decision and, for blocked queries, that nothing ran afterwards."""

    @classmethod
    def evaluate(cls, question: BenchmarkQuestion, trace: RunTrace, response_status: str) -> Optional[MetricScore]:
        expected = question.guardrail_expected_verdict
        if expected is None:
            return None

        should_block = expected != "APPROVED"
        guardrail_update = trace.update_for("node_1_guardrail")
        validation_status = guardrail_update.get("validation_status")
        was_blocked = validation_status == "BLOCKED_GUARDRAIL"

        checks: Dict[str, bool] = {"decision_correct": was_blocked == should_block}

        verdict_observed = trace.guardrail_verdict is not None
        if verdict_observed:
            checks["verdict_correct"] = trace.guardrail_verdict == expected

        if should_block:
            checks["refusal_status"] = response_status == "OUT_OF_SCOPE_REFUSAL"
            checks["no_downstream_nodes"] = not (set(trace.node_order) & DOWNSTREAM_NODES)
            checks["no_tool_calls"] = len(trace.tool_calls) == 0

        score = sum(checks.values()) / len(checks)
        failed = [k for k, ok in checks.items() if not ok]
        reason = (
            f"Guardrail correct: expected {expected}, {'blocked' if was_blocked else 'approved'}."
            if not failed else
            f"Guardrail check failed ({', '.join(failed)}): expected {expected}, "
            f"observed verdict {trace.guardrail_verdict or 'not observed'}, "
            f"{'blocked' if was_blocked else 'approved'}."
        )
        return _metric("Guardrail Correctness", score, reason, {
            "expected_verdict": expected,
            "observed_verdict": trace.guardrail_verdict,
            "verdict_observed": verdict_observed,
            "blocked": was_blocked,
            "checks": checks,
            "nodes_run": trace.node_order,
        }, threshold=1.0)


# =============================================================================
# 2. Entity resolution correctness
# =============================================================================

def _parse_utc(value: str) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _set_f1(expected: set, actual: set) -> float:
    if not expected and not actual:
        return 1.0
    if not expected or not actual:
        return 0.0
    tp = len(expected & actual)
    if tp == 0:
        return 0.0
    precision, recall = tp / len(actual), tp / len(expected)
    return 2 * precision * recall / (precision + recall)


def _window_matched(window: DateWindow, resolved: List[datetime]) -> bool:
    slack = timedelta(hours=window.tolerance_hours)
    start, end = _parse_utc(window.start_utc), _parse_utc(window.end_utc)
    if start is None or end is None:
        return False
    # Every resolved timestamp that falls inside the window (with slack) counts; a window is
    # matched when at least one does, so both a start-only and a start+end resolution pass.
    return any(start - slack <= ts <= end + slack for ts in resolved)


class ClarificationVerdict(BaseModel):
    """Structured judge output for an unexpected clarification question."""
    valid: bool = Field(description="True if the clarification targets a genuine ambiguity or missing detail")
    reason: str = Field(description="One short sentence")


_CLARIFICATION_JUDGE_PROMPT = """A maritime operations assistant resolves vessel, port and date references before researching a question.
It has the full 40-vessel roster and 15-port list, and resolves relative dates against a fixed snapshot (2026-10-26 12:00 UTC).
A vessel or port named in the roster is NOT ambiguous. 'Current voyage' of a named vessel is not ambiguous when the vessel has one active voyage.

It chose to ask the user a clarification question instead of proceeding. Decide whether that question is VALID.
VALID: the user's message has a genuine ambiguity or is missing something needed to answer (e.g. two vessels could match,
an unspecified time period, a vessel or port that cannot be identified), and the question is specific, concise and targets it.
INVALID: it asks for information already in the message or the roster, asks something the assistant could look up itself,
or is vague or off-topic.

[USER MESSAGE]
{query}

[EXPECTED RESOLUTION (what a correct resolver would have produced without asking)]
vessels={vessels} ports={ports} dates={dates}

[CLARIFICATION QUESTION ASKED]
{clarification}"""


def _llm_clarification_verdict(question: BenchmarkQuestion, clarification: str) -> Optional[ClarificationVerdict]:
    try:
        from ai_agent.src.agent.client.llm_client import get_llm
        llm = get_llm(model=os.getenv("EVAL_JUDGE_MODEL") or None, temperature=0.0)
        expected = question.expected_resolution
        result = llm.with_structured_output(ClarificationVerdict).invoke(_CLARIFICATION_JUDGE_PROMPT.format(
            query=question.query,
            vessels=expected.vessel_ids if expected else [],
            ports=expected.port_codes if expected else [],
            dates=[w.phrase for w in expected.date_windows] if expected else [],
            clarification=clarification,
        ))
        return ClarificationVerdict.model_validate(result) if isinstance(result, dict) else result
    except Exception as exc:
        logger.warning("Clarification judge unavailable: %s", exc)
        return None


class ResolverEvaluator:
    """Compares the resolver's entities and dates to ExpectedResolution."""

    @classmethod
    def evaluate(
        cls,
        question: BenchmarkQuestion,
        resolved_entities: Dict[str, Any],
        needs_clarification: bool = False,
        resolver_ran: bool = True,
        clarification_question: Optional[str] = None,
        use_llm: bool = True,
        clarification_judge: Optional[Callable[[BenchmarkQuestion, str], Optional[ClarificationVerdict]]] = None,
    ) -> Optional[MetricScore]:
        expected = question.expected_resolution
        if expected is None:
            return None

        if not resolver_ran:
            return _metric("Entity Resolution Correctness", 0.0, "Resolver did not run (query was blocked or the run failed earlier).", {})

        if needs_clarification and not expected.should_clarify and clarification_question:
            verdict = (clarification_judge or (_llm_clarification_verdict if use_llm else (lambda q, c: None)))(
                question, clarification_question
            )
            if verdict is not None:
                return _metric(
                    "Entity Resolution Correctness",
                    1.0 if verdict.valid else 0.0,
                    (
                        f"Resolver asked a valid clarification question instead of resolving: {verdict.reason}"
                        if verdict.valid else
                        f"Resolver asked an unnecessary clarification question: {verdict.reason}"
                    ),
                    {
                        "clarification_valid": verdict.valid,
                        "clarification_question": clarification_question,
                        "judge_reason": verdict.reason,
                    },
                )

        if needs_clarification != expected.should_clarify:
            kind = "asked for clarification" if needs_clarification else "did not ask for clarification"
            return _metric(
                "Entity Resolution Correctness", 0.0,
                f"Resolver {kind}, expected should_clarify={expected.should_clarify}.",
                {"needs_clarification": needs_clarification, "clarification_question": clarification_question,
                 "clarification_valid": None},
            )

        vessels = {str(v.get("vessel_id")).upper() for v in resolved_entities.get("vessels", []) if v.get("vessel_id")}
        ports = {str(p.get("port_code")).upper() for p in resolved_entities.get("ports", []) if p.get("port_code")}
        voyages = {str(v).upper() for v in resolved_entities.get("voyages", [])}

        components: Dict[str, float] = {}
        details: Dict[str, Any] = {}
        for label, exp, act in (
            ("vessels", {x.upper() for x in expected.vessel_ids}, vessels),
            ("ports", {x.upper() for x in expected.port_codes}, ports),
            ("voyages", {x.upper() for x in expected.voyage_ids}, voyages),
        ):
            if not exp and not act:
                continue
            if label == "vessels" and expected.allow_extra_vessels and exp:
                components[label] = len(exp & act) / len(exp)
                details[label] = {"expected": sorted(exp), "resolved": sorted(act), "recall": round(components[label], 3), "extras_allowed": True}
                continue
            components[label] = _set_f1(exp, act)
            details[label] = {"expected": sorted(exp), "resolved": sorted(act), "f1": round(components[label], 3)}

        resolved_dates = [d for d in (_parse_utc(x) for x in resolved_entities.get("dates_utc", [])) if d is not None]
        if expected.date_windows:
            date_results = {w.phrase: _window_matched(w, resolved_dates) for w in expected.date_windows}
            components["dates"] = sum(date_results.values()) / len(date_results)
            details["dates"] = {
                "expected": [f"{w.phrase}: {w.start_utc} to {w.end_utc} (+/-{w.tolerance_hours}h)" for w in expected.date_windows],
                "resolved": resolved_entities.get("dates_utc", []),
                "matched": date_results,
            }

        if not components:
            return _metric("Entity Resolution Correctness", 1.0, "No entities or dates expected and none fabricated.", details)

        score = sum(components.values()) / len(components)
        weak = [k for k, v in components.items() if v < 1.0]
        reason = "All resolved entities and dates match." if not weak else f"Mismatch in: {', '.join(weak)}."
        return _metric("Entity Resolution Correctness", score, reason, details)


# =============================================================================
# 3. Planner accuracy
# =============================================================================

class ElementJudgement(BaseModel):
    index: int = Field(description="1-based index of the expected plan element")
    coverage: Literal["yes", "partial", "no"] = Field(description="Whether the plan covers this element")
    note: str = Field(default="", description="One short sentence of evidence")


class PlanCoverage(BaseModel):
    """Structured judge output for the research plan."""
    elements: List[ElementJudgement]


_PLANNER_JUDGE_PROMPT = """You are auditing the research plan written by the planning step of a maritime operations assistant.
The plan is instructions for a researcher that will call database tools. Decide, for each expected element,
whether the plan tells the researcher to cover it. Judge meaning, not wording. A plan that targets the wrong
vessel, voyage or time window does not cover the element.

[USER QUESTION]
{question}

[EXPECTED ELEMENTS]
{elements}

[RESEARCH PLAN]
{plan}

For every expected element return coverage "yes", "partial" or "no" with a one-sentence note."""

_STOPWORDS = {
    "with", "that", "from", "this", "have", "which", "their", "into", "and", "the", "for", "are", "was", "has",
    "its", "all", "any", "each", "not", "than", "then", "when", "what", "will", "should", "must",
}


def _heuristic_coverage(elements: List[str], plan: str) -> List[float]:
    """Keyword overlap fallback when no LLM is available. Coarser than the judge; flagged in details."""
    plan_low = plan.lower()
    out = []
    for element in elements:
        tokens = [t for t in re.findall(r"[a-z0-9\-]{4,}", element.lower()) if t not in _STOPWORDS]
        if not tokens:
            out.append(0.0)
            continue
        hit = sum(1 for t in set(tokens) if t in plan_low) / len(set(tokens))
        out.append(1.0 if hit >= 0.6 else 0.5 if hit >= 0.35 else 0.0)
    return out


def _llm_coverage(question: BenchmarkQuestion, plan: str) -> Optional[List[float]]:
    try:
        from ai_agent.src.agent.client.llm_client import get_llm
        llm = get_llm(model=os.getenv("EVAL_JUDGE_MODEL") or None, temperature=0.0)
        judge = llm.with_structured_output(PlanCoverage)
        elements = "\n".join(f"{i}. {e}" for i, e in enumerate(question.expected_plan_elements, 1))
        result = judge.invoke(_PLANNER_JUDGE_PROMPT.format(question=question.query, elements=elements, plan=plan))
        if isinstance(result, dict):
            result = PlanCoverage.model_validate(result)
    except Exception as exc:
        logger.warning("Planner LLM judge unavailable, using heuristic: %s", exc)
        return None

    value = {"yes": 1.0, "partial": 0.5, "no": 0.0}
    by_index = {j.index: value[j.coverage] for j in result.elements}
    return [by_index.get(i, 0.0) for i in range(1, len(question.expected_plan_elements) + 1)]


def _tool_mentioned(tool: str, plan: str) -> bool:
    plan_low = plan.lower()
    return tool.lower() in plan_low or tool.lower().replace("_", " ") in plan_low


class PlannerEvaluator:
    """Scores the research plan on element coverage (judge) and expected tool mentions (deterministic)."""

    @classmethod
    def evaluate(
        cls,
        question: BenchmarkQuestion,
        research_plan: Optional[str],
        coverage_fn: Optional[Callable[[BenchmarkQuestion, str], Optional[List[float]]]] = None,
        use_llm: bool = True,
    ) -> Optional[MetricScore]:
        if not question.expected_plan_elements:
            return None

        plan = (research_plan or "").strip()
        if not plan:
            return _metric("Planner Accuracy", 0.0, "No research plan was produced.", {})

        coverage = (coverage_fn or (_llm_coverage if use_llm else (lambda q, p: None)))(question, plan)
        method = "llm_judge"
        if coverage is None:
            coverage = _heuristic_coverage(question.expected_plan_elements, plan)
            method = "heuristic_keyword"

        element_score = sum(coverage) / len(coverage)
        details: Dict[str, Any] = {
            "method": method,
            "elements": [
                {"element": e, "coverage": c} for e, c in zip(question.expected_plan_elements, coverage)
            ],
        }

        if question.expected_tools:
            mentioned = [t for t in question.expected_tools if _tool_mentioned(t, plan)]
            tool_score = len(mentioned) / len(question.expected_tools)
            details["tools"] = {"expected": question.expected_tools, "mentioned": mentioned, "recall": round(tool_score, 3)}
            score = 0.7 * element_score + 0.3 * tool_score
        else:
            score = element_score

        missing = [e["element"] for e in details["elements"] if e["coverage"] < 1.0]
        reason = (
            f"Plan covers all {len(coverage)} expected elements ({method})."
            if not missing else f"Plan misses or only partly covers {len(missing)}/{len(coverage)} elements ({method})."
        )
        return _metric("Planner Accuracy", score, reason, details)


# =============================================================================
# 4. Tool execution correctness
# =============================================================================

class ToolExecutionEvaluator:
    """Fails if any researcher tool call raised or returned an error."""

    @classmethod
    def evaluate(cls, question: BenchmarkQuestion, trace: RunTrace) -> Optional[MetricScore]:
        if question.guardrail_expected_verdict not in (None, "APPROVED"):
            return None  # blocked queries must make no tool calls; the guardrail metric checks that

        calls = trace.tool_calls
        names = [c.name for c in calls]
        details: Dict[str, Any] = {
            "total_calls": len(calls),
            "tools_called": names,
            "expected_tools_not_called": [t for t in question.expected_tools if t not in names],
        }

        if not calls:
            return _metric(
                "Tool Execution Correctness", 0.0,
                "Researcher made no tool calls, so the answer cannot be grounded in retrieved data.",
                details, threshold=1.0,
            )

        failed = [c for c in calls if c.error]
        details["failed_calls"] = [{"tool": c.name, "args": c.args, "error": c.error} for c in failed]
        score = (len(calls) - len(failed)) / len(calls)
        reason = (
            f"All {len(calls)} tool calls succeeded."
            if not failed else f"{len(failed)}/{len(calls)} tool calls errored: {', '.join(sorted({c.name for c in failed}))}."
        )
        return _metric("Tool Execution Correctness", score, reason, details, threshold=1.0)
