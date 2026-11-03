"""
Researcher agent connected to the Maritime Knowledge Graph MCP server over HTTP.
Uses MCPAdapter to discover and adapt MCP tools for LangChain ReAct agent execution.
"""

import asyncio
import os
import random
from typing import Any, Dict, Optional

from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware
from langchain.agents.structured_output import ToolStrategy
from langchain.mcp import MCPAdapter
from langchain_core.messages import HumanMessage, SystemMessage

from ai_agent.src.utilities.logger import get_logger
from ai_agent.src.schemas.researcher_agent_dto import NoDataReason, ResearcherResponse
from ai_agent.src.agent.state import AgentState
from ai_agent.src.agent.prompts.prompt_loader import get_agent_prompt
from ai_agent.src.agent.client.llm_client import get_llm


logger = get_logger(__name__)

MCP_SERVER_URL = os.getenv(
    "MARITIME_MCP_SERVER_URL",
    "http://localhost:8000/mcp",
)

# Exclude mutation/write tools and raw query execution to ensure researcher uses domain tools exclusively
EXCLUDED_RESEARCHER_TOOLS = {"create_nodes", "update_nodes", "execute_read_query", "execute_query"}

# Retry & Jitter Configuration
RESEARCHER_MAX_RETRIES = int(os.getenv("RESEARCHER_MAX_RETRIES", "3"))
RESEARCHER_BASE_DELAY = float(os.getenv("RESEARCHER_RETRY_BASE_DELAY", "1.5"))
RESEARCHER_MAX_DELAY = float(os.getenv("RESEARCHER_RETRY_MAX_DELAY", "10.0"))

_researcher_agent = None


