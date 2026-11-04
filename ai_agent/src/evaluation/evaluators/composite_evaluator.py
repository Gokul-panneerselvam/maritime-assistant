"""
Composite Evaluator & Benchmark Summarizer.
Executes batch evaluation across questions and compiles multi-dimensional BenchmarkSummary reports.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from ai_agent.src.evaluation.schemas import (
    BenchmarkQuestion,
    BenchmarkSummary,
    EvaluationResult,
)
from ai_agent.src.evaluation.evaluators.rule_evaluator import RuleBasedEvaluator
from ai_agent.src.evaluation.evaluators.llm_judge import LLMJudgeEvaluator
from ai_agent.src.evaluation.evaluators.node_evaluators import (
    GuardrailEvaluator,
    PlannerEvaluator,
    ResolverEvaluator,
    ToolExecutionEvaluator,
)
from ai_agent.src.evaluation.trace import RunTrace


class CompositeEvaluator:
    """Orchestrates individual question evaluation and benchmark summary compilation."""

    @classmethod
    def evaluate_turn(
        cls,
        question: BenchmarkQuestion,
        response_dict: Dict[str, Any],
        latency_sec: float = 0.0,
        enable_llm_judge: bool = False,
        trace: Optional[RunTrace] = None
    ) -> EvaluationResult:
        """Evaluates a single question turn using rule evaluator, node metrics from a trace, and optional LLM judge."""
        result = RuleBasedEvaluator.evaluate(question, response_dict, latency_sec=latency_sec)

        if trace is not None:
            cls.attach_node_metrics(result, question, trace, use_llm=enable_llm_judge)

        if enable_llm_judge:
            judge_score = LLMJudgeEvaluator.evaluate(question, response_dict)
            if judge_score:
                result.metrics["llm_semantic_judge"] = judge_score
                # Re-calculate composite score including LLM judge
                total_w = sum(m.weight for m in result.metrics.values())
                w_sum = sum(m.score * m.weight for m in result.metrics.values())
                if result.negative_constraint_violations:
                    result.overall_score = 0.0
                else:
                    result.overall_score = round(w_sum / max(0.001, total_w), 3)
                result.passed = result.overall_score >= 0.70 and len(result.negative_constraint_violations) == 0

        return result

    @classmethod
    def attach_node_metrics(
        cls,
        result: EvaluationResult,
        question: BenchmarkQuestion,
        trace: RunTrace,
        use_llm: bool = False
    ) -> EvaluationResult:
        """Adds guardrail, resolver, planner and tool-execution metrics from a live-run trace, then rescores."""
        resolver_update = trace.update_for("node_2_resolver")
        planner_update = trace.update_for("node_3_planner")

        resolver_metric = ResolverEvaluator.evaluate(
            question,
            resolver_update.get("resolved_entities") or {},
            needs_clarification=bool(resolver_update.get("needs_clarification")),
            resolver_ran="node_2_resolver" in trace.node_order,
            clarification_question=trace.resolver_clarification,
            use_llm=use_llm,
        )
        # A valid clarification legitimately ends the run before planning and research, so those
        # nodes had no chance to run and are not scored.
        halted_validly = bool(resolver_metric and resolver_metric.details.get("clarification_valid"))

        node_metrics = {
            "guardrail_correctness": GuardrailEvaluator.evaluate(question, trace, result.response_status),
            "entity_resolution": resolver_metric,
            "planner_accuracy": None if halted_validly else PlannerEvaluator.evaluate(
                question, planner_update.get("research_plan"), use_llm=use_llm
            ),
            "tool_execution": None if halted_validly else ToolExecutionEvaluator.evaluate(question, trace),
        }
        for key, metric in node_metrics.items():
            if metric is not None:
                result.metrics[key] = metric

        total_w = sum(m.weight for m in result.metrics.values())
        w_sum = sum(m.score * m.weight for m in result.metrics.values())
        if result.negative_constraint_violations:
            result.overall_score = 0.0
        else:
            result.overall_score = round(w_sum / max(0.001, total_w), 3)
        result.passed = result.overall_score >= 0.70 and not result.negative_constraint_violations
        result.node_trace = trace.model_dump()
        return result

    @classmethod
    def compile_benchmark_summary(
        cls,
        results: List[EvaluationResult]
    ) -> BenchmarkSummary:
        """Aggregates a list of question evaluation results into a comprehensive BenchmarkSummary."""
        total = len(results)
        if total == 0:
            return BenchmarkSummary(
                timestamp=datetime.now(timezone.utc).isoformat(),
                total_questions=0,
                passed_questions=0,
                overall_pass_rate=0.0,
                average_score=0.0,
                epistemic_fidelity_score=0.0,
                factual_accuracy_score=0.0,
                robustness_score=0.0,
                operational_actionability_score=0.0,
                guardrail_safety_score=0.0,
                reference_average_score=0.0,
                parallel_average_score=0.0,
                guardrail_average_score=0.0,
                category_scores={},
                results=[]
            )

        passed_count = sum(1 for r in results if r.passed)
        avg_score = round(sum(r.overall_score for r in results) / total, 3)
        pass_rate = round(passed_count / total, 3)

        # Pillar scores
        def _get_metric_avg(metric_name: str) -> float:
            scores = [
                r.metrics[metric_name].score
                for r in results
                if metric_name in r.metrics
            ]
            return round(sum(scores) / len(scores), 3) if scores else 0.0

        epistemic_avg = _get_metric_avg("epistemic_fidelity")
        factual_avg = _get_metric_avg("factual_accuracy")
        robustness_avg = _get_metric_avg("robustness_and_safety")
        operational_avg = _get_metric_avg("operational_actionability")

        # Cohort scores
        ref_results = [r for r in results if r.is_reference]
        parallel_results = [r for r in results if not r.is_reference and "Guardrail" not in r.pair_id]
        guardrail_results = [r for r in results if "Guardrail" in r.pair_id]

        ref_avg = round(sum(r.overall_score for r in ref_results) / len(ref_results), 3) if ref_results else 0.0
        par_avg = round(sum(r.overall_score for r in parallel_results) / len(parallel_results), 3) if parallel_results else 0.0
        guard_avg = round(sum(r.overall_score for r in guardrail_results) / len(guardrail_results), 3) if guardrail_results else 0.0

        # Category scores
        cat_map: Dict[str, List[float]] = {}
        for r in results:
            cat_map.setdefault(r.category, []).append(r.overall_score)
        category_scores = {
            cat: round(sum(scores) / len(scores), 3)
            for cat, scores in cat_map.items()
        }

        return BenchmarkSummary(
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_questions=total,
            passed_questions=passed_count,
            overall_pass_rate=pass_rate,
            average_score=avg_score,
            epistemic_fidelity_score=epistemic_avg,
            factual_accuracy_score=factual_avg,
            robustness_score=robustness_avg,
            operational_actionability_score=operational_avg,
            guardrail_safety_score=guard_avg,
            reference_average_score=ref_avg,
            parallel_average_score=par_avg,
            guardrail_average_score=guard_avg,
            category_scores=category_scores,
            results=results
        )

