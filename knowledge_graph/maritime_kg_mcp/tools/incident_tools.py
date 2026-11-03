"""Incident domain tools for Maritime Knowledge Graph MCP server.
Provides search_incident_history (recurrence analysis across vessel, class,
manager, and fleet scopes with correction chains and technical bulletins).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from utility.dependencies import DatabaseClientProtocol
from utility.logger import get_logger
from knowledge_graph.maritime_kg_mcp.models import (
    GetIncidentHistoryResult,
    IncidentEvidence,
    IncidentNode,
    MessageLink,
    MessageNode,
    ScopeResult,
    SearchIncidentHistoryInput,
    Tier,
    ToolResponse,
    VesselNode,
    VesselProfile,
)
from knowledge_graph.maritime_kg_mcp.renderer import (
    render_ambiguous,
    render_incident_history,
    render_no_data,
)
from knowledge_graph.maritime_kg_mcp.resolver import resolve_vessel

logger = get_logger(__name__)


def search_incident_history(
    client: DatabaseClientProtocol, args: SearchIncidentHistoryInput
) -> ToolResponse:
    """Finds recurrences of an incident type or component across vessel, class, manager, and fleet scopes."""
    resolved_type = args.incident_type
    keyword = args.keyword
    anchor_vessel_id: Optional[str] = None
    anchor_class_name: Optional[str] = None
    anchor_manager_name: Optional[str] = None
    correction_notes: List[str] = []

    # 1. Resolve from existing incident_id pattern if provided
    if args.incident_id:
        inc_pattern_cypher = """
        MATCH (inc:Incident {incident_id: $inc_id})
        OPTIONAL MATCH (inc)-[:AFFECTS_VESSEL]->(v:Vessel)
        OPTIONAL MATCH (v)-[:OF_CLASS]->(vc:VesselClass)
        OPTIONAL MATCH (v)-[:MANAGED_BY]->(tm:TechnicalManager)
        OPTIONAL MATCH (m:Message)-[:CORRECTS_INCIDENT]->(inc)
        RETURN inc.type AS type,
               v.vessel_id AS vessel_id,
               vc.name AS class_name,
               tm.name AS manager_name,
               m.filename AS corr_file,
               m.subject AS corr_subj
        """
        recs = client.execute_read_query(inc_pattern_cypher, {"inc_id": args.incident_id})
        if recs:
            r = recs[0]
            if not resolved_type:
                resolved_type = r["type"]
            if not anchor_vessel_id and r.get("vessel_id"):
                anchor_vessel_id = r["vessel_id"]
                anchor_class_name = r.get("class_name")
                anchor_manager_name = r.get("manager_name")
            if r.get("corr_file"):
                correction_notes.append(f"Correction in {r['corr_file']}: {r.get('corr_subj')}")

    # 2. Resolve anchor vessel if specified explicitly
    if args.anchor_vessel and not anchor_vessel_id:
        v_node, amb = resolve_vessel(client, args.anchor_vessel)
        if amb:
            return render_ambiguous(amb)
        if not v_node:
            return render_no_data({"anchor_vessel": args.anchor_vessel})
        anchor_vessel_id = v_node.vessel_id

        # Query class and manager for anchor vessel
        vm_cypher = """
        MATCH (v:Vessel {vessel_id: $vid})
        OPTIONAL MATCH (v)-[:OF_CLASS]->(vc:VesselClass)
        OPTIONAL MATCH (v)-[:MANAGED_BY]->(tm:TechnicalManager)
        RETURN vc.name AS class_name, tm.name AS manager_name
        """
        vm_recs = client.execute_read_query(vm_cypher, {"vid": anchor_vessel_id})
        if vm_recs:
            anchor_class_name = vm_recs[0].get("class_name")
            anchor_manager_name = vm_recs[0].get("manager_name")

    # Match incidents across requested scopes
    seen_incident_ids: Set[str] = set()
    scope_results: List[ScopeResult] = []

    # Helper function to query a scope
    def _query_scope(where_vessel_clause: str, params: Dict[str, Any]) -> List[IncidentEvidence]:
        cypher = f"""
        MATCH (inc:Incident)
        MATCH (inc)-[:AFFECTS_VESSEL]->(v:Vessel)
        OPTIONAL MATCH (v)-[:OF_CLASS]->(vc:VesselClass)
        OPTIONAL MATCH (v)-[:MANAGED_BY]->(tm:TechnicalManager)
        OPTIONAL MATCH (m:Message)-[r:REPORTS_INCIDENT|CORROBORATES_INCIDENT|REVISES|CORRECTS_INCIDENT]->(inc)
        WHERE inc.status IN $statuses
          AND (
            $type IS NULL OR toLower(inc.type) CONTAINS toLower($type)
          )
          AND (
            $kw IS NULL OR toLower(inc.type) CONTAINS toLower($kw) OR toLower(coalesce(m.cleaned_body, '')) CONTAINS toLower($kw)
          )
          AND ({where_vessel_clause})
        WITH inc, v, vc, tm, collect(DISTINCT {{
            edge_type: type(r),
            message: {{
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
            }}
        }}) AS raw_links
        ORDER BY inc.reported_utc DESC
        LIMIT $limit
        RETURN inc.incident_id AS incident_id,
               inc.type AS type,
               inc.status AS status,
               coalesce(inc.severity, 'Unknown') AS severity,
               inc.reported_utc AS reported_utc,
               coalesce(inc.source, 'Unknown') AS source,
               inc.attributed_delay_hours AS attributed_delay_hours,
               v.vessel_id AS vessel_id, v.name AS vessel_name, v.imo AS vessel_imo,
               raw_links
        """
        all_params = {
            "statuses": args.statuses,
            "type": resolved_type,
            "kw": keyword,
            "limit": args.limit_per_scope,
            **params
        }
        records = client.execute_read_query(cypher, all_params)
        results: List[IncidentEvidence] = []

        for r in records:
            inc_id = r["incident_id"]
            if inc_id in seen_incident_ids:
                continue
            seen_incident_ids.add(inc_id)

            tier = Tier.CONFIRMED if r["status"] == "Confirmed" else (
                Tier.DISMISSED if r["status"] == "Dismissed" else Tier.UNVERIFIED
            )
            v_node = VesselNode(vessel_id=r["vessel_id"], name=r["vessel_name"], imo=r["vessel_imo"])
            inc_node = IncidentNode(
                incident_id=inc_id,
                type=r["type"],
                status=r["status"],
                severity=r.get("severity") or "Unknown",
                reported_utc=r.get("reported_utc"),
                source=r.get("source") or "Unknown",
                attributed_delay_hours=r.get("attributed_delay_hours")
            )
            links = []
            for l in r.get("raw_links", []):
                if l and l.get("edge_type") and l.get("message", {}).get("message_id"):
                    m_d = l["message"]
                    msg = MessageNode(
                        message_id=m_d["message_id"],
                        filename=m_d["filename"],
                        message_type=m_d["message_type"],
                        message_kind=m_d["message_kind"],
                        trust_tier=m_d["trust_tier"],
                        sender=m_d["sender"],
                        sent_at_utc=m_d["sent_at_utc"],
                        subject=m_d["subject"],
                        snippet=m_d.get("snippet"),
                        is_malicious=m_d.get("is_malicious", False)
                    )
                    links.append(MessageLink(edge_type=l["edge_type"], message=msg))

            results.append(IncidentEvidence(
                incident=inc_node,
                tier=tier,
                vessel=v_node,
                links=links
            ))
        return results

    # Execute per scope
    for sc in args.scopes:
        if sc == "vessel" and anchor_vessel_id:
            ev_list = _query_scope("v.vessel_id = $vid", {"vid": anchor_vessel_id})
            confirmed_hours = sum(e.incident.attributed_delay_hours or 0.0 for e in ev_list if e.tier == Tier.CONFIRMED)
            distinct_v = len({e.vessel.vessel_id for e in ev_list if e.vessel})
            scope_results.append(ScopeResult(
                scope="vessel",
                scope_label=f"Vessel: {anchor_vessel_id}",
                incidents=ev_list,
                total_matches=len(ev_list),
                distinct_vessels=distinct_v,
                total_attributed_delay_hours=round(confirmed_hours, 2)
            ))
        elif sc == "class" and anchor_class_name:
            ev_list = _query_scope("vc.name = $cname AND v.vessel_id <> $vid", {"cname": anchor_class_name, "vid": anchor_vessel_id or ""})
            confirmed_hours = sum(e.incident.attributed_delay_hours or 0.0 for e in ev_list if e.tier == Tier.CONFIRMED)
            distinct_v = len({e.vessel.vessel_id for e in ev_list if e.vessel})
            scope_results.append(ScopeResult(
                scope="class",
                scope_label=f"Class: {anchor_class_name}",
                incidents=ev_list,
                total_matches=len(ev_list),
                distinct_vessels=distinct_v,
                total_attributed_delay_hours=round(confirmed_hours, 2)
            ))
        elif sc == "manager" and anchor_manager_name:
            ev_list = _query_scope("tm.name = $mname AND v.vessel_id <> $vid", {"mname": anchor_manager_name, "vid": anchor_vessel_id or ""})
            confirmed_hours = sum(e.incident.attributed_delay_hours or 0.0 for e in ev_list if e.tier == Tier.CONFIRMED)
            distinct_v = len({e.vessel.vessel_id for e in ev_list if e.vessel})
            scope_results.append(ScopeResult(
                scope="manager",
                scope_label=f"Manager: {anchor_manager_name}",
                incidents=ev_list,
                total_matches=len(ev_list),
                distinct_vessels=distinct_v,
                total_attributed_delay_hours=round(confirmed_hours, 2)
            ))
        elif sc == "fleet":
            ev_list = _query_scope("true", {})
            confirmed_hours = sum(e.incident.attributed_delay_hours or 0.0 for e in ev_list if e.tier == Tier.CONFIRMED)
            distinct_v = len({e.vessel.vessel_id for e in ev_list if e.vessel})
            scope_results.append(ScopeResult(
                scope="fleet",
                scope_label="Entire Fleet",
                incidents=ev_list,
                total_matches=len(ev_list),
                distinct_vessels=distinct_v,
                total_attributed_delay_hours=round(confirmed_hours, 2)
            ))

    # 3. Bulletins
    bulletins: List[MessageLink] = []
    bulletin_cypher = """
    MATCH (m:Message)
    WHERE m.message_kind IN ['technical_bulletin', 'technical_correction']
      AND (
        $type IS NULL OR toLower(m.subject) CONTAINS toLower($type) OR toLower(coalesce(m.cleaned_body, '')) CONTAINS toLower($type)
      )
    RETURN m.message_id AS message_id,
           m.filename AS filename,
           m.message_type AS message_type,
           m.message_kind AS message_kind,
           m.trust_tier AS trust_tier,
           m.sender AS sender,
           m.sent_at_utc AS sent_at_utc,
           m.subject AS subject,
           substring(coalesce(m.cleaned_body, m.raw_message, ''), 0, 300) AS snippet,
           coalesce(m.is_malicious, false) AS is_malicious
    LIMIT 5
    """
    b_recs = client.execute_read_query(bulletin_cypher, {"type": resolved_type or keyword})
    for r in b_recs:
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
        bulletins.append(MessageLink(edge_type="ABOUT_CLASS", message=msg))

    result = GetIncidentHistoryResult(
        pattern={"type": resolved_type, "keyword": keyword, "anchor_vessel": anchor_vessel_id},
        scopes=scope_results,
        bulletins=bulletins,
        correction_chain_notes=correction_notes
    )
    return render_incident_history(result)


# =============================================================================
# Legacy preserved helpers
# =============================================================================

def search_incidents(
    client: DatabaseClientProtocol,
    severity: Optional[str] = None,
    incident_type: Optional[str] = None,
    status: Optional[str] = None,
    voyage_id: Optional[str] = None,
    vessel_id: Optional[str] = None,
    limit: int = 50
) -> Dict[str, Any]:
    """Legacy helper searching incidents."""
    cypher = """
    MATCH (inc:Incident)
    OPTIONAL MATCH (inc)-[:OCCURRED_ON_VOYAGE]->(voy:Voyage)
    OPTIONAL MATCH (inc)-[:AFFECTS_VESSEL]->(v:Vessel)
    WHERE ($severity IS NULL OR toLower(inc.severity) = toLower($severity))
      AND ($incident_type IS NULL OR toLower(inc.type) CONTAINS toLower($incident_type))
      AND ($status IS NULL OR toLower(inc.status) = toLower($status))
      AND ($voyage_id IS NULL OR voy.voyage_id = $voyage_id)
      AND ($vessel_id IS NULL OR v.vessel_id = $vessel_id)
    RETURN inc.incident_id AS incident_id,
           inc.type AS type,
           coalesce(inc.severity, 'Unknown') AS severity,
           inc.status AS status,
           toString(inc.reported_utc) AS reported_utc,
           inc.attributed_delay_hours AS attributed_delay_hours,
           coalesce(inc.source, 'Unknown') AS source,
           voy.voyage_id AS voyage_id,
           v.name AS vessel_name
    ORDER BY inc.reported_utc DESC
    LIMIT $limit
    """
    records = client.execute_read_query(cypher, {
        "severity": severity,
        "incident_type": incident_type,
        "status": status,
        "voyage_id": voyage_id,
        "vessel_id": vessel_id,
        "limit": limit
    })
    return {"total": len(records), "incidents": records}
