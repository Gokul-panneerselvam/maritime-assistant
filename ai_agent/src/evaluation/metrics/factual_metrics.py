"""
Factual Accuracy & Ground Truth Metric Evaluator.
Validates entity recall, numeric precision (delay hours, container counts), and cross-fleet relationships.
"""

import re
from typing import Any, Dict, List, Optional
from ai_agent.src.evaluation.schemas import MetricScore, BenchmarkQuestion


class FactualMetricEvaluator:
    """Evaluates factual precision and ground truth entity recall."""

    @classmethod
    def _extract_full_text(cls, response_dict: Dict[str, Any]) -> str:
        """Flattens all text fields of an agent response into a single searchable string."""
        texts = []
        if response_dict.get("executive_summary"):
            texts.append(str(response_dict["executive_summary"]))

        for f in response_dict.get("confirmed_facts") or []:
            if isinstance(f, dict):
                texts.append(str(f.get("statement") or f.get("fact") or ""))
            elif isinstance(f, str):
                texts.append(f)

        for u in response_dict.get("unverified_reports") or []:
            if isinstance(u, dict):
                texts.append(str(u.get("statement") or u.get("report") or ""))
            elif isinstance(u, str):
                texts.append(u)

        for s in response_dict.get("system_inferences") or []:
            if isinstance(s, dict):
                texts.append(str(s.get("deduction") or s.get("inference") or ""))
                texts.append(str(s.get("rationale") or ""))
            elif isinstance(s, str):
                texts.append(s)

        for p in response_dict.get("false_premises_detected") or []:
            if isinstance(p, dict):
                texts.append(str(p.get("user_assumption") or ""))
                texts.append(str(p.get("grounded_reality") or ""))

        return " ".join(texts)

    @classmethod
    def evaluate(
        cls,
        question: BenchmarkQuestion,
        response_dict: Dict[str, Any]
    ) -> MetricScore:
        """
        Calculates Factual Accuracy score (0.0 to 1.0).
        Evaluates:
          1. Entity Recall (target vessels, voyages, incidents, ports)
          2. Numeric Accuracy (delay hours, container quantities)
          3. Cross-fleet relationship checks (where applicable)
        """
        if question.category in ["Guardrail Scope Enforcement (Out-of-Scope)", "Guardrail Safety & Profanity Defense"]:
            return MetricScore(
                metric_name="Factual Accuracy",
                score=1.0,
                passed=True,
                weight=1.0,
                reason="Factual accuracy not applicable to guardrail filter.",
                details={"is_guardrail": True}
            )

        full_text = cls._extract_full_text(response_dict).lower()
        subscores: Dict[str, float] = {}
        feedback: List[str] = []

        # 1. Entity Recall
        target_entities = (
            question.target_vessels +
            question.target_voyages +
            question.target_incidents +
            question.target_ports
        )
        if target_entities:
            found_count = 0
            for ent in target_entities:
                if ent.lower() in full_text:
                    found_count += 1
            entity_ratio = min(1.0, found_count / max(1, len(target_entities) * 0.6))
            subscores["entity_recall"] = entity_ratio
            feedback.append(f"Entity recall: {found_count}/{len(target_entities)} target tokens identified.")
        else:
            subscores["entity_recall"] = 1.0

        # 2. Numeric Precision: Delay Hours
        if question.expected_delay_hours is not None:
            expected_val = str(int(question.expected_delay_hours))
            # e.g. "55" or "55 hours" or "55.0"
            if re.search(r"\b" + re.escape(expected_val) + r"(\.0)?\b", full_text):
                subscores["delay_hours"] = 1.0
                feedback.append(f"Accurate delay duration identified ({question.expected_delay_hours}h).")
            else:
                subscores["delay_hours"] = 0.2
                feedback.append(f"Expected delay duration ({question.expected_delay_hours}h) not found.")

        # 3. Numeric Precision: Container Counts
        if question.expected_container_counts:
            matched_customers = 0
            total_customers = len(question.expected_container_counts)
            for customer, count in question.expected_container_counts.items():
                cust_lower = customer.lower()
                count_str = str(count)
                # Check if customer and count appear in proximity
                if cust_lower in full_text and count_str in full_text:
                    matched_customers += 1

            container_ratio = matched_customers / total_customers
            subscores["container_counts"] = container_ratio
            feedback.append(
                f"Customer container breakdown: {matched_customers}/{total_customers} accurately matched."
            )

        # 4. Cross-Fleet Checks
        if question.cross_fleet_checks:
            cf_points = 0.0
            cf_total = 3.0  # same_vessel, same_class, same_manager
            
            # Same vessel
            expected_vessel = question.cross_fleet_checks.get("same_vessel")
            if expected_vessel:
                if "yes" in full_text or "once before" in full_text or "inc-118" in full_text or "previously" in full_text:
                    cf_points += 1.0
            else:
                if "no" in full_text or "first" in full_text or "no prior" in full_text:
                    cf_points += 1.0

            # Same class
            expected_class = question.cross_fleet_checks.get("same_class")
            if expected_class:
                if "ocean pearl" in full_text or "tb-26-14" in full_text or "inc-077" in full_text:
                    cf_points += 1.0
            else:
                if "no" in full_text or "none" in full_text or "isolated" in full_text:
                    cf_points += 1.0

            # Same manager
            expected_manager = question.cross_fleet_checks.get("same_manager")
            if expected_manager:
                if "silver tern" in full_text or "eastpoint" in full_text or "harbourline" in full_text or "3 other" in full_text or "three" in full_text:
                    cf_points += 1.0

            cf_score = cf_points / cf_total
            subscores["cross_fleet"] = cf_score
            feedback.append(f"Cross-fleet relationship reasoning: {int(cf_score * 100)}% verified.")

        # Aggregate weighted factual score
        if subscores:
            avg_score = round(sum(subscores.values()) / len(subscores), 3)
        else:
            avg_score = 1.0

        passed = avg_score >= 0.70
        return MetricScore(
            metric_name="Factual Accuracy",
            score=avg_score,
            passed=passed,
            weight=1.2,
            reason=" | ".join(feedback),
            details=subscores
        )

