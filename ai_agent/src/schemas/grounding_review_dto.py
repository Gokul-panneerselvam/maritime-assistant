"""
Grounding Review DTO for Maritime Operations AI Agent Reviewer Node.
Defines the structured output schema for the LLM judge.
"""

from pydantic import BaseModel, Field


class GroundingReview(BaseModel):
    """Structured output from LLM Grounding Judge."""
    is_grounded: bool = Field(
        description="Whether all claims in the researcher response are strictly grounded in the retrieved database truth."
    )
    hallucination_detected: bool = Field(
        description="True if unsupported claims, fabricated entities, or false citations were detected."
    )
    feedback_for_agent: str = Field(
        default="",
        description="Actionable critique and instructions for the researcher agent if claims were ungrounded."
    )


__all__ = ["GroundingReview"]

