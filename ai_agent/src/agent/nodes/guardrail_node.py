"""
Input Guardrail Node for Maritime Operations AI Agent.
Evaluates domain scope, prompt injection / jailbreak attempts, and toxicity
using LangChain structured output with InputGuardrailResponse schema.
Returns a typed InputGuardrailNodeResponse Pydantic model.
"""

from typing import Any, Dict, List, Literal, Optional
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

from ai_agent.src.utilities.logger import get_logger
from ai_agent.src.schemas.epistemic import (
    MaritimeAgentResponse
)
from ai_agent.src.schemas.input_guardrail_dto import (
    InputGuardrailResponse,
    InputGuardrailNodeResponse
)
from ai_agent.src.agent.state import AgentState
from ai_agent.src.agent.prompts.prompt_loader import get_agent_prompt
from ai_agent.src.agent.client.llm_client import get_llm, LLMClient

logger = get_logger(__name__)


def extract_clean_messages(messages: List[BaseMessage]) -> List[BaseMessage]:
    """Filters conversational history to only Human and AI messages meant for humans."""
    clean = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            clean.append(msg)
        elif isinstance(msg, AIMessage):
            if not getattr(msg, "tool_calls", None) and not msg.additional_kwargs.get("is_internal"):
                clean.append(msg)
    return clean


def input_guardrail_node(state: AgentState) -> InputGuardrailNodeResponse:
    """Evaluates user query for maritime scope, injection attacks, and safety via structured LLM output."""
    messages = state.get("messages", [])
    clean_history = extract_clean_messages(messages)
    state['clean_messages'] = clean_history
    user_query = state.get("user_query") or (clean_history[-1].content if clean_history else "")

    prompt_config = get_agent_prompt("input_guardrail")
    system_prompt = prompt_config["system"]

    history_text = "\n".join([f"{m.type.upper()}: {m.content}" for m in clean_history[-5:-1]])
    user_eval_prompt = f"""Conversation History:
                        {history_text or "No prior history"}

                        Current User Message to Evaluate:
                        {user_query}

                        Evaluate the message according to safety and domain criteria.
                        """

    llm = get_llm(temperature=1)
    structured_llm = llm.with_structured_output(InputGuardrailResponse)

    try:
        eval_result = structured_llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_eval_prompt)
        ])
    except Exception as e:
        logger.error("Input guardrail structured output evaluation failed: %s", e, exc_info=True)
        raise RuntimeError(f"Input guardrail evaluation failed: {e}") from e

    if not eval_result.is_allowed:
        suggested = eval_result.suggested_response or (
            "I am the Maritime Operations AI Agent dedicated to commercial fleet tracking, "
            "port congestion, vessel voyages, and container booking analysis. "
            "Please provide a maritime operational question."
        )
        refusal_response = MaritimeAgentResponse(
            status="OUT_OF_SCOPE_REFUSAL",
            executive_summary=suggested,
            confirmed_facts=[],
            unverified_reports=[],
            system_inferences=[],
            false_premises_detected=[],
            clarification=None,
            citations=[],
            cypher_queries_executed=[]
        )
        return InputGuardrailNodeResponse(
            final_response=refusal_response,
            validation_status="BLOCKED_GUARDRAIL"
        )

    return InputGuardrailNodeResponse(
        user_query=user_query,
        validation_status="APPROVED"
    )


__all__ = [
    "InputGuardrailResponse",
    "InputGuardrailNodeResponse",
    "input_guardrail_node",
    "extract_clean_messages"
]
