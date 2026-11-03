"""
Researcher agent connected to the Maritime Knowledge Graph MCP server over HTTP.
Uses MCPAdapter to discover and adapt MCP tools for LangChain ReAct agent execution.
"""

import os
from typing import Any, Dict

from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware
from langchain.agents.structured_output import ToolStrategy
from langchain.mcp import MCPAdapter
from langchain_core.messages import HumanMessage, SystemMessage

from ai_agent.src.utilities.logger import get_logger
from ai_agent.src.schemas.researcher_agent_dto import ResearcherResponse
from ai_agent.src.agent.state import AgentState
from ai_agent.src.agent.prompts.prompt_loader import get_agent_prompt
from ai_agent.src.agent.client.llm_client import get_llm


logger = get_logger(__name__)

MCP_SERVER_URL = os.getenv(
    "MARITIME_MCP_SERVER_URL",
    "http://localhost:8000/mcp",
)

_researcher_agent = None


async def build_researcher_agent():
    """Creates a researcher agent using only the read query tool exposed by the maritime MCP server."""
    model = get_llm(temperature=0.0)
    token = os.getenv("MCP_SERVER_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    try:
        if headers:
            try:
                from fastmcp.client.transports import StreamableHttpTransport
                target = StreamableHttpTransport(MCP_SERVER_URL, headers=headers)
            except Exception:
                target = MCP_SERVER_URL
        else:
            target = MCP_SERVER_URL

        async with MCPAdapter(target) as adapter:
            mcp_tools = await adapter.list_tools()
            logger.info("Loaded %d tools from maritime MCP server at %s", len(mcp_tools), MCP_SERVER_URL)
    except Exception as exc:
        logger.error(
            "Failed to connect to maritime MCP server at %s: %s",
            MCP_SERVER_URL,
            exc,
            exc_info=True,
        )
        raise RuntimeError(
            f"Failed to connect to maritime MCP server at {MCP_SERVER_URL}: {exc}"
        ) from exc

    query_tools = [
        t for t in mcp_tools
        if getattr(t, "name", "") == "execute_read_query"
        or "query" in getattr(t, "name", "").lower()
        or "cypher" in getattr(t, "name", "").lower()
    ]

    if not query_tools:
        available_names = [getattr(t, "name", str(t)) for t in mcp_tools]
        raise RuntimeError(
            f"Maritime MCP server at {MCP_SERVER_URL} does not expose a read query tool. "
            f"Discovered tools: {available_names}"
        )

    logger.info("Configured researcher agent with query tool: %s", [t.name for t in query_tools])

    return create_agent(
        model=model,
        tools=query_tools,
        response_format=ToolStrategy(ResearcherResponse),
        middleware=[
            SummarizationMiddleware(
                model=model,
                trigger=("tokens", 6000),
                keep=("messages", 20),
            )
        ],
    )


async def get_researcher_agent():
    """Lazily creates and caches the MCP-connected researcher agent."""
    global _researcher_agent
    if _researcher_agent is None:
        _researcher_agent = await build_researcher_agent()
    return _researcher_agent


async def researcher_node(state: AgentState) -> Dict[str, Any]:
    """Researcher node using maritime MCP tools and structured output."""
    agent = await get_researcher_agent()
    prompt_config = get_agent_prompt("agent_system")
    system_prompt = prompt_config["system"]

    research_plan = state.get("research_plan")
    if research_plan:
        system_prompt += f"""

DATA RESEARCH PLAN (INSTRUCTIONS ON WHAT DATA TO CHECK):
{research_plan}
"""

    normalized_query = (
        state.get("normalized_query") or state.get("user_query", "")
    )
    user_prompt = f"""RESOLVED ENTITIES: {state.get("resolved_entities", {})}
USER QUERY: {normalized_query}
Use the MCP tools to retrieve evidence. Return data_available=false instead of guessing when evidence is insufficient.
"""
    if state.get("validation_feedback"):
        user_prompt += f"""PRIOR VALIDATION FEEDBACK: {state["validation_feedback"]}
Correct the previous issues and ensure every claim is supported by tool results.
"""

    result = await agent.ainvoke(
        {
            "messages": [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]
        }
    )

    researcher_response = result.get("structured_response")
    if not isinstance(researcher_response, ResearcherResponse):
        logger.error("Researcher agent did not return a valid structured response.")
        raise RuntimeError("Researcher agent did not return a valid structured response.")

    previous_queries = state.get("cypher_queries_executed", [])
    agent_queries = getattr(researcher_response, "cypher_queries_executed", None) or []
    all_queries = list(dict.fromkeys(previous_queries + agent_queries))
    if hasattr(researcher_response, "cypher_queries_executed"):
        researcher_response.cypher_queries_executed = all_queries

    return {
        "draft_response": researcher_response,
        "cypher_queries_executed": all_queries,
    }


agent_reasoning_node = researcher_node

__all__ = [
    "MCP_SERVER_URL",
    "build_researcher_agent",
    "get_researcher_agent",
    "researcher_node",
    "agent_reasoning_node",
]
