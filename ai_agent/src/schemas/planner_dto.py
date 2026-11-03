"""
Data Research Planner DTOs for Maritime Operations AI Agent.
Defines schemas for the research planner LLM structured output and node response.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class DataResearchPlan(BaseModel):
    """
    Structured data research plan generated from the user query and Knowledge Graph schema.
    Instructs the researcher agent on what data and operational records to check.
    """
    summary_of_intent: str = Field(
        ...,
        description="Clear summary of the user's operational query and what questions must be answered."
    )
    target_entities: List[str] = Field(
        default_factory=list,
        description="Target vessels, ports, voyages, incidents, or bookings identified for investigation."
    )
    relevant_kg_nodes: List[str] = Field(
        default_factory=list,
        description="Relevant Knowledge Graph node labels (e.g., Vessel, Voyage, PortCall, Incident, Congestion, Booking, Message)."
    )
    relevant_relationships: List[str] = Field(
        default_factory=list,
        description="Connected relationship types to traverse (e.g., OPERATES_VOYAGE, HAS_PORT_CALL, EXPERIENCED_INCIDENT, DESCRIBES_CONGESTION)."
    )
    data_points_to_check: List[str] = Field(
        default_factory=list,
        description="Specific data attributes, timestamps (UTC), delay hours, congestion levels, or statuses to inspect."
    )
    descriptive_plan: str = Field(
        ...,
        description="Comprehensive, step-by-step instructions for the researcher agent outlining exactly what queries to run and what data to check."
    )


class PlannerNodeResponse(BaseModel):
    """Response payload returned by the research planner node into AgentState."""
    research_plan: str


__all__ = ["DataResearchPlan", "PlannerNodeResponse"]

