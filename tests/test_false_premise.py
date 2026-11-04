"""
Tests for the false_premises field: researcher model validation, citation collection,
and hydration into a FALSE_PREMISE final response.
"""

import pytest
from pydantic import ValidationError

from ai_agent.src.agent.nodes.reviewer_node import _extract_all_citations, _hydrate_maritime_response
from ai_agent.src.schemas.researcher_agent_dto import (
    Citation,
    ConfirmedFact,
    FalsePremise,
    NoDataReason,
    ResearcherResponse,
)

PREMISE = FalsePremise(
    user_assumption="MV Blue Horizon was delayed at Hamburg last month.",
    grounded_reality="Blue Horizon called at Antwerp (VG-0997) on schedule; it had no Hamburg call.",
    citations=[Citation(node="Voyage", id="VG-0997"), Citation(node="PortCall", id="PC-7008")],
)


def answerable(**overrides) -> ResearcherResponse:
    data = dict(
        data_available=True,
        summary="Blue Horizon was not delayed at Hamburg; it called at Antwerp on schedule.",
        confirmed_facts=[ConfirmedFact(fact="VG-0997 berthed at Antwerp with 0 h delay.", citations=[Citation(node="Voyage", id="VG-0997")])],
    )
    data.update(overrides)
    return ResearcherResponse(**data)


def test_false_premises_default_to_empty():
    assert answerable().false_premises == []


def test_false_premises_allowed_when_data_available():
    assert answerable(false_premises=[PREMISE]).false_premises[0].user_assumption.startswith("MV Blue Horizon")


def test_false_premises_rejected_when_data_unavailable():
    with pytest.raises(ValidationError, match="false_premises must be empty"):
        ResearcherResponse(
            data_available=False,
            no_data_reason=NoDataReason.NO_MATCHING_DATA,
            no_data_explanation="nothing found",
            summary="No data.",
            false_premises=[PREMISE],
        )


def test_false_premise_citations_are_collected_for_database_verification():
    citations = _extract_all_citations(answerable(false_premises=[PREMISE]))
    assert {"node": "PortCall", "id": "PC-7008"} in citations
    assert {"node": "Voyage", "id": "VG-0997"} in citations


def test_hydration_sets_false_premise_status():
    final = _hydrate_maritime_response(answerable(false_premises=[PREMISE]), {"nodes": {}})
    assert final.status == "FALSE_PREMISE"
    assert len(final.false_premises_detected) == 1
    detected = final.false_premises_detected[0]
    assert detected.user_assumption == PREMISE.user_assumption
    assert detected.grounded_reality == PREMISE.grounded_reality
    assert detected.citations == ["VG-0997", "PC-7008"]  # bare ids, so the UI can resolve them like other chips
    assert final.executive_summary == answerable().summary


def test_hydration_without_false_premise_stays_success():
    final = _hydrate_maritime_response(answerable(), {"nodes": {}})
    assert final.status == "SUCCESS"
    assert final.false_premises_detected == []
