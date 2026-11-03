"""Message intelligence tools for Maritime Knowledge Graph MCP server.
Provides search_messages: searches and inspects unstructured communications
(noon reports, agent emails, technical bulletins, etc.) by text query, message ID,
or filename, with automatic suppression of malicious payloads.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from utility.dependencies import DatabaseClientProtocol
from utility.logger import get_logger
from knowledge_graph.maritime_kg_mcp.models import (
    MessageHit,
    MessageLink,
    MessageNode,
    SearchMessagesInput,
    SearchMessagesResult,
    ToolResponse,
)
from knowledge_graph.maritime_kg_mcp.renderer import (
    render_ambiguous,
    render_no_data,
    render_search_messages,
)
from knowledge_graph.maritime_kg_mcp.resolver import resolve_port, resolve_vessel

logger = get_logger(__name__)


def search_messages(
    client: DatabaseClientProtocol, args: SearchMessagesInput
) -> ToolResponse:
    """Searches and inspects operational communications across trust tiers, kinds, and connected entities."""
    # Resolve vessel / port if provided
    vessel_id: Optional[str] = None
    if args.vessel:
        v_node, amb = resolve_vessel(client, args.vessel)
        if amb:
            return render_ambiguous(amb)
        if v_node:
            vessel_id = v_node.vessel_id

    port_code: Optional[str] = None
    if args.port:
        p_node, p_amb = resolve_port(client, args.port)
        if p_amb:
            return render_ambiguous(p_amb)
        if p_node:
            port_code = p_node.port_code

    start_iso = args.window.start_utc.isoformat() if args.window else None
    end_iso = args.window.end_utc.isoformat() if args.window else None

    # Check if this is a targeted lookup by message ID or filename
    is_targeted = bool(args.message_id or args.filename)

    cypher = """
    MATCH (m:Message)
    WHERE ($msg_id IS NULL OR m.message_id = $msg_id OR toLower(m.message_id) = toLower($msg_id))
      AND ($filename IS NULL OR m.filename = $filename OR toLower(m.filename) = toLower($filename))
      AND ($query IS NULL
           OR toLower(m.subject) CONTAINS toLower($query)
           OR toLower(coalesce(m.cleaned_body, '')) CONTAINS toLower($query))
      AND ($voyage_id IS NULL OR EXISTS { (m)-[:ABOUT_VOYAGE|REFERENCES_VOYAGE]->(:Voyage {voyage_id: $voyage_id}) })
      AND ($vessel_id IS NULL OR EXISTS { (m)-[:SENT_BY_VESSEL|ABOUT_VESSEL|REFERENCES_VESSEL]->(:Vessel {vessel_id: $vessel_id}) })
      AND ($port_code IS NULL OR EXISTS { (m)-[:EVENT_AT_PORT|REFERENCES_PORT|DESCRIBES_CONGESTION]->(:Port {port_code: $port_code}) })
      AND ($incident_id IS NULL OR EXISTS { (m)-[:REPORTS_INCIDENT|CORROBORATES_INCIDENT|REVISES|CORRECTS_INCIDENT]->(:Incident {incident_id: $incident_id}) })
      AND (size($kinds) = 0 OR m.message_kind IN $kinds)
      AND (size($tiers) = 0 OR m.trust_tier IN $tiers)
      AND ($start_iso IS NULL OR m.sent_at_utc >= datetime($start_iso))
      AND ($end_iso IS NULL OR m.sent_at_utc <= datetime($end_iso))
      AND ($include_post OR m.sent_at_utc <= datetime('2026-10-26T12:00:00Z'))
    OPTIONAL MATCH (m)-[r]->(target)
    WITH m, collect(DISTINCT {
        edge_type: type(r),
        target_label: labels(target)[0],
        target_key: coalesce(target.vessel_id, target.voyage_id, target.port_code, target.incident_id, target.booking_id, target.name, '')
    }) AS edges_data
    ORDER BY m.sent_at_utc DESC
    LIMIT $limit
    RETURN m.message_id AS message_id,
           m.filename AS filename,
           m.message_type AS message_type,
           m.message_kind AS message_kind,
           m.trust_tier AS trust_tier,
           m.sender AS sender,
           m.sent_at_utc AS sent_at_utc,
           m.subject AS subject,
           substring(coalesce(m.cleaned_body, m.raw_message, ''), 0, 300) AS snippet,
           m.cleaned_body AS cleaned_body,
           m.raw_message AS raw_message,
           coalesce(m.is_malicious, false) AS is_malicious,
           coalesce(m.in_snapshot, true) AS in_snapshot,
           edges_data
    """
    records = client.execute_read_query(cypher, {
        "msg_id": args.message_id,
        "filename": args.filename,
        "query": args.query,
        "voyage_id": args.voyage_id,
        "vessel_id": vessel_id,
        "port_code": port_code,
        "incident_id": args.incident_id,
        "kinds": args.kinds,
        "tiers": args.trust_tiers,
        "start_iso": start_iso,
        "end_iso": end_iso,
        "include_post": args.include_post_snapshot,
        "limit": args.limit
    })

    if not records:
        return render_no_data({"args": args.model_dump(exclude_none=True)})

    hits: List[MessageHit] = []
    flagged_count = 0
    detailed_view = is_targeted or len(records) == 1

    for r in records:
        is_mal = bool(r.get("is_malicious", False))
        if is_mal:
            flagged_count += 1

        msg_node = MessageNode(
            message_id=r["message_id"],
            filename=r["filename"],
            message_type=r["message_type"],
            message_kind=r["message_kind"],
            trust_tier=r["trust_tier"],
            sender=r["sender"],
            sent_at_utc=r["sent_at_utc"],
            subject=r["subject"],
            snippet=None if is_mal else r.get("snippet"),
            cleaned_body=None if is_mal else r.get("cleaned_body"),
            raw_message=None if is_mal else r.get("raw_message"),
            is_malicious=is_mal,
            in_snapshot=r.get("in_snapshot", True)
        )

        # Build compact edge list string
        linked_edges: List[str] = []
        for e in r.get("edges_data", []):
            if e and e.get("edge_type") and e.get("target_key"):
                linked_edges.append(f"{e['edge_type']}->{e['target_key']}")

        # Full body if detailed view and not malicious
        body_text: Optional[str] = None
        if detailed_view:
            if is_mal:
                body_text = "[WITHHELD: Message flagged for potential security or injection content]"
            else:
                body_text = r.get("raw_message") if args.include_raw else r.get("cleaned_body")

        hits.append(MessageHit(
            message=msg_node,
            linked=linked_edges,
            body=body_text
        ))

    result = SearchMessagesResult(
        hits=hits,
        total_matches=len(hits),
        flagged_malicious_count=flagged_count,
        detailed_view=detailed_view
    )
    return render_search_messages(result)

