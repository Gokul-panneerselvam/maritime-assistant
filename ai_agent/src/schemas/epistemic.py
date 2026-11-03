"""
Epistemic Response & Citation Schemas for Maritime Operations AI Agent.
Enforces strict 3-way epistemic segregation and grounded citations.
"""

from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, model_validator


# ==============================================================================
# 1. Citations Schemas (Message vs Data Nodes)
# ==============================================================================

class MessageCitation(BaseModel):
    """Citation referencing an unstructured operational communication node."""
    citation_type: Literal["MESSAGE"] = "MESSAGE"
    citation_id: str = Field(description="Unique reference tag used in the response text, e.g. CIT-01")
    filename: str = Field(description="Operational file name, e.g. noon_2026-10-06_ocean_star.txt")
    message_type: str = Field(description="Source vocabulary: Master's report, Crew message, Agent email, Technical manager, Port agent")
    trust_tier: Literal["T1", "T2", "T3", "T4"] = Field(description="Hierarchy tier for conflict resolution")
    sender: str = Field(description="From header or sender identity")
    sent_at_utc: Optional[str] = Field(default=None, description="ISO-8601 UTC timestamp")
    subject: Optional[str] = Field(default=None, description="Subject header")
    raw_message: str = Field(description="Verbatim, unmodified text of the operational message")


class EntityDataCitation(BaseModel):
    """Citation referencing a structured tabular node in the Maritime Knowledge Graph."""
    citation_type: Literal["ENTITY_NODE"] = "ENTITY_NODE"
    citation_id: str = Field(description="Unique reference tag used in the response text, e.g. CIT-02")
    label: str = Field(description="Graph Node label: Vessel, Voyage, PortCall, Incident, Booking, Congestion, Port")
    primary_id: str = Field(description="Node primary key: V001, INC-084, PC-102, VG-1042, etc.")
    attributes: Dict[str, Any] = Field(
        default_factory=dict,
        description="Complete key-value dictionary of all properties on this node"
    )
    backing_messages: List[MessageCitation] = Field(
        default_factory=list,
        description="Any Message nodes in the graph linked to this entity (e.g. REPORTS, CORROBORATES, REVISES)"
    )


Citation = Union[MessageCitation, EntityDataCitation]


# ==============================================================================
# 2. Epistemic Separation Components
# ==============================================================================

class ConfirmedFact(BaseModel):
    """A claim strictly substantiated by verified tabular records or T1/T2 communications."""
    statement: str = Field(default="", description="Factual claim with strict grounding")
    fact: Optional[str] = Field(default=None, description="Alias for statement")
    citations: List[Any] = Field(
        default_factory=list,
        description="List of citation_ids or filenames supporting this fact"
    )

    @model_validator(mode="before")
    @classmethod
    def sync_statement_fact(cls, data: Any) -> Any:
        if isinstance(data, dict):
            val = data.get("statement") or data.get("fact") or ""
            data["statement"] = val
            data["fact"] = val
        return data


class UnverifiedReport(BaseModel):
    """A claim originating from pending records, T3 crew relays, or T4 customer messages."""
    statement: str = Field(default="", description="Claim originating from unverified or pending operational logs")
    report: Optional[str] = Field(default=None, description="Alias for statement")
    source: str = Field(default="Field Communication", description="Originating channel or sender (e.g. Crew WhatsApp Relay)")
    citations: List[Any] = Field(
        default_factory=list,
        description="List of citation_ids or filenames supporting this report"
    )

    @model_validator(mode="before")
    @classmethod
    def sync_statement_report(cls, data: Any) -> Any:
        if isinstance(data, dict):
            val = data.get("statement") or data.get("report") or ""
            data["statement"] = val
            data["report"] = val
        return data


