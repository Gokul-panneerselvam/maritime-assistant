"""
Operational Actionability Metric Evaluator.
Validates the presence of actionable, concrete next steps for fleet dispatch and operations.
"""

from typing import Any, Dict, List
from ai_agent.src.evaluation.schemas import MetricScore, BenchmarkQuestion, QuestionCategory


class OperationalMetricEvaluator:
    """Evaluates the actionability and completeness of operational follow-ups."""

    @classmethod
    def _extract_full_text(cls, response_dict: Dict[str, Any]) -> str:
        texts = []
        if response_dict.get("executive_summary"):
            texts.append(str(response_dict["executive_summary"]))

        for f in response_dict.get("confirmed_facts") or []:
            if isinstance(f, dict):
                texts.append(str(f.get("statement") or f.get("fact") or ""))
            elif isinstance(f, str):
                texts.append(f)

        for s in response_dict.get("system_inferences") or []:
            if isinstance(s, dict):
                texts.append(str(s.get("deduction") or s.get("inference") or ""))
                texts.append(str(s.get("rationale") or ""))
            elif isinstance(s, str):
                texts.append(s)

        return " ".join(texts).lower()

    @classmethod
    def evaluate(
        cls,
        question: BenchmarkQuestion,
        response_dict: Dict[str, Any]
    ) -> MetricScore:
        """
        Calculates the Operational Actionability score (0.0 to 1.0).
        Evaluates presence of domain-informed operational next steps.
        """
        if question.category in [
            QuestionCategory.GUARDRAIL_SCOPE,
            QuestionCategory.GUARDRAIL_SAFETY,
            "Guardrail Scope Enforcement (Out-of-Scope)",
            "Guardrail Safety & Profanity Defense",
        ]:
            return MetricScore(
                metric_name="Operational Actionability",
                score=1.0,
                passed=True,
                weight=1.0,
                reason="Operational follow-up not applicable to guardrail filter.",
                details={"is_guardrail": True}
            )

        if not question.expected_operational_checks:
            return MetricScore(
                metric_name="Operational Actionability",
                score=1.0,
                passed=True,
                weight=1.0,
                reason="No specific operational follow-ups required for this query category.",
                details={}
            )

        full_text = cls._extract_full_text(response_dict)
        matched_checks = 0
        total_checks = len(question.expected_operational_checks)
        feedback: List[str] = []

        for check in question.expected_operational_checks:
            # Extract key operational terms from the ground truth check
            keywords = [
                w.lower() for w in check.split()
                if len(w) > 3 and w.lower() not in ["with", "that", "from", "regarding", "should", "must", "check"]
            ]
            # Match if at least 2 key terms from the check appear
            matches = sum(1 for kw in keywords if kw in full_text)
            if matches >= 2:
                matched_checks += 1

        ratio = round(matched_checks / max(1, total_checks), 3)
        passed = ratio >= 0.50

        feedback.append(
            f"Matched {matched_checks}/{total_checks} operational follow-up recommendations."
        )

        return MetricScore(
            metric_name="Operational Actionability",
            score=ratio,
            passed=passed,
            weight=1.0,
            reason=" | ".join(feedback),
            details={"matched_checks": matched_checks, "total_checks": total_checks}
        )
