"""
Unit tests for AI Agent System Prompts, Prompt Loader, and Agent Node integration.
"""

import os
os.environ["LANGCHAIN_TRACING_V2"] = "false"

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from ai_agent.src.agent.prompts.prompt_loader import load_agent_prompts, get_agent_prompt
from ai_agent.src.agent.nodes.planner_node import planner_node, format_research_plan_text
from ai_agent.src.schemas.planner_dto import DataResearchPlan
from ai_agent.src.agent.state import AgentState


def test_prompt_loader_all_sections():
    """Verify that all prompt sections in agent_prompts.yaml are loaded and valid."""
    prompts = load_agent_prompts(reload=True)
    required_sections = [
        "input_guardrail",
        "entity_resolution",
        "research_planner",
        "agent_system",
        "output_guardrail",
        "grounding_validator",
        "conversation_summarizer",
    ]
    for section in required_sections:
        assert section in prompts, f"Missing section: {section}"
        section_data = get_agent_prompt(section)
        assert "system" in section_data, f"Section {section} missing 'system' key"
        assert len(section_data["system"]) > 50, f"Section {section} content too short"


def test_research_planner_system_prompt_domain_tools():
    """Verify research_planner system prompt contains instructions for the domain tools and excludes execute_read_query."""
    prompt = get_agent_prompt("research_planner")["system"]
    
    expected_tools = [
        "get_voyage_context",
        "get_vessel_context",
        "scan_voyages",
        "get_port_context",
        "search_incident_history",
        "get_cargo_exposure",
        "track_booking",
        "search_messages",
        "get_knowledge_graph_schema",
    ]
    for tool in expected_tools:
        assert tool in prompt, f"Expected domain tool {tool} in research_planner prompt"

    assert "execute_read_query is cut" in prompt

    assert "2026-10-26 12:00 UTC" in prompt or "2026-10-26 12:00:00Z" in prompt
    assert "CONFIRMED FACTS" in prompt
    assert "UNVERIFIED REPORTS" in prompt
    assert "SYSTEM INFERENCES" in prompt


def test_agent_system_prompt_domain_tools():
    """Verify agent_system system prompt contains domain tools inventory, excludes execute_read_query, and defines epistemic rules."""
    prompt = get_agent_prompt("agent_system")["system"]
    
    expected_tools = [
        "get_voyage_context",
        "get_vessel_context",
        "scan_voyages",
        "get_port_context",
        "search_incident_history",
        "get_cargo_exposure",
        "track_booking",
        "search_messages",
        "get_knowledge_graph_schema",
    ]
    for tool in expected_tools:
        assert tool in prompt, f"Expected domain tool {tool} in agent_system prompt"

    assert "execute_read_query" in prompt
    assert "cut" in prompt.lower()
    assert "CITABLE" in prompt
    assert "CONFIRMED FACTS" in prompt or "Confirmed Facts" in prompt
    assert "UNVERIFIED REPORTS" in prompt or "Unverified Reports" in prompt
    assert "SYSTEM INFERENCES" in prompt or "System Inferences" in prompt


def test_format_research_plan_text():
    """Verify formatting of DataResearchPlan object."""
    plan = DataResearchPlan(
        summary_of_intent="Investigate delay for MV Ocean Star",
        target_entities=["V001", "VG-1042"],
        relevant_kg_nodes=["Vessel", "Voyage", "Incident"],
        relevant_relationships=["OPERATES_VOYAGE", "EXPERIENCED_INCIDENT"],
        data_points_to_check=["revised_eta_utc", "recorded_delay_hours"],
        descriptive_plan="1. Call get_voyage_context(voyage_id='VG-1042').\n2. Reconcile delays.",
    )
    text = format_research_plan_text(plan)
    assert "RESEARCH PLAN OBJECTIVE: Investigate delay for MV Ocean Star" in text
    assert "TARGET ENTITIES: V001, VG-1042" in text
    assert "1. Call get_voyage_context(voyage_id='VG-1042')" in text


@patch("ai_agent.src.agent.nodes.planner_node.get_llm")
def test_planner_node_success(mock_get_llm):
    """Verify planner_node invokes LLM and produces plan with domain tool guidance."""
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(
        content="1. Query Intent: Assess delay.\n2. Target: VG-1042.\n3. Plan: Call get_voyage_context."
    )
    mock_get_llm.return_value = mock_llm

    state: AgentState = {
        "user_query": "Why is VG-1042 delayed?",
        "normalized_query": "Why is voyage VG-1042 delayed?",
        "resolved_entities": {"voyage_id": "VG-1042", "vessel_id": "V001"},
    }

    result = planner_node(state)
    assert "research_plan" in result
    assert "Call get_voyage_context" in result["research_plan"]


