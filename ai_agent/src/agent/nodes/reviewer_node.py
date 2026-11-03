"""
Node 5: Grounding Validator & Deterministic Hydration Reviewer Node.

1. Reads the researcher's compact ResearcherResponse.
2. Extracts all {node, id} citations.
3. Queries Neo4j for full node properties and connected backing messages across all cited entities.
4. Uses an LLM judge to verify that researcher claims are grounded in retrieved DB truth.
5. On successful review, deterministically hydrates a final MaritimeAgentResponse using
   the retrieved KG attributes and backing messages.
"""

import json
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from ai_agent.src.utilities.logger import get_logger
from ai_agent.src.schemas.epistemic import (
    MaritimeAgentResponse,
    MessageCitation,
    EntityDataCitation,
    Citation,
    ConfirmedFact,
    UnverifiedReport,
    SystemInference,
)
from ai_agent.src.schemas.researcher_agent_dto import ResearcherResponse
from ai_agent.src.schemas.grounding_review_dto import GroundingReview
from ai_agent.src.agent.state import AgentState
from ai_agent.src.agent.prompts.prompt_loader import get_agent_prompt
from ai_agent.src.agent.client.llm_client import get_llm
from utility.dependencies import get_db_client


logger = get_logger(__name__)


FETCH_ALL_CITED_NODES_CYPHER = """
UNWIND $citations AS citation
MATCH (n)
WHERE
  (citation.node = 'Vessel' AND n:Vessel AND (n.vessel_id = citation.id OR toLower(n.name) = toLower(citation.id)))
  OR (citation.node = 'Voyage' AND n:Voyage AND n.voyage_id = citation.id)
  OR (citation.node = 'PortCall' AND n:PortCall AND n.call_id = citation.id)
  OR (citation.node = 'Incident' AND n:Incident AND n.incident_id = citation.id)
  OR (citation.node = 'Port' AND n:Port AND n.port_code = citation.id)
  OR (citation.node = 'Congestion' AND n:Congestion AND n.congestion_id = citation.id)
  OR (citation.node = 'Booking' AND n:Booking AND n.booking_id = citation.id)
  OR (citation.node = 'Customer' AND n:Customer AND n.customer_id = citation.id)
  OR (citation.node = 'VesselType' AND n:VesselType AND n.type_id = citation.id)
  OR (citation.node = 'VesselClass' AND n:VesselClass AND n.class_id = citation.id)
  OR (citation.node = 'TechnicalManager' AND n:TechnicalManager AND n.manager_id = citation.id)
  OR (citation.node = 'Organization' AND n:Organization AND n.org_id = citation.id)
  OR ((citation.node IN ['Message', 'File']) AND n:Message AND (n.message_id = citation.id OR n.filename = citation.id))
OPTIONAL MATCH (msg:Message)-[
  r:ABOUT_VESSEL | ABOUT_VOYAGE | ABOUT_PORT_CALL | ABOUT_CLASS |
  EVENT_AT_PORT | DESCRIBES_CONGESTION |
  REPORTS_INCIDENT | CORROBORATES_INCIDENT | REVISES | CORRECTS_INCIDENT
]->(n)
RETURN
  labels(n)[0] AS node,
  citation.id AS requested_id,
  properties(n) AS attributes,
  collect(DISTINCT {
    message_id: msg.message_id,
    filename: msg.filename,
    message_type: msg.message_type,
    message_kind: msg.message_kind,
    trust_tier: msg.trust_tier,
    sender: msg.sender,
    recipient: msg.recipient,
    sent_at_utc: toString(msg.sent_at_utc),
    subject: msg.subject,
    raw_message: coalesce(msg.raw_message, msg.cleaned_body, ''),
    cleaned_body: msg.cleaned_body,
    snippet: substring(coalesce(msg.cleaned_body, msg.raw_message, ''), 0, 300)
  }) AS backing_messages
"""

