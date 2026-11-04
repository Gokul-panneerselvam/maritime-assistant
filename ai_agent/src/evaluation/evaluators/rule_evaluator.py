"""
Deterministic Rule-Based Evaluator.
Executes high-speed, 100% reproducible evaluation across Epistemic, Factual, Robustness, and Operational metrics.
"""

from typing import Any, Dict, Optional
from ai_agent.src.evaluation.schemas import (
    BenchmarkQuestion,
    EvaluationResult,
    MetricScore,
)
from ai_agent.src.evaluation.metrics.epistemic_metrics import EpistemicMetricEvaluator
from ai_agent.src.evaluation.metrics.factual_metrics import FactualMetricEvaluator
from ai_agent.src.evaluation.metrics.robustness_metrics import RobustnessMetricEvaluator
from ai_agent.src.evaluation.metrics.operational_metrics import OperationalMetricEvaluator


class RuleBasedEvaluator:
    """Evaluates agent responses using deterministic rules, schemas, and exact entity matching."""

    @classmethod
    def evaluate(
        cls,
        question: BenchmarkQuestion,
        response_dict: Dict[str, Any],
        latency_sec: float = 0.0
    ) -> EvaluationResult:
        """Evaluates an agent response against a benchmark question."""
        metrics: Dict[str, MetricScore] = {}

        # 1. Epistemic Metric
        epistemic_metric = EpistemicMetricEvaluator.evaluate(question, response_dict)
        metrics["epistemic_fidelity"] = epistemic_metric

        # 2. Factual Accuracy Metric
        factual_metric = FactualMetricEvaluator.evaluate(question, response_dict)
        metrics["factual_accuracy"] = factual_metric

        # 3. Robustness & Safety Metric
        robustness_metric = RobustnessMetricEvaluator.evaluate(question, response_dict)
        metrics["robustness_and_safety"] = robustness_metric

        # 4. Operational Actionability Metric
        operational_metric = OperationalMetricEvaluator.evaluate(question, response_dict)
        metrics["operational_actionability"] = operational_metric

        # Compute Composite Weighted Score
        total_weight = sum(m.weight for m in metrics.values())
        weighted_sum = sum(m.score * m.weight for m in metrics.values())
        overall_score = round(weighted_sum / max(0.001, total_weight), 3)

        # Negative constraint check: If robustness failed due to negative constraint violations, score = 0
        violations = robustness_metric.details.get("violations", [])
        if violations:
            overall_score = 0.0

        passed = overall_score >= 0.70 and len(violations) == 0

        # Status match
        resp_status = str(response_dict.get("status", "")).upper()
        exp_status = question.expected_status.upper()
        status_match = (resp_status == exp_status) or (
            exp_status in ["DATA_UNAVAILABLE", "FALSE_PREMISE"] and resp_status in ["DATA_UNAVAILABLE", "FALSE_PREMISE"]
        )

        agent_summary = str(response_dict.get("executive_summary") or response_dict.get("summary") or "")

        return EvaluationResult(
            question_id=question.id,
            pair_id=question.pair_id,
            is_reference=question.is_reference,
            query=question.query,
            category=question.category.value,
            data_availability=question.data_availability.value,
            response_status=resp_status,
            status_match=status_match,
            agent_summary=agent_summary[:250] + ("..." if len(agent_summary) > 250 else ""),
            metrics=metrics,
            overall_score=overall_score,
            passed=passed,
            latency_sec=round(latency_sec, 2),
            negative_constraint_violations=violations,
            raw_response=response_dict
        )

