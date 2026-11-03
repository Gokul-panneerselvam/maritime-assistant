"""
Typed AgentState and LangGraph channel reducers for the Maritime Operations AI Agent.
"""


from typing import Annotated, Any, Dict, List, Optional, TypedDict, Union

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from ai_agent.src.schemas.epistemic import MaritimeAgentResponse
from ai_agent.src.schemas.researcher_agent_dto import ResearcherResponse


class AgentState(TypedDict):
    """Full execution state for the 5-layer LangGraph state machine."""

    # Full message history (Human, AI, ToolMessages, etc.)
    messages: Annotated[List[BaseMessage], add_messages]

    # Filtered conversational memory (Human & AI messages only)
    clean_messages: List[BaseMessage]

    # Input Processing
    user_query: str
    normalized_query: str
    resolved_entities: Dict[str, Any]

    # Entity Resolver clarification chat
    # Temporary resolver-only history; cleared after successful resolution.
    entity_resolver_messages: List[BaseMessage]
    entity_resolution_pending: bool

    # Clarification response shown to the user
    needs_clarification: bool
    clarification_prompt: Optional[str]

    # Data Research Planner
    research_plan: Optional[str]

    # Agent Generation
    draft_response: Optional[Union[ResearcherResponse, MaritimeAgentResponse]]
    cited_entity_keys: List[str]
    cited_message_files: List[str]
    cypher_queries_executed: List[str]

    # Grounding Validation
    db_ground_truth: Dict[str, Any]
    validation_status: str
    validation_feedback: Optional[str]
    validation_retries: int

    # Final Output
    final_response: Optional[MaritimeAgentResponse]