async def build_researcher_agent():
    """Creates a researcher agent using the specialized domain tools exposed by the maritime MCP server."""
    model = get_llm()
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

    research_tools = [
        t for t in mcp_tools
        if getattr(t, "name", "") not in EXCLUDED_RESEARCHER_TOOLS
    ]

    if not research_tools:
        available_names = [getattr(t, "name", str(t)) for t in mcp_tools]
        raise RuntimeError(
            f"Maritime MCP server at {MCP_SERVER_URL} does not expose research tools. "
            f"Discovered tools: {available_names}"
        )

    logger.info("Configured researcher agent with %d domain research tools (execute_read_query cut): %s", len(research_tools), [t.name for t in research_tools])

    return create_agent(
        model=model,
        tools=research_tools,
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


def _extract_structured_response(result: Any) -> Optional[ResearcherResponse]:
    """Extracts or parses a ResearcherResponse from an agent execution result."""
    if not isinstance(result, dict):
        return None

    # 1. Direct structured_response attribute
    structured = result.get("structured_response")
    if isinstance(structured, ResearcherResponse):
        return structured
    if isinstance(structured, dict):
        try:
            return ResearcherResponse.model_validate(structured)
        except Exception as exc:
            logger.debug("Failed validating structured_response dict as ResearcherResponse: %s", exc)

    # 2. Inspect messages in reverse for structured tool calls or JSON payload
    messages = result.get("messages", []) or []
    for msg in reversed(messages):
        tool_calls = getattr(msg, "tool_calls", None) or []
        for tc in tool_calls:
            tc_name = tc.get("name", "")
            if tc_name.lower() in ("researcherresponse", "response_format", "final_response"):
                args = tc.get("args") or {}
                if isinstance(args, dict):
                    try:
                        return ResearcherResponse.model_validate(args)
                    except Exception as exc:
                        logger.debug("Failed validating tool_call args as ResearcherResponse: %s", exc)

        content = getattr(msg, "content", None)
        if isinstance(content, str):
            content_str = content.strip()
            if content_str.startswith("{") and "data_available" in content_str:
                try:
                    return ResearcherResponse.model_validate_json(content_str)
                except Exception as exc:
                    logger.debug("Failed validating message JSON content as ResearcherResponse: %s", exc)

    return None


async def researcher_node(state: AgentState) -> Dict[str, Any]:
    """
    Researcher node using maritime MCP domain tools and structured output.
    Includes exponential backoff with full jitter on failures to avoid 500 crashes.
    """
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

CRITICAL OPERATIONAL EXTRACTION RULES:
1. EXHAUSTIVE RECORDING MANDATE: Never miss, drop, or omit available operational information returned by the tools.
   - UNVERIFIED REPORTS: If ANY incident in the tool output has status 'Reported', 'Under review', or 'Dismissed', OR if any T3/T4 communication, crew WhatsApp/relay, or pending claim appears, you MUST record it in `unverified_reports`. NEVER omit unverified reports simply because confirmed facts exist or because an incident was dismissed.
   - CONFIRMED FACTS: Record all verified ground truth, official timestamps, port calls, and T1/T2 communications in `confirmed_facts`.
   - SYSTEM INFERENCES: Record all calculations (delay reconciliations, berth-window margins, forward projections) in `system_inferences` with a clear rationale.
2. CITATION MANDATE: Extract citations directly from the tool's CITABLE list: [{{"node": "<label>", "id": "<primary_id>"}}].
3. NO FABRICATION: If evidence is truly absent, set data_available=false instead of guessing.
"""
    if state.get("validation_feedback"):
        user_prompt += f"""PRIOR VALIDATION FEEDBACK: {state["validation_feedback"]}
Correct the previous issues and ensure every claim is supported by tool results.
"""

    researcher_response: Optional[ResearcherResponse] = None
    last_error: Optional[Exception] = None

    for attempt in range(RESEARCHER_MAX_RETRIES):
        try:
            logger.info("Executing researcher agent invocation attempt %d/%d...", attempt + 1, RESEARCHER_MAX_RETRIES)
            result = await agent.ainvoke(
                {
                    "messages": [
                        SystemMessage(content=system_prompt),
                        HumanMessage(content=user_prompt),
                    ]
                }
            )
            researcher_response = _extract_structured_response(result)
            if researcher_response is not None:
                logger.info("Researcher agent successfully returned valid structured response on attempt %d.", attempt + 1)
                break

            logger.warning(
                "Researcher attempt %d/%d did not return a valid structured response.",
                attempt + 1,
                RESEARCHER_MAX_RETRIES,
            )
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Researcher attempt %d/%d failed with exception: %s",
                attempt + 1,
                RESEARCHER_MAX_RETRIES,
                exc,
                exc_info=True,
            )

        if attempt < RESEARCHER_MAX_RETRIES - 1:
            # Full jitter exponential backoff: delay = uniform(0.5, 1.5) * min(MAX_DELAY, BASE_DELAY * (2 ** attempt))
            cap = min(RESEARCHER_MAX_DELAY, RESEARCHER_BASE_DELAY * (2 ** attempt))
            jitter = random.uniform(0.5, 1.5)
            delay = round(cap * jitter, 2)
            logger.info(
                "Waiting %.2fs with jitter before retry %d/%d for researcher agent...",
                delay,
                attempt + 2,
                RESEARCHER_MAX_RETRIES,
            )
            await asyncio.sleep(delay)

    # If all retries exhausted without a structured response, do not crash with RuntimeError.
    # Fall back gracefully to an evidence-based DATA_UNAVAILABLE response.
    if researcher_response is None:
        logger.error(
            "Researcher agent exhausted %d retries without structured response (last error: %s). "
            "Gracefully falling back to DATA_UNAVAILABLE state instead of raising error.",
            RESEARCHER_MAX_RETRIES,
            last_error,
        )
        researcher_response = ResearcherResponse(
            data_available=False,
            no_data_reason=NoDataReason.DATA_SOURCE_ERROR,
            no_data_explanation=(
                f"The researcher agent was unable to extract a verified structured response "
                f"from domain tools after {RESEARCHER_MAX_RETRIES} attempts with exponential backoff and jitter."
            ),
            summary=(
                "Operational intelligence is temporarily unavailable for this query. "
                "Repeated attempts to retrieve and structure knowledge graph evidence encountered transient timeouts or format limits. "
                "Please retry or rephrase your inquiry."
            ),
            confirmed_facts=[],
            unverified_reports=[],
            system_inferences=[],
        )

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
    "EXCLUDED_RESEARCHER_TOOLS",
    "MCP_SERVER_URL",
    "RESEARCHER_MAX_RETRIES",
    "RESEARCHER_BASE_DELAY",
    "RESEARCHER_MAX_DELAY",
    "build_researcher_agent",
    "get_researcher_agent",
    "researcher_node",
    "agent_reasoning_node",
]