@patch("ai_agent.src.agent.nodes.planner_node.get_llm")
def test_planner_node_fallback(mock_get_llm):
    """Verify planner_node fallback includes domain tools when LLM raises exception."""
    mock_llm = MagicMock()
    mock_llm.invoke.side_effect = RuntimeError("LLM connection error")
    mock_get_llm.return_value = mock_llm

    state: AgentState = {
        "user_query": "Why is VG-1042 delayed?",
        "normalized_query": "Why is voyage VG-1042 delayed?",
        "resolved_entities": {"voyage_id": "VG-1042"},
    }

    result = planner_node(state)
    assert "research_plan" in result
    plan = result["research_plan"]
    assert "RESEARCH PLAN (FALLBACK):" in plan
    assert "get_voyage_context" in plan
    assert "get_vessel_context" in plan


def test_researcher_agent_excludes_execute_query():
    """Verify that EXCLUDED_RESEARCHER_TOOLS cuts execute_read_query, execute_query, and write tools."""
    from ai_agent.src.agent.nodes.researcher_node import EXCLUDED_RESEARCHER_TOOLS

    assert "execute_read_query" in EXCLUDED_RESEARCHER_TOOLS
    assert "execute_query" in EXCLUDED_RESEARCHER_TOOLS
    assert "create_nodes" in EXCLUDED_RESEARCHER_TOOLS
    assert "update_nodes" in EXCLUDED_RESEARCHER_TOOLS

    # Verify tool filtering
    all_tool_names = [
        "execute_read_query",
        "execute_query",
        "create_nodes",
        "update_nodes",
        "get_voyage_context",
        "get_vessel_context",
        "scan_voyages",
        "get_port_context",
        "search_incident_history",
        "get_cargo_exposure",
        "track_booking",
        "search_messages",
        "get_knowledge_graph_schema",
    ]
    mock_tools = [MagicMock(name=n) for n in all_tool_names]
    for m, n in zip(mock_tools, all_tool_names):
        m.name = n

    filtered_tools = [t for t in mock_tools if getattr(t, "name", "") not in EXCLUDED_RESEARCHER_TOOLS]
    filtered_names = [t.name for t in filtered_tools]

    assert "execute_read_query" not in filtered_names
    assert "execute_query" not in filtered_names
    assert "create_nodes" not in filtered_names
    assert "update_nodes" not in filtered_names
    assert "get_voyage_context" in filtered_names
    assert "search_messages" in filtered_names
    assert len(filtered_names) == 9


def test_extract_structured_response_variants():
    """Verify that _extract_structured_response handles direct, dict, tool_calls, and JSON."""
    from ai_agent.src.agent.nodes.researcher_node import _extract_structured_response
    from ai_agent.src.schemas.researcher_agent_dto import ResearcherResponse, NoDataReason
    from langchain_core.messages import AIMessage

    # Direct instance
    res1 = ResearcherResponse(
        data_available=False,
        no_data_reason=NoDataReason.NO_MATCHING_DATA,
        no_data_explanation="Nothing found",
        summary="No data found.",
    )
    assert _extract_structured_response({"structured_response": res1}) == res1

    # Dict format
    res2_dict = {
        "data_available": False,
        "no_data_reason": "NO_MATCHING_DATA",
        "no_data_explanation": "Dict test",
        "summary": "No data found.",
    }
    extracted2 = _extract_structured_response({"structured_response": res2_dict})
    assert isinstance(extracted2, ResearcherResponse)
    assert extracted2.no_data_explanation == "Dict test"

    # From tool_calls in message
    msg = AIMessage(
        content="",
        tool_calls=[{
            "id": "call_123",
            "name": "ResearcherResponse",
            "args": res2_dict,
        }]
    )
    extracted3 = _extract_structured_response({"messages": [msg]})
    assert isinstance(extracted3, ResearcherResponse)
    assert extracted3.no_data_explanation == "Dict test"


def test_researcher_fallback_response_structure():
    """Verify that ResearcherResponse fallback model has required epistemic sections and DATA_SOURCE_ERROR status."""
    from ai_agent.src.schemas.researcher_agent_dto import ResearcherResponse, NoDataReason

    fallback = ResearcherResponse(
        data_available=False,
        no_data_reason=NoDataReason.DATA_SOURCE_ERROR,
        no_data_explanation="The researcher agent was unable to extract a verified structured response from domain tools.",
        summary="Operational intelligence is temporarily unavailable for this query.",
        confirmed_facts=[],
        unverified_reports=[],
        system_inferences=[],
    )

    assert fallback.data_available is False
    assert fallback.no_data_reason == NoDataReason.DATA_SOURCE_ERROR
    assert "temporarily unavailable" in fallback.summary
    assert fallback.confirmed_facts == []
    assert fallback.unverified_reports == []
    assert fallback.system_inferences == []