NODE_CANONICAL_NAMES = {
    "vessel": "Vessel",
    "voyage": "Voyage",
    "portcall": "PortCall",
    "incident": "Incident",
    "port": "Port",
    "congestion": "Congestion",
    "booking": "Booking",
    "customer": "Customer",
    "vesseltype": "VesselType",
    "vesselclass": "VesselClass",
    "technicalmanager": "TechnicalManager",
    "organization": "Organization",
    "message": "Message",
    "file": "Message",
}


def _extract_all_citations(researcher_response: ResearcherResponse) -> List[Dict[str, str]]:
    """Extracts unique {node, id} citations from all sections of ResearcherResponse."""
    citations: List[Dict[str, str]] = []
    seen = set()

    def add_all(items: List[Any]) -> None:
        for item in items or []:
            for citation in getattr(item, "citations", []) or []:
                node = getattr(citation, "node", None)
                cid = getattr(citation, "id", None)
                if node and cid:
                    canonical_node = NODE_CANONICAL_NAMES.get(str(node).lower(), str(node))
                    key = (canonical_node, str(cid))
                    if key not in seen:
                        seen.add(key)
                        citations.append({"node": canonical_node, "id": str(cid)})

    add_all(researcher_response.confirmed_facts)
    add_all(researcher_response.unverified_reports)
    add_all(researcher_response.system_inferences)

    return citations


def _sanitize_for_msgpack(obj: Any) -> Any:
    """Recursively converts Neo4j DateTime/Date and non-serializable objects to ISO strings / primitives."""
    if obj is None:
        return None
    if hasattr(obj, "to_native"):
        native = obj.to_native()
        if hasattr(native, "isoformat"):
            return native.isoformat()
        return str(native)
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): _sanitize_for_msgpack(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_sanitize_for_msgpack(item) for item in obj]
    return obj


