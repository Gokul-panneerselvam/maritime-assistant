"""
Data Research Planner Node for Maritime Operations AI Agent.
Analyzes the user message, normalized query, and resolved entities alongside
the Maritime Knowledge Graph schema to produce a descriptive research plan
instructing the researcher agent on what data, nodes, relationships, and backing
records to investigate.
"""

import json
from typing import Any, Dict
from langchain_core.messages import HumanMessage, SystemMessage

from ai_agent.src.utilities.logger import get_logger
from ai_agent.src.schemas.planner_dto import (
    DataResearchPlan,
    PlannerNodeResponse
)
from ai_agent.src.agent.state import AgentState
from ai_agent.src.agent.prompts.prompt_loader import get_agent_prompt
from ai_agent.src.agent.client.llm_client import get_llm

logger = get_logger(__name__)


def format_research_plan_text(plan: DataResearchPlan) -> str:
    """Formats a DataResearchPlan into clear, descriptive instructions for the researcher agent."""
    lines = [
        f"RESEARCH PLAN OBJECTIVE: {plan.summary_of_intent}",
        "",
        f"TARGET ENTITIES: {', '.join(plan.target_entities) if plan.target_entities else 'None explicitly targeted'}",
        f"RELEVANT KG NODE LABELS: {', '.join(plan.relevant_kg_nodes) if plan.relevant_kg_nodes else 'Vessel, Voyage'}",
        f"RELEVANT RELATIONSHIPS: {', '.join(plan.relevant_relationships) if plan.relevant_relationships else 'OPERATES_VOYAGE'}",
        f"DATA POINTS TO VERIFY: {', '.join(plan.data_points_to_check) if plan.data_points_to_check else 'All operational properties'}",
        "",
        "DETAILED INSTRUCTIONS FOR RESEARCHER AGENT:",
        plan.descriptive_plan
    ]
    return "\n".join(lines)


def planner_node(state: AgentState) -> Dict[str, Any]:
    """
    Data Research Planner Node.
    Takes the user message and normalized entities, feeds Knowledge Graph schema
    information to the LLM, and creates a descriptive planner instructing the
    researcher agent on what data to check.
    """
    user_query = state.get("user_query", "")
    normalized_query = state.get("normalized_query") or user_query
    resolved_entities = state.get("resolved_entities", {})
    logger.info("Executing data research planner for query: '%s'", normalized_query[:60])

    prompt_config = get_agent_prompt("research_planner")
    system_prompt = prompt_config["system"]

    user_prompt = f"""OPERATIONAL CONTEXT:

                        RESOLVED ENTITIES FROM RESOLUTION LAYER:
                        {json.dumps(resolved_entities, indent=2)}

                        USER OPERATIONAL QUERY:
                        {normalized_query}

                        Using the Knowledge Graph schema and operational guidelines provided in the system prompt, generate a descriptive data research plan to instruct the researcher agent on what data, nodes, relationships, and backing records need to be checked to answer this query thoroughly and accurately.
                        """

    llm = get_llm(temperature=1)

    try:
        # The research planner system prompt explicitly instructs:
        # "Output the plan as plain structured text (numbered sections), not JSON."
        # We invoke the LLM directly to obtain the full descriptive research plan,
        # avoiding tool_choice='required' conflicts with providers like Groq.
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ])

        plan_content = response.content if hasattr(response, "content") else str(response)
        if isinstance(plan_content, list):
            plan_content = "\n".join([str(b.get("text", b)) if isinstance(b, dict) else str(b) for b in plan_content])
        descriptive_plan = str(plan_content).strip()

        logger.info("Data research plan successfully generated.")

        return {
            "research_plan": descriptive_plan
        }

    except Exception as e:
        logger.error("Data research planner failed to generate plan: %s", e, exc_info=True)
        # Fallback to descriptive guidance using raw user query and resolved entities
        fallback_plan = (
            f"RESEARCH PLAN (FALLBACK):\n"
            f"Analyze query: '{normalized_query}'.\n"
            f"Check entities: {json.dumps(resolved_entities)} using Maritime Knowledge Graph domain tools.\n"
            f"Use get_voyage_context for voyage/delay issues, get_vessel_context for vessel status, "
            f"get_port_context for congestion, search_incident_history for fault recurrences, "
            f"get_cargo_exposure for containers/bookings, and search_messages for operational communications."
        )
        return {
            "research_plan": fallback_plan
        }


__all__ = [
    "format_research_plan_text",
    "planner_node",
]

