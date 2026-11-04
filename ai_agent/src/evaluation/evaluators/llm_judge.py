"""
LLM-as-a-Judge Semantic Evaluator for Maritime Operations Assistant.
Uses configured LLM to provide qualitative grading and rubric assessment.
"""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from ai_agent.src.evaluation.schemas import BenchmarkQuestion, MetricScore
from ai_agent.src.agent.client.llm_client import get_llm
from ai_agent.src.utilities.logger import get_logger

logger = get_logger(__name__)


class LLMJudgeScore(BaseModel):
    """Structured rubric output from LLM Judge."""
    reasoning_quality_score: float = Field(ge=0.0, le=1.0, description="Logical flow and deductive clarity")
    domain_accuracy_score: float = Field(ge=0.0, le=1.0, description="Adherence to maritime operational norms")
    epistemic_tone_score: float = Field(ge=0.0, le=1.0, description="Segregation of facts vs inferences")
    overall_judge_score: float = Field(ge=0.0, le=1.0, description="Aggregate judgment score")
    critique: str = Field(description="Detailed rationale and constructive critique")


class LLMJudgeEvaluator:
    """Evaluates agent responses using an LLM Judge with maritime rubrics."""

    JUDGE_PROMPT_TEMPLATE = """You are an expert Maritime Operations Auditor and LLM Judge evaluating an AI Assistant.
Evaluate the following Assistant Response against the Ground Truth and Question.

[QUESTION]: {question}
[GROUND TRUTH]: {ground_truth}
[ASSISTANT RESPONSE]: {assistant_response}

Rubric:
1. Reasoning Quality (0.0-1.0): Does the response present structured, logical maritime deduction?
2. Domain Accuracy (0.0-1.0): Does it match ground truth facts, numbers, and operational checks?
3. Epistemic Tone (0.0-1.0): Are confirmed facts, reports, and deductions clearly distinguished?

Return your evaluation conforming strictly to the requested schema.
"""

    @classmethod
    def evaluate(
        cls,
        question: BenchmarkQuestion,
        response_dict: Dict[str, Any]
    ) -> Optional[MetricScore]:
        """Runs LLM Judge evaluation. Returns None if LLM is unavailable or offline."""
        try:
            llm = get_llm(temperature=0.0)
            if not llm:
                return None

            structured_llm = llm.with_structured_output(LLMJudgeScore)
            prompt = cls.JUDGE_PROMPT_TEMPLATE.format(
                question=question.query,
                ground_truth=question.ground_truth_summary,
                assistant_response=str(response_dict.get("executive_summary") or response_dict)
            )

            result: LLMJudgeScore = structured_llm.invoke(prompt)
            return MetricScore(
                metric_name="LLM Semantic Judge",
                score=round(result.overall_judge_score, 3),
                passed=result.overall_judge_score >= 0.70,
                weight=1.0,
                reason=result.critique,
                details={
                    "reasoning_quality": result.reasoning_quality_score,
                    "domain_accuracy": result.domain_accuracy_score,
                    "epistemic_tone": result.epistemic_tone_score,
                }
            )
        except Exception as e:
            logger.debug("LLM Judge evaluation skipped/failed: %s", e)
            return None

