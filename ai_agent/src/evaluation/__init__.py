"""
Maritime Operations AI Agent Evaluation Engine.
Provides standardized benchmark datasets, multi-pillar epistemic metrics,
deterministic & LLM-as-a-Judge evaluators, test harness, and reporting tools.
"""

from ai_agent.src.evaluation.schemas import (
    BenchmarkQuestion,
    BenchmarkSummary,
    EvaluationResult,
    MetricScore,
    DataAvailabilityStatus,
    QuestionCategory,
)
from ai_agent.src.evaluation.dataset import (
    BENCHMARK_QUESTIONS,
    get_benchmark_questions,
    get_benchmark_question_by_id,
)
from ai_agent.src.evaluation.harness import EvaluationHarness, GOLDEN_REFERENCE_RESPONSES
from ai_agent.src.evaluation.evaluators.composite_evaluator import CompositeEvaluator
from ai_agent.src.evaluation.evaluators.rule_evaluator import RuleBasedEvaluator
from ai_agent.src.evaluation.reporter import EvaluationReporter

__all__ = [
    "BenchmarkQuestion",
    "BenchmarkSummary",
    "EvaluationResult",
    "MetricScore",
    "DataAvailabilityStatus",
    "QuestionCategory",
    "BENCHMARK_QUESTIONS",
    "get_benchmark_questions",
    "get_benchmark_question_by_id",
    "EvaluationHarness",
    "GOLDEN_REFERENCE_RESPONSES",
    "CompositeEvaluator",
    "RuleBasedEvaluator",
    "EvaluationReporter",
]

