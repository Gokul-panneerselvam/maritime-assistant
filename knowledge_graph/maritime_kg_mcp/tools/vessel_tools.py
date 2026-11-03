"""Vessel domain tools for Maritime Knowledge Graph MCP server.
Provides get_vessel_context (comprehensive 360-degree vessel dossier)
alongside preserved legacy helper functions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from utility.dependencies import DatabaseClientProtocol
from utility.logger import get_logger
from knowledge_graph.maritime_kg_mcp.models import (
    BerthVerdict,
    BerthWindowAssessment,
    GetVesselContextInput,
    GetVesselContextResult,
    IncidentEvidence,
    IncidentNode,
    MessageLink,
    MessageNode,
    Tier,
    ToolResponse,
    VesselNode,
    VesselProfile,
    VoyageNode,
    VoyageTimelineRow,
)
from knowledge_graph.maritime_kg_mcp.renderer import (
    render_ambiguous,
    render_no_data,
    render_vessel_context,
)
from knowledge_graph.maritime_kg_mcp.resolver import resolve_vessel

logger = get_logger(__name__)


def _eval_berth_window(revised_eta: Optional[datetime], bw_start: Optional[datetime], bw_end: Optional[datetime]) -> BerthWindowAssessment:
    if not (revised_eta and bw_start and bw_end):
        return BerthWindowAssessment(verdict=BerthVerdict.UNKNOWN, margin_hours=None)
    if revised_eta > bw_end:
        margin = (revised_eta - bw_end).total_seconds() / 3600.0
        return BerthWindowAssessment(verdict=BerthVerdict.LATE, margin_hours=round(margin, 2))
    elif revised_eta < bw_start:
        margin = (revised_eta - bw_start).total_seconds() / 3600.0
        return BerthWindowAssessment(verdict=BerthVerdict.EARLY, margin_hours=round(margin, 2))
    else:
        return BerthWindowAssessment(verdict=BerthVerdict.INSIDE_WINDOW, margin_hours=0.0)


def get_vessel_context(
    client: DatabaseClientProtocol, args: GetVesselContextInput
) -> ToolResponse:
    """Retrieves full vessel profile, sister ships, voyage timeline, incidents, and bulletins."""
    v_node, ambiguity = resolve_vessel(client, args.vessel)
    if ambiguity:
        return render_ambiguous(ambiguity)
    if not v_node:
        return render_no_data({"vessel": args.vessel})

    vessel_id = v_node.vessel_id

    # 1. Fetch Vessel Profile
    profile_cypher = """
    MATCH (v:Vessel {vessel_id: $vessel_id})
    OPTIONAL MATCH (v)-[:OF_TYPE]->(vt:VesselType)
    OPTIONAL MATCH (v)-[:OF_CLASS]->(vc:VesselClass)
    OPTIONAL MATCH (v)-[:MANAGED_BY]->(tm:TechnicalManager)
    RETURN v.vessel_id AS vessel_id,
           v.name AS name,
           v.imo AS imo,
           coalesce(vt.name, 'Unknown') AS type_name,
           coalesce(vc.name, 'Unknown') AS class_name,
           coalesce(tm.name, 'Unknown') AS manager_name
    """
    prof_rec = client.execute_read_query(profile_cypher, {"vessel_id": vessel_id})
    if not prof_rec:
        return render_no_data({"vessel_id": vessel_id})

    p_data = prof_rec[0]
    profile = VesselProfile(
        vessel_id=p_data["vessel_id"],
        name=p_data["name"],
        imo=p_data["imo"],
        type_name=p_data["type_name"],
        class_name=p_data["class_name"],
        manager_name=p_data["manager_name"]
    )

    # 2. Sister Vessels (same class)
    sister_vessels: List[VesselNode] = []
    if args.include_sisters and profile.class_name != "Unknown":
        sisters_cypher = """
        MATCH (vc:VesselClass {name: $class_name})<-[:OF_CLASS]-(s:Vessel)
        WHERE s.vessel_id <> $vessel_id
        RETURN s.vessel_id AS vessel_id, s.name AS name, s.imo AS imo
        ORDER BY s.vessel_id
        """
        s_recs = client.execute_read_query(sisters_cypher, {"class_name": profile.class_name, "vessel_id": vessel_id})
        sister_vessels = [VesselNode(vessel_id=r["vessel_id"], name=r["name"], imo=r["imo"]) for r in s_recs]

    # 3. Manager Fleet
    manager_fleet: List[VesselNode] = []
    if args.include_manager_fleet and profile.manager_name != "Unknown":
        fleet_cypher = """
        MATCH (tm:TechnicalManager {name: $manager_name})<-[:MANAGED_BY]-(m:Vessel)
        WHERE m.vessel_id <> $vessel_id
        RETURN m.vessel_id AS vessel_id, m.name AS name, m.imo AS imo
        ORDER BY m.vessel_id
        """
        f_recs = client.execute_read_query(fleet_cypher, {"manager_name": profile.manager_name, "vessel_id": vessel_id})
        manager_fleet = [VesselNode(vessel_id=r["vessel_id"], name=r["name"], imo=r["imo"]) for r in f_recs]

    # 4. Voyage Timeline
    timeline_cypher = """
    MATCH (v:Vessel {vessel_id: $vessel_id})-[:OPERATES_VOYAGE]->(voy:Voyage)
    MATCH (voy)-[:DEPARTS_FROM]->(orig:Port)
    MATCH (voy)-[:ARRIVES_AT]->(dest:Port)
    OPTIONAL MATCH (voy)-[:EXPERIENCED_INCIDENT]->(inc:Incident)
    WITH voy, orig, dest, collect(inc.incident_id) AS incident_ids
    ORDER BY voy.departure_utc DESC
    LIMIT $limit
    RETURN voy.voyage_id AS voyage_id,
           voy.status AS status,
           voy.departure_utc AS departure_utc,
           voy.original_eta_utc AS original_eta_utc,
           voy.revised_eta_utc AS revised_eta_utc,
           voy.berth_window_start_utc AS berth_window_start_utc,
           voy.berth_window_end_utc AS berth_window_end_utc,
           voy.recorded_delay_hours AS recorded_delay_hours,
           voy.revised_eta_local AS revised_eta_local,
           orig.port_code AS origin_code,
           dest.port_code AS dest_code,
           incident_ids
    """
    t_recs = client.execute_read_query(timeline_cypher, {"vessel_id": vessel_id, "limit": args.voyages_limit})

    timeline: List[VoyageTimelineRow] = []
    current_voyage_id: Optional[str] = None

    for r in t_recs:
        voy = VoyageNode(
            voyage_id=r["voyage_id"],
            status=r["status"],
            departure_utc=r.get("departure_utc"),
            original_eta_utc=r.get("original_eta_utc"),
            revised_eta_utc=r.get("revised_eta_utc"),
            berth_window_start_utc=r.get("berth_window_start_utc"),
            berth_window_end_utc=r.get("berth_window_end_utc"),
            recorded_delay_hours=r.get("recorded_delay_hours"),
            revised_eta_local=r.get("revised_eta_local"),
        )
        bw = _eval_berth_window(voy.revised_eta_utc, voy.berth_window_start_utc, voy.berth_window_end_utc)

        if not current_voyage_id and voy.status in ("Delayed", "On schedule"):
            current_voyage_id = voy.voyage_id

        timeline.append(
            VoyageTimelineRow(
                voyage=voy,
                origin_code=r["origin_code"],
                dest_code=r["dest_code"],
                incident_ids=[i for i in r.get("incident_ids", []) if i],
                berth_window=bw
            )
        )

    # 5. Incidents
    incidents_cypher = """
    MATCH (v:Vessel {vessel_id: $vessel_id})
    MATCH (v)<-[:AFFECTS_VESSEL]-(inc:Incident)
    OPTIONAL MATCH (inc)-[:OCCURRED_ON_VOYAGE]->(voy:Voyage)
    OPTIONAL MATCH (m:Message)-[r:REPORTS_INCIDENT|CORROBORATES_INCIDENT|REVISES|CORRECTS_INCIDENT]->(inc)
    WITH inc, voy, collect(DISTINCT {
        edge_type: type(r),
        message: {
            message_id: m.message_id,
            filename: m.filename,
            message_type: m.message_type,
            message_kind: m.message_kind,
            trust_tier: m.trust_tier,
            sender: m.sender,
            sent_at_utc: m.sent_at_utc,
            subject: m.subject,
            snippet: substring(coalesce(m.cleaned_body, m.raw_message, ''), 0, 300),
            is_malicious: coalesce(m.is_malicious, false)
        }
    }) AS raw_links
    ORDER BY inc.reported_utc DESC
    RETURN inc.incident_id AS incident_id,
           inc.type AS type,
           inc.status AS status,
           coalesce(inc.severity, 'Unknown') AS severity,
           inc.reported_utc AS reported_utc,
           coalesce(inc.source, 'Unknown') AS source,
           inc.attributed_delay_hours AS attributed_delay_hours,
           voy.voyage_id AS voyage_id,
           raw_links
    """
    inc_recs = client.execute_read_query(incidents_cypher, {"vessel_id": vessel_id})
    incidents: List[IncidentEvidence] = []

    for r in inc_recs:
        status_val = r["status"]
        if args.incidents == "open" and status_val in ("Dismissed", "Resolved"):
            continue

        tier = Tier.CONFIRMED if status_val == "Confirmed" else (
            Tier.DISMISSED if status_val == "Dismissed" else Tier.UNVERIFIED
        )
        inc_node = IncidentNode(
            incident_id=r["incident_id"],
            type=r["type"],
            status=status_val,
            severity=r.get("severity") or "Unknown",
            reported_utc=r.get("reported_utc"),
            source=r.get("source") or "Unknown",
            attributed_delay_hours=r.get("attributed_delay_hours")
        )

        links: List[MessageLink] = []
        for l in r.get("raw_links", []):
            if l and l.get("edge_type") and l.get("message", {}).get("message_id"):
                m_data = l["message"]
                msg_node = MessageNode(
                    message_id=m_data["message_id"],
                    filename=m_data["filename"],
                    message_type=m_data["message_type"],
                    message_kind=m_data["message_kind"],
                    trust_tier=m_data["trust_tier"],
                    sender=m_data["sender"],
                    sent_at_utc=m_data["sent_at_utc"],
                    subject=m_data["subject"],
                    snippet=m_data.get("snippet"),
                    is_malicious=m_data.get("is_malicious", False)
                )
                links.append(MessageLink(edge_type=l["edge_type"], message=msg_node))

        incidents.append(IncidentEvidence(
            incident=inc_node,
            tier=tier,
            voyage_id=r.get("voyage_id"),
            vessel=v_node,
            links=links
        ))

    # 6. Class Messages (Bulletins)
    class_messages: List[MessageLink] = []
    if profile.class_name != "Unknown":
        class_cypher = """
        MATCH (vc:VesselClass {name: $class_name})<-[r:ABOUT_CLASS]-(m:Message)
        RETURN type(r) AS edge_type,
               m.message_id AS message_id,
               m.filename AS filename,
               m.message_type AS message_type,
               m.message_kind AS message_kind,
               m.trust_tier AS trust_tier,
               m.sender AS sender,
               m.sent_at_utc AS sent_at_utc,
               m.subject AS subject,
               substring(coalesce(m.cleaned_body, m.raw_message, ''), 0, 300) AS snippet,
               coalesce(m.is_malicious, false) AS is_malicious
        ORDER BY m.sent_at_utc DESC
        LIMIT 5
        """
        cm_recs = client.execute_read_query(class_cypher, {"class_name": profile.class_name})
        for r in cm_recs:
            msg = MessageNode(
                message_id=r["message_id"],
                filename=r["filename"],
                message_type=r["message_type"],
                message_kind=r["message_kind"],
                trust_tier=r["trust_tier"],
                sender=r["sender"],
                sent_at_utc=r["sent_at_utc"],
                subject=r["subject"],
                snippet=r.get("snippet"),
                is_malicious=r["is_malicious"]
            )
            class_messages.append(MessageLink(edge_type=r["edge_type"], message=msg))

    result = GetVesselContextResult(
        vessel=profile,
        sister_vessels=sister_vessels,
        manager_fleet=manager_fleet,
        current_voyage_id=current_voyage_id,
        timeline=timeline,
        incidents=incidents,
        class_messages=class_messages,
        vessel_messages=[]
    )

    return render_vessel_context(result)


# =============================================================================
# Legacy preserved helpers (for backwards compatibility)
# =============================================================================

def search_vessels(
    client: DatabaseClientProtocol,
    vessel_id: Optional[str] = None,
    name: Optional[str] = None,
    imo: Optional[int] = None,
    vessel_type: Optional[str] = None,
    vessel_class: Optional[str] = None,
    limit: int = 50
) -> Dict[str, Any]:
    """Legacy helper function preserving dictionary output for basic vessel search."""
    cypher = """
    MATCH (v:Vessel)
    OPTIONAL MATCH (v)-[:OF_TYPE]->(vt:VesselType)
    OPTIONAL MATCH (v)-[:OF_CLASS]->(vc:VesselClass)
    OPTIONAL MATCH (v)-[:MANAGED_BY]->(tm:TechnicalManager)
    WHERE ($vessel_id IS NULL OR v.vessel_id = $vessel_id)
      AND ($name IS NULL OR toLower(v.name) CONTAINS toLower($name))
      AND ($imo IS NULL OR v.imo = $imo)
      AND ($vessel_type IS NULL OR toLower(vt.name) CONTAINS toLower($vessel_type))
      AND ($vessel_class IS NULL OR toLower(vc.name) CONTAINS toLower($vessel_class))
    RETURN v.vessel_id AS vessel_id,
           v.name AS name,
           v.imo AS imo,
           vt.name AS type,
           vc.name AS vessel_class,
           tm.name AS technical_manager
    ORDER BY v.vessel_id
    LIMIT $limit
    """
    records = client.execute_read_query(cypher, {
        "vessel_id": vessel_id,
        "name": name,
        "imo": imo,
        "vessel_type": vessel_type,
        "vessel_class": vessel_class,
        "limit": limit
    })
    return {"status": "SUCCESS", "success": True, "count": len(records), "vessels": records}


def get_vessel_details(client: DatabaseClientProtocol, vessel_id: str) -> Dict[str, Any]:
    """Legacy helper returning raw dictionary details for a vessel."""
    args = GetVesselContextInput(vessel=vessel_id)
    resp = get_vessel_context(client, args)
    return {"vessel_id": vessel_id, "text": resp.to_agent_text(), "status": resp.status.value}
