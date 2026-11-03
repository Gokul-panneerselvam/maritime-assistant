"""
Entity Resolution and Temporal Normalization Node for Maritime Operations AI Agent.

Standardizes vessel names to canonical IDs, port names to UN/LOCODEs, and timestamps
to ISO-8601 UTC. Detects ambiguous maritime entities and asks free-text clarification
questions through a resolver-specific chat history.

The resolver chat is temporary:
- It is initialized from clean_messages + user_query when resolution starts.
- Follow-up user answers are appended while clarification is pending.
- It is cleared after successful resolution.
- It is never merged into clean_messages.
"""


from typing import Any, Dict, List, Optional

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)

from ai_agent.src.utilities.logger import get_logger
from ai_agent.src.schemas.entity_resolver_dto import (
    EntityResolutionResponse,
    EntityResolutionNodeResponse,
)
from ai_agent.src.agent.state import AgentState
from ai_agent.src.agent.prompts.prompt_loader import get_agent_prompt
from ai_agent.src.agent.client.llm_client import get_llm


logger = get_logger(__name__)


def _format_messages(messages: List[BaseMessage]) -> str:
    """Formats LangChain messages as readable chat text."""
    return "\n".join(
        f"{getattr(message, 'type', 'message').upper()}: {getattr(message, 'content', '')}"
        for message in messages
    )


def run_entity_resolution_llm(
    resolver_messages: List[BaseMessage],
) -> EntityResolutionResponse:
    """Runs structured entity resolution using the resolver-specific chat history."""
    prompt_config = get_agent_prompt("entity_resolution")
    system_prompt = prompt_config["system"]

    resolution_prompt = f"""
                        Conversation History:
                        {_format_messages(resolver_messages) or "No prior history"}

                        Standardize entities, resolve dates to ISO-8601 UTC
                        (Reference snapshot: 2026-10-26T12:00:00Z), and detect ambiguities.

                        If information is insufficient or ambiguous, ask one concise clarification question.
                        Do not provide answer options.
                        """

    llm = get_llm(temperature=0.0)
    structured_llm = llm.with_structured_output(EntityResolutionResponse)

    try:
        result = structured_llm.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=resolution_prompt),
            ]
        )

        if isinstance(result, dict):
            result = EntityResolutionResponse.model_validate(result)

        return result

    except Exception as exc:
        logger.error(
            "Entity resolution structured output failed: %s", exc, exc_info=True
        )
        raise RuntimeError(f"Entity resolution evaluation failed: {exc}") from exc


def build_clarification_response(
    result: EntityResolutionResponse,
    resolver_messages: List[BaseMessage],
) -> EntityResolutionNodeResponse:
    """Builds a clarification response and preserves the resolver chat for the next turn."""
    default_question = (
        "Could you please provide more details about the vessel or voyage?"
    )

    clarification = result.clarification_needed
    question = (
        clarification.question
        if clarification and clarification.question
        else default_question
    )

    return EntityResolutionNodeResponse(
        normalized_query="",
        resolved_entities={},
        needs_clarification=True,
        clarification_response=question,
        entity_resolver_messages=resolver_messages
        + [AIMessage(content=question)],
        entity_resolution_pending=True,
    )


def build_final_resolution(
    result: EntityResolutionResponse,
    user_query: str,
) -> EntityResolutionNodeResponse:
    """Builds the final successful resolution response and clears resolver chat."""
    resolved_entities = {
        "vessels": [vessel.model_dump() for vessel in result.resolved_vessels],
        "ports": [port.model_dump() for port in result.resolved_ports],
        "voyages": list(result.resolved_voyages),
        "dates_utc": list(result.resolved_dates_utc),
    }

    return EntityResolutionNodeResponse(
        normalized_query=result.normalized_query or user_query,
        resolved_entities=resolved_entities,
        needs_clarification=False,
        clarification_response=None,
        entity_resolver_messages=[],
        entity_resolution_pending=False,
    )


def entity_resolution_node(state: AgentState) -> EntityResolutionNodeResponse:
    """
    Entity Resolution and Temporal Normalization node.

    Maintains a temporary resolver-specific clarification chat. On ambiguity, returns a
    clarification question and ends the node. On the next user turn, the user answer is
    appended to this resolver chat and resolution is retried.

    On successful resolution, the resolver chat is cleared and is not added to
    clean_messages.
    """
    user_query = state.get("user_query", "")
    resolver_messages = state.get("entity_resolver_messages", [])
    is_pending = state.get("entity_resolution_pending", False)

    if is_pending:
        # The new user_query is the clarification answer.
        resolver_messages = resolver_messages + [HumanMessage(content=user_query)]
        logger.info(
            "Entity resolution: continuing clarification chat with %d messages",
            len(resolver_messages),
        )
    else:
        # Start a fresh resolver chat from clean history plus the current query.
        clean_history = state.get("clean_messages", [])
        resolver_messages = list(clean_history) + [HumanMessage(content=user_query)]
        logger.info("Entity resolution: starting new resolver chat")

    result = run_entity_resolution_llm(resolver_messages)

    if result.is_ambiguous:
        return build_clarification_response(result, resolver_messages)

    return build_final_resolution(result, user_query)


__all__ = [
    "run_entity_resolution_llm",
    "build_clarification_response",
    "build_final_resolution",
    "entity_resolution_node",
]