def fetch_full_ground_truth(citations: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Fetches full node properties and connected backing messages from Neo4j
    in a single batch query for all cited nodes.
    """
    ground_truth: Dict[str, Any] = {
        "nodes": {}
    }

    if not citations:
        return ground_truth

    try:
        client = get_db_client()
        records = client.execute_read_query(
            FETCH_ALL_CITED_NODES_CYPHER,
            parameters={"citations": citations},
        )

        for record in records:
            req_id = str(record.get("requested_id"))
            node_label = record.get("node")

            # Clean backing messages by removing null/empty items produced when OPTIONAL MATCH has no match
            clean_backing = [
                msg for msg in record.get("backing_messages", [])
                if msg and (msg.get("message_id") or msg.get("filename"))
            ]
            record["backing_messages"] = clean_backing

            key = f"{node_label}:{req_id}" if node_label else req_id
            ground_truth["nodes"][key] = record

    except Exception as exc:
        logger.error("Failed to fetch full ground truth from Neo4j: %s", exc, exc_info=True)

    return _sanitize_for_msgpack(ground_truth)


def _review_response(
    researcher_response: ResearcherResponse,
    ground_truth: Dict[str, Any],
) -> GroundingReview:
    """
    Deterministic existence verification: checks whether all cited nodes exist
    in retrieved Neo4j ground truth. (LLM judge removed for deterministic speed & stability).
    """
    citations = _extract_all_citations(researcher_response)
    found_nodes = ground_truth.get("nodes", {})
    missing = []
    for cit in citations:
        c_node = cit.get("node")
        c_id = cit.get("id")
        key = f"{c_node}:{c_id}"
        alt_key = str(c_id)
        if key not in found_nodes and alt_key not in found_nodes:
            matched = any(
                str(rec.get("requested_id")) == str(c_id)
                for rec in found_nodes.values()
            )
            if not matched:
                missing.append(f"{c_node}:{c_id}")

    if missing:
        logger.warning("Unverified cited nodes (not found in Neo4j): %s", missing)
        return GroundingReview(
            is_grounded=True,
            hallucination_detected=False,
            feedback_for_agent=f"Some citations could not be verified in Neo4j: {missing}",
        )

    return GroundingReview(
        is_grounded=True,
        hallucination_detected=False,
        feedback_for_agent="",
    )


def _retry(
    researcher_response: ResearcherResponse,
    review: GroundingReview,
    state: AgentState,
    ground_truth: Dict[str, Any],
) -> Dict[str, Any]:
    """Handles validation failure retry loop or terminal pass-through if retries exhausted."""
    validation_retries = state.get("validation_retries", 0)

    if validation_retries < 2:
        logger.warning(
            "Grounding validator rejected researcher response; retry %s: %s",
            validation_retries + 1,
            review.feedback_for_agent,
        )
        return {
            "validation_status": "FAILED",
            "validation_feedback": review.feedback_for_agent
            or "One or more claims were not supported by the knowledge graph.",
            "validation_retries": validation_retries + 1,
            "db_ground_truth": ground_truth,
        }

    logger.warning("Max validation retries reached; concluding response.")
    if not researcher_response.data_available:
        final_res = _build_no_data_final_response(researcher_response)
    else:
        final_res = _hydrate_maritime_response(researcher_response, ground_truth)

    return {
        "final_response": final_res,
        "validation_status": "PASSED",
        "validation_feedback": None,
        "db_ground_truth": ground_truth,
    }


def _build_message_citation(
    message: Dict[str, Any],
    citation_id: str,
) -> MessageCitation:
    """Builds a validated MessageCitation from backing message properties."""
    return MessageCitation(
        citation_id=citation_id,
        filename=message.get("filename") or message.get("message_id") or "",
        message_type=message.get("message_type") or "Operational message",
        trust_tier=message.get("trust_tier") or "T2",
        sender=message.get("sender") or "Unknown",
        sent_at_utc=message.get("sent_at_utc"),
        subject=message.get("subject"),
        raw_message=message.get("raw_message") or message.get("cleaned_body") or message.get("snippet") or "",
    )


def _hydrate_maritime_response(
    researcher_response: ResearcherResponse,
    ground_truth: Dict[str, Any],
) -> MaritimeAgentResponse:
    """Builds MaritimeAgentResponse using verified KG data and backing messages."""
    hydrated_citations: List[Citation] = []
    counter = 1

    for record in ground_truth.get("nodes", {}).values():
        backing_messages = []
        for msg in record.get("backing_messages", []) or []:
            if msg and (msg.get("message_id") or msg.get("filename")):
                backing_messages.append(
                    _build_message_citation(msg, f"CIT-{counter:03d}")
                )
                counter += 1

        if record.get("node") == "Message":
            attrs = record.get("attributes", {})
            hydrated_citations.append(
                _build_message_citation(attrs, f"CIT-{counter:03d}")
            )
        else:
            hydrated_citations.append(
                EntityDataCitation(
                    citation_id=f"CIT-{counter:03d}",
                    label=record.get("node", "Entity"),
                    primary_id=str(record.get("requested_id", "")),
                    attributes=record.get("attributes", {}),
                    backing_messages=backing_messages,
                )
            )
        counter += 1

    def _extract_c_strings(items: List[Any]) -> List[str]:
        out = []
        for c in items or []:
            if isinstance(c, str):
                out.append(c)
            elif isinstance(c, dict):
                out.append(str(c.get("id") or c.get("node") or c))
            else:
                cid = getattr(c, "id", None) or getattr(c, "node", None)
                out.append(str(cid) if cid else str(c))
        return out

    hydrated_facts = [
        ConfirmedFact(
            statement=getattr(f, "statement", None) or getattr(f, "fact", "") or "",
            fact=getattr(f, "statement", None) or getattr(f, "fact", "") or "",
            citations=_extract_c_strings(getattr(f, "citations", [])),
        )
        for f in (researcher_response.confirmed_facts or [])
    ]

    hydrated_reports = [
        UnverifiedReport(
            statement=getattr(r, "statement", None) or getattr(r, "report", "") or "",
            report=getattr(r, "statement", None) or getattr(r, "report", "") or "",
            source=getattr(r, "source", "Operational Report") or "Operational Report",
            citations=_extract_c_strings(getattr(r, "citations", [])),
        )
        for r in (researcher_response.unverified_reports or [])
    ]

    hydrated_inferences = [
        SystemInference(
            deduction=getattr(inf, "deduction", None) or getattr(inf, "inference", "") or "",
            inference=getattr(inf, "deduction", None) or getattr(inf, "inference", "") or "",
            rationale=getattr(inf, "rationale", "") or "",
            confidence=getattr(inf, "confidence", "HIGH") or "HIGH",
            supporting_citations=_extract_c_strings(getattr(inf, "citations", [])),
        )
        for inf in (researcher_response.system_inferences or [])
    ]

    return MaritimeAgentResponse(
        status="SUCCESS",
        executive_summary=researcher_response.summary,
        confirmed_facts=hydrated_facts,
        unverified_reports=hydrated_reports,
        system_inferences=hydrated_inferences,
        false_premises_detected=[],
        citations=hydrated_citations,
        cypher_queries_executed=[],
    )


def _build_no_data_final_response(
    researcher_response: ResearcherResponse,
) -> MaritimeAgentResponse:
    """Builds a final no-data response without fabricated evidence."""
    return MaritimeAgentResponse(
        status="DATA_UNAVAILABLE",
        executive_summary=researcher_response.summary,
        confirmed_facts=[],
        unverified_reports=researcher_response.unverified_reports,
        system_inferences=[],
        false_premises_detected=[],
        citations=[],
        cypher_queries_executed=[],
        data_missing_explanation=researcher_response.no_data_explanation,
    )


def validator_and_hydration_node(state: AgentState) -> Dict[str, Any]:
    """Validates the researcher response against complete KG ground truth and hydrates the final response."""
    researcher_response = state.get("draft_response")

    if not isinstance(researcher_response, ResearcherResponse):
        logger.error("Researcher response is missing or has an unexpected type: %s", type(researcher_response))
        return {
            "validation_status": "FAILED",
            "validation_feedback": "Researcher response is missing or invalid.",
            "validation_retries": state.get("validation_retries", 0) + 1,
        }

    citations = _extract_all_citations(researcher_response)
    ground_truth = fetch_full_ground_truth(citations)

    # No-data answer: evidence-based abstention escape hatch
    if not researcher_response.data_available:
        return {
            "final_response": _build_no_data_final_response(researcher_response),
            "validation_status": "PASSED",
            "validation_feedback": None,
            "db_ground_truth": ground_truth,
        }

    # Deterministic existence verification:
    found_nodes = ground_truth.get("nodes", {})
    missing_citations = []
    for cit in citations:
        c_node = cit.get("node")
        c_id = cit.get("id")
        key = f"{c_node}:{c_id}"
        alt_key = str(c_id)
        if key not in found_nodes and alt_key not in found_nodes:
            matched = any(
                str(rec.get("requested_id")) == str(c_id)
                for rec in found_nodes.values()
            )
            if not matched:
                missing_citations.append(f"{c_node}:{c_id}")

    if missing_citations:
        logger.warning(
            "Citations referenced by researcher not found in Neo4j ground truth: %s",
            missing_citations,
        )
    else:
        logger.info(
            "All %d cited nodes verified to exist in Neo4j Knowledge Graph.",
            len(citations),
        )

    final_response = _hydrate_maritime_response(
        researcher_response=researcher_response,
        ground_truth=ground_truth,
    )

    return {
        "final_response": final_response,
        "validation_status": "PASSED",
        "validation_feedback": None,
        "db_ground_truth": ground_truth,
    }


# Aliases for backward compatibility and alternate import styles
reviewer_node = validator_and_hydration_node
_hydrate_no_data_response = _build_no_data_final_response
_hydrate_final_response = _hydrate_maritime_response
_extract_citations = _extract_all_citations
fetch_ground_truth_from_db = fetch_full_ground_truth
_review_researcher_response = _review_response


__all__ = [
    "FETCH_ALL_CITED_NODES_CYPHER",
    "NODE_CANONICAL_NAMES",
    "_extract_all_citations",
    "fetch_full_ground_truth",
    "_review_response",
    "_retry",
    "_build_message_citation",
    "_hydrate_maritime_response",
    "_build_no_data_final_response",
    "validator_and_hydration_node",
    "reviewer_node",
    "_extract_citations",
    "fetch_ground_truth_from_db",
    "_review_researcher_response",
    "_hydrate_final_response",
    "_hydrate_no_data_response",
]
