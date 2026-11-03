from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, model_validator

from ai_agent.src.schemas.epistemic import MaritimeAgentResponse


# ==============================================================================
# 1. Input Guardrail Response Schema
# ==============================================================================

class InputGuardrailResponse(BaseModel):
    """Structured response model for input guardrail evaluation."""
    is_allowed: bool = Field(
        description="Whether the user message is safe and within maritime domain scope to proceed."
    )
    verdict: Literal["APPROVED", "OUT_OF_SCOPE", "PROMPT_INJECTION", "TOXIC_CONTENT"] = Field(
        description="Classification verdict for the user input."
    )
    reason: str = Field(
        description="Clear explanation of why the input was approved or rejected."
    )
    suggested_response: Optional[str] = Field(
        default=None,
        description="If rejected, a polite explanation steering the user back to maritime operations; None if approved."
    )


class InputGuardrailNodeResponse(BaseModel):
    """Pydantic response model for the input guardrail node state update."""
    user_query: Optional[str] = Field(
        default=None,
        description="The active user query being processed."
    )
    validation_status: Literal["APPROVED", "BLOCKED_GUARDRAIL"] = Field(
        description="Guardrail outcome: 'APPROVED' to continue pipeline, or 'BLOCKED_GUARDRAIL' to halt."
    )
    final_response: Optional[MaritimeAgentResponse] = Field(
        default=None,
        description="Refusal response when input is blocked by guardrails."
    )


__all__ = ["InputGuardrailResponse", "InputGuardrailNodeResponse"]
