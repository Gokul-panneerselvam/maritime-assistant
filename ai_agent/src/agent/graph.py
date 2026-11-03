"""
LangGraph StateGraph Definition for Maritime Operations AI Agent.
Compiles the 5-layer workflow with conditional routing, self-correction loop,
and persistent SQLite checkpointing.
"""


from typing import Literal

from langgraph.graph import StateGraph, START, END

from ai_agent.src.utilities.logger import get_logger
from ai_agent.src.agent.state import AgentState
from ai_agent.src.agent.nodes.guardrail_node import input_guardrail_node
from ai_agent.src.agent.nodes.entity_resolver_node import entity_resolution_node
from ai_agent.src.agent.nodes.planner_node import planner_node
from ai_agent.src.agent.nodes.researcher_node import researcher_node
from ai_agent.src.agent.nodes.reviewer_node import validator_and_hydration_node
from ai_agent.src.agent.memory.checkpointer import get_checkpointer


logger = get_logger(__name__)


def route_guardrail(state: AgentState) -> Literal["node_2_resolver", "__end__"]:
    """Routes to entity resolution or terminates directly if blocked by guardrails."""
    if state.get("validation_status") == "BLOCKED_GUARDRAIL":
        return END

    return "node_2_resolver"


def route_after_resolver(state: AgentState) -> Literal["node_3_planner", "__end__"]:
    """
    Routes after entity resolution.

    If the resolver needs clarification, end this run and return the clarification
    question to the user. The next user message will enter through the guardrail and
    reach the resolver again.
    """
    if state.get("entity_resolution_pending") or state.get("needs_clarification"):
        return END

    return "node_3_planner"


def route_validator(state: AgentState) -> Literal["node_4_researcher", "__end__"]:
    """Conditional self-correction edge: re-runs agent node if validation failed."""
    if state.get("validation_status") == "FAILED":
        return "node_4_researcher"

    return END


def build_maritime_agent_graph():
    """Builds and compiles the Maritime Operations StateGraph."""
    checkpointer = get_checkpointer()
    builder = StateGraph(AgentState)

    # Add Nodes
    builder.add_node("node_1_guardrail", input_guardrail_node)
    builder.add_node("node_2_resolver", entity_resolution_node)
    builder.add_node("node_3_planner", planner_node)
    builder.add_node("node_4_researcher", researcher_node)
    builder.add_node("node_5_validator", validator_and_hydration_node)

    # Add Edges
    builder.add_edge(START, "node_1_guardrail")

    # Conditional routing after input guardrail
    builder.add_conditional_edges(
        "node_1_guardrail",
        route_guardrail,
        {
            "node_2_resolver": "node_2_resolver",
            END: END,
        },
    )

    # Resolver either asks a clarification question and ends,
    # or successfully resolves entities and continues to data research planner.
    builder.add_conditional_edges(
        "node_2_resolver",
        route_after_resolver,
        {
            "node_3_planner": "node_3_planner",
            END: END,
        },
    )

    builder.add_edge("node_3_planner", "node_4_researcher")
    builder.add_edge("node_4_researcher", "node_5_validator")

    # Conditional routing after validator (self-correction loop vs finish)
    builder.add_conditional_edges(
        "node_5_validator",
        route_validator,
        {
            "node_4_researcher": "node_4_researcher",
            END: END,
        },
    )

    compiled_graph = builder.compile(checkpointer=checkpointer)
    return compiled_graph


_compiled_graph = None


def get_graph():
    global _compiled_graph

    if _compiled_graph is None:
        _compiled_graph = build_maritime_agent_graph()

    return _compiled_graph