class SystemInference(BaseModel):
    """The agent's reasoned projection, mathematical deduction, or root-cause hypothesis."""
    deduction: str = Field(default="", description="Synthesized operational deduction or forward projection")
    inference: Optional[str] = Field(default=None, description="Alias for deduction")
    rationale: str = Field(default="", description="Step-by-step reasoning linking facts and reports to this conclusion")
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = "MEDIUM"
    supporting_citations: List[Any] = Field(
        default_factory=list,
        description="List of citations grounding the premises of this inference"
    )

    @model_validator(mode="before")
    @classmethod
    def sync_deduction_inference(cls, data: Any) -> Any:
        if isinstance(data, dict):
            val = data.get("deduction") or data.get("inference") or ""
            data["deduction"] = val
            data["inference"] = val
            if not data.get("supporting_citations") and data.get("citations"):
                data["supporting_citations"] = data.get("citations")
        return data


class PremiseCorrection(BaseModel):
    """Explicit correction when a user query is built upon a false assumption."""
    user_assumption: str = Field(description="The incorrect premise found in the user prompt")
    grounded_reality: str = Field(description="The verified ground truth from the graph")
    citations: List[str] = Field(
        default_factory=list,
        description="Citations supporting the ground truth"
    )


# ==============================================================================
# 3. Clarification Models
# ==============================================================================

class ClarificationOption(BaseModel):
    option_id: str = Field(description="Identifier for the option")
    label: str = Field(description="Short human-readable label")
    description: str = Field(description="Detailed explanation of the choice")


class ClarificationPrompt(BaseModel):
    question: str = Field(description="Clarifying question posed to the operator")
    reason: str = Field(description="Why clarification is necessary before proceeding")
    options: List[ClarificationOption] = Field(default_factory=list)


# ==============================================================================
# 4. Final Maritime Agent Response Model
# ==============================================================================

class MaritimeAgentResponse(BaseModel):
    """Structured response object emitted by the Maritime Operations AI Agent."""
    status: Literal[
        "SUCCESS",
        "CLARIFICATION_NEEDED",
        "DATA_UNAVAILABLE",
        "FALSE_PREMISE",
        "OUT_OF_SCOPE_REFUSAL"
    ] = "SUCCESS"
    executive_summary: str = Field(
        default="",
        description="Concise operational synthesis in executive markdown format"
    )
    confirmed_facts: List[Union[ConfirmedFact, Any]] = Field(default_factory=list)
    unverified_reports: List[Union[UnverifiedReport, Any]] = Field(default_factory=list)
    system_inferences: List[Union[SystemInference, Any]] = Field(default_factory=list)
    false_premises_detected: List[PremiseCorrection] = Field(default_factory=list)
    clarification: Optional[ClarificationPrompt] = None
    citations: List[Citation] = Field(default_factory=list)
    cypher_queries_executed: List[str] = Field(default_factory=list)
    data_missing_explanation: Optional[str] = Field(
        default=None,
        description="Explanation if required data was absent from the database"
    )

    @model_validator(mode="before")
    @classmethod
    def populate_executive_summary(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "status" in data and isinstance(data["status"], str):
                data["status"] = data["status"].strip().upper()

            if not data.get("executive_summary"):
                fallback = (
                    data.get("summary")
                    or data.get("data_missing_explanation")
                    or data.get("message")
                    or data.get("answer")
                    or (
                        f"Operational status: {data.get('status', 'SUCCESS')}. "
                        + (data.get("data_missing_explanation") or "Operational query evaluated.")
                    )
                )
                data["executive_summary"] = str(fallback)

            if "epistemic_sections" in data and isinstance(data["epistemic_sections"], dict):
                ep = data["epistemic_sections"]
                if "confirmed_facts" in ep and not data.get("confirmed_facts"):
                    data["confirmed_facts"] = ep["confirmed_facts"]
                if "unverified_reports" in ep and not data.get("unverified_reports"):
                    data["unverified_reports"] = ep["unverified_reports"]
                if "system_inferences" in ep and not data.get("system_inferences"):
                    data["system_inferences"] = ep["system_inferences"]

            if data.get("status") == "DATA_UNAVAILABLE" and not data.get("data_missing_explanation"):
                data["data_missing_explanation"] = data.get("executive_summary")

        return data


# ==============================================================================
# 5. Input Guardrail Models
# ==============================================================================

class InputGuardrailResponse(BaseModel):
    """Structured response model for input guardrail LLM evaluation."""
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
    clean_messages: List[Any] = Field(
        default_factory=list,
        description="Filtered human and AI conversational messages."
    )
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



