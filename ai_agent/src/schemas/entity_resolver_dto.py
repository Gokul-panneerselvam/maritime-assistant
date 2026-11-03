"""
Entity Resolution Data Transfer Objects and Schemas.
Structured models for entity resolution LLM response and node state updates.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class ResolvedVessel(BaseModel):
    """Resolved maritime vessel entity."""
    vessel_id: Optional[str] = Field(default=None, description="Canonical vessel ID, e.g. 'V001'")
    name: Optional[str] = Field(default=None, description="Vessel name, e.g. 'MV Ocean Star'")


class ResolvedPort(BaseModel):
    """Resolved seaport entity."""
    port_code: Optional[str] = Field(default=None, description="UN/LOCODE port code, e.g. 'NLRTM'")
    name: Optional[str] = Field(default=None, description="Port name, e.g. 'Rotterdam'")


class ClarificationOptionDTO(BaseModel):
    """Candidate option for clarifying ambiguous entities."""
    option_id: str = Field(description="Option identifier, e.g. '1'")
    label: str = Field(description="Human-readable label, e.g. 'MV Ocean Star (V001)'")
    description: str = Field(default="", description="Contextual description")


class ClarificationNeeded(BaseModel):
    """Clarification details when ambiguity is detected."""
    question: str = Field(
        default="Could you please specify which vessel or voyage you are referring to?",
        description="Clarifying question posed to the operator"
    )
    options: List[ClarificationOptionDTO] = Field(
        default_factory=list,
        description="2-4 candidate options for the operator to select from"
    )


class EntityResolutionResponse(BaseModel):
    """Structured response model for entity resolution and date standardization LLM call."""
    normalized_query: str = Field(
        description="Rewritten query with canonical entity names and standardized ISO-8601 UTC dates"
    )
    resolved_vessels: List[ResolvedVessel] = Field(
        default_factory=list,
        description="List of resolved maritime vessels"
    )
    resolved_ports: List[ResolvedPort] = Field(
        default_factory=list,
        description="List of resolved ports"
    )
    resolved_voyages: List[str] = Field(
        default_factory=list,
        description="List of resolved voyage IDs, e.g. ['VG-1042']"
    )
    resolved_dates_utc: List[str] = Field(
        default_factory=list,
        description="Standardized ISO-8601 UTC date/time strings, e.g. ['2026-10-26T12:00:00Z']"
    )
    is_ambiguous: bool = Field(
        default=False,
        description="Whether the query contains ambiguous vessel or voyage references requiring clarification"
    )
    clarification_needed: Optional[ClarificationNeeded] = Field(
        default=None,
        description="Clarification question and options if is_ambiguous is True; None otherwise"
    )

    @field_validator("resolved_vessels", mode="before")
    @classmethod
    def coerce_vessels(cls, v):
        if not v:
            return []
        items = []
        for item in v:
            if isinstance(item, str):
                items.append(ResolvedVessel(vessel_id=item, name=item))
            elif isinstance(item, dict):
                items.append(ResolvedVessel(**item))
            elif isinstance(item, ResolvedVessel):
                items.append(item)
        return items

    @field_validator("resolved_ports", mode="before")
    @classmethod
    def coerce_ports(cls, v):
        if not v:
            return []
        items = []
        for item in v:
            if isinstance(item, str):
                items.append(ResolvedPort(port_code=item, name=item))
            elif isinstance(item, dict):
                items.append(ResolvedPort(**item))
            elif isinstance(item, ResolvedPort):
                items.append(item)
        return items

    @field_validator("clarification_needed", mode="before")
    @classmethod
    def coerce_clarification(cls, v):
        if not v:
            return None
        if isinstance(v, str):
            return ClarificationNeeded(question=v, options=[])
        if isinstance(v, dict):
            return ClarificationNeeded(**v)
        return v


class EntityResolutionNodeResponse(BaseModel):
    """Pydantic response model for the entity resolution node state update."""
    normalized_query: str = Field(description="Normalized query text")
    resolved_entities: Dict[str, Any] = Field(
        default_factory=dict,
        description="Dictionary mapping vessel, port, voyage, and date entity lists"
    )
    needs_clarification: bool = Field(
        default=False,
        description="Flag indicating if the workflow requires user confirmation"
    )
    clarification_response: Optional[str] = Field(
        default=None,
        description="Selected clarification value resumed from interrupt"
    )
    entity_resolution_cache: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Persisted cache of entity resolution LLM evaluation"
    )


# Re-export ResearcherResponse for flexible import paths
from ai_agent.src.schemas.researcher_agent_dto import ResearcherResponse

__all__ = [
    "ResolvedVessel",
    "ResolvedPort",
    "ClarificationOptionDTO",
    "ClarificationNeeded",
    "EntityResolutionResponse",
    "EntityResolutionNodeResponse",
    "ResearcherResponse",
]

