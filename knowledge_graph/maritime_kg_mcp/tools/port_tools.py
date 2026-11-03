"""Port domain tools for Maritime Knowledge Graph MCP server.
Provides get_port_context (comprehensive port dossier with congestion series,
port agents, terminal port calls, and inbound voyages).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from utility.dependencies import DatabaseClientProtocol
from utility.logger import get_logger
from knowledge_graph.maritime_kg_mcp.models import (
    BerthVerdict,
    BerthWindowAssessment,
    CongestionNode,
    Gap,
    GetPortContextInput,
    GetPortContextResult,
    InboundVoyageRow,
    MessageLink,
    MessageNode,
    OrganizationNode,
    PortCallNode,
    PortCallRow,
    PortNode,
    Tier,
    ToolResponse,
    VesselNode,
    VoyageNode,
)
from knowledge_graph.maritime_kg_mcp.renderer import (
    render_ambiguous,
    render_no_data,
    render_port_context,
)
from knowledge_graph.maritime_kg_mcp.resolver import resolve_port

logger = get_logger(__name__)


def _eval_bw(revised_eta: Optional[datetime], bw_start: Optional[datetime], bw_end: Optional[datetime]) -> BerthWindowAssessment:
    if not (revised_eta and bw_start and bw_end):
        return BerthWindowAssessment(verdict=BerthVerdict.UNKNOWN, margin_hours=None)
    if revised_eta > bw_end:
        margin = (revised_eta - bw_end).total_seconds() / 3600.0
        return BerthWindowAssessment(verdict=BerthVerdict.LATE, margin_hours=round(margin, 2))
    elif revised_eta < bw_start:
        margin = (revised_eta - bw_start).total_seconds() / 3600.0
        return BerthWindowAssessment(verdict=BerthVerdict.EARLY, margin_hours=round(margin, 2))
    return BerthWindowAssessment(verdict=BerthVerdict.INSIDE_WINDOW, margin_hours=0.0)


def get_port_context(
    client: DatabaseClientProtocol, args: GetPortContextInput
) -> ToolResponse:
    """Retrieves port master data, agents, congestion history, port calls, and inbound sailings."""
    port_node, ambiguity = resolve_port(client, args.port)
    if ambiguity:
        return render_ambiguous(ambiguity)
    if not port_node:
        return render_no_data({"port": args.port})

    port_code = port_node.port_code
    start_iso = args.window.start_utc.isoformat()
    end_iso = args.window.end_utc.isoformat()
    start_date = args.window.start_utc.date().isoformat()
    end_date = args.window.end_utc.date().isoformat()

    # 1. Port Agents (Organizations BASED_AT this port)
    agents_cypher = """
    MATCH (org:Organization)-[:BASED_AT]->(p:Port {port_code: $port_code})
    RETURN org.org_id AS org_id, org.name AS name, coalesce(org.org_type, 'port_agent') AS org_type
    """
    ag_recs = client.execute_read_query(agents_cypher, {"port_code": port_code})
    agents = [OrganizationNode(org_id=r["org_id"], name=r["name"], org_type=r["org_type"]) for r in ag_recs]

    # 2. Congestion Series in Window
    cg_cypher = """
    MATCH (p:Port {port_code: $port_code})-[:HAS_CONGESTION]->(cg:Congestion)
    WHERE toString(cg.date_utc) >= $start_date AND toString(cg.date_utc) <= $end_date
    RETURN cg.congestion_id AS congestion_id,
           cg.date_utc AS date_utc,
           cg.congestion_level AS congestion_level,
           cg.avg_wait_hours AS avg_wait_hours,
           cg.vessels_at_anchor AS vessels_at_anchor
    ORDER BY cg.date_utc ASC
    """
    cg_recs = client.execute_read_query(cg_cypher, {
        "port_code": port_code,
        "start_date": start_date,
        "end_date": end_date
    })

    congestion_nodes: List[CongestionNode] = []
    total_wait = 0.0
    wait_count = 0
    max_anchor = 0
    peak_level = "Low"
    peak_date = "N/A"
    level_order = {"Low": 1, "Moderate": 2, "High": 3}

    for r in cg_recs:
        d_val = r["date_utc"]
        if hasattr(d_val, "to_native"):
            d_val = d_val.to_native()
        elif isinstance(d_val, str):
            d_val = datetime.strptime(d_val[:10], "%Y-%m-%d").date()

        c_level = r["congestion_level"]
        avg_w = r.get("avg_wait_hours")
        v_anc = r.get("vessels_at_anchor") or 0

        if avg_w is not None:
            total_wait += avg_w
            wait_count += 1
        if v_anc > max_anchor:
            max_anchor = v_anc

        if level_order.get(c_level, 0) >= level_order.get(peak_level, 0):
            peak_level = c_level
            peak_date = str(d_val)

        congestion_nodes.append(CongestionNode(
            congestion_id=r["congestion_id"],
            port_code=port_code,
            date_utc=d_val,
            congestion_level=c_level,
            avg_wait_hours=avg_w,
            vessels_at_anchor=v_anc
        ))

    congestion_summary = {
        "peak_level": peak_level,
        "peak_date": peak_date,
        "avg_wait_hours": round(total_wait / wait_count, 2) if wait_count > 0 else 0.0,
        "max_vessels_at_anchor": max_anchor
    }

    # 3. Port Calls in Window
    port_calls: List[PortCallRow] = []
    if args.include_port_calls:
        pc_cypher = """
        MATCH (pc:PortCall)-[:AT_PORT]->(p:Port {port_code: $port_code})
        MATCH (pc)-[:CALL_BY]->(v:Vessel)
        OPTIONAL MATCH (pc)-[:PART_OF_VOYAGE]->(voy:Voyage)
        WHERE (pc.anchorage_arrival_utc >= datetime($start_iso) AND pc.anchorage_arrival_utc <= datetime($end_iso))
           OR (pc.berthing_utc >= datetime($start_iso) AND pc.berthing_utc <= datetime($end_iso))
        RETURN pc.call_id AS call_id,
               pc.call_type AS call_type,
               pc.anchorage_arrival_utc AS anchorage_arrival_utc,
               pc.berth_scheduled_utc AS berth_scheduled_utc,
               pc.berthing_utc AS berthing_utc,
               pc.departure_utc AS departure_utc,
               pc.anchorage_wait_hours AS anchorage_wait_hours,
               pc.port_stay_hours AS port_stay_hours,
               v.vessel_id AS vessel_id, v.name AS vessel_name, v.imo AS vessel_imo,
               voy.voyage_id AS voyage_id
        ORDER BY pc.anchorage_arrival_utc ASC
        LIMIT $max_calls
        """
        pc_recs = client.execute_read_query(pc_cypher, {
            "port_code": port_code,
            "start_iso": start_iso,
            "end_iso": end_iso,
            "max_calls": args.max_port_calls
        })
        for r in pc_recs:
            call_node = PortCallNode(
                call_id=r["call_id"],
                call_type=r["call_type"],
                port_code=port_code,
                vessel_id=r["vessel_id"],
                anchorage_arrival_utc=r.get("anchorage_arrival_utc"),
                berth_scheduled_utc=r.get("berth_scheduled_utc"),
                berthing_utc=r.get("berthing_utc"),
                departure_utc=r.get("departure_utc"),
                anchorage_wait_hours=r.get("anchorage_wait_hours"),
                port_stay_hours=r.get("port_stay_hours")
            )
            v_node = VesselNode(vessel_id=r["vessel_id"], name=r["vessel_name"], imo=r["vessel_imo"])
            port_calls.append(PortCallRow(call=call_node, vessel=v_node, voyage_id=r.get("voyage_id")))

    # 4. Inbound Voyages in Window
    inbound_voyages: List[InboundVoyageRow] = []
    if args.include_inbound_voyages:
        inb_cypher = """
        MATCH (voy:Voyage)-[:ARRIVES_AT]->(p:Port {port_code: $port_code})
        MATCH (v:Vessel)-[:OPERATES_VOYAGE]->(voy)
        WHERE voy.revised_eta_utc >= datetime($start_iso) AND voy.revised_eta_utc <= datetime($end_iso)
        RETURN voy.voyage_id AS voyage_id,
               voy.status AS status,
               voy.departure_utc AS departure_utc,
               voy.original_eta_utc AS original_eta_utc,
               voy.revised_eta_utc AS revised_eta_utc,
               voy.berth_window_start_utc AS berth_window_start_utc,
               voy.berth_window_end_utc AS berth_window_end_utc,
               voy.recorded_delay_hours AS recorded_delay_hours,
               v.vessel_id AS vessel_id, v.name AS vessel_name, v.imo AS vessel_imo
        ORDER BY voy.revised_eta_utc ASC
        LIMIT 15
        """
        inb_recs = client.execute_read_query(inb_cypher, {
            "port_code": port_code,
            "start_iso": start_iso,
            "end_iso": end_iso
        })
        for r in inb_recs:
            voy = VoyageNode(
                voyage_id=r["voyage_id"],
                status=r["status"],
                departure_utc=r.get("departure_utc"),
                original_eta_utc=r.get("original_eta_utc"),
                revised_eta_utc=r.get("revised_eta_utc"),
                berth_window_start_utc=r.get("berth_window_start_utc"),
                berth_window_end_utc=r.get("berth_window_end_utc"),
                recorded_delay_hours=r.get("recorded_delay_hours")
            )
            v_node = VesselNode(vessel_id=r["vessel_id"], name=r["vessel_name"], imo=r["vessel_imo"])
            bw = _eval_bw(voy.revised_eta_utc, voy.berth_window_start_utc, voy.berth_window_end_utc)
            inbound_voyages.append(InboundVoyageRow(voyage=voy, vessel=v_node, berth_window=bw))

    # 5. Messages about Port
    messages: List[MessageLink] = []
    if args.include_messages:
        msg_cypher = """
        MATCH (m:Message)-[r:EVENT_AT_PORT|REFERENCES_PORT|DESCRIBES_CONGESTION]->(p:Port {port_code: $port_code})
        WHERE m.sent_at_utc >= datetime($start_iso) AND m.sent_at_utc <= datetime($end_iso)
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
        LIMIT 10
        """
        msg_recs = client.execute_read_query(msg_cypher, {
            "port_code": port_code,
            "start_iso": start_iso,
            "end_iso": end_iso
        })
        for r in msg_recs:
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
            messages.append(MessageLink(edge_type=r["edge_type"], message=msg))

    # Gaps
    gaps: List[Gap] = []
    if not congestion_nodes:
        gaps.append(Gap(
            kind="CONGESTION_DATA_MISSING",
            detail=f"No daily congestion records logged for port {port_code} in the specified date window.",
            related_ids=[port_code]
        ))

    result = GetPortContextResult(
        port=port_node,
        agents=agents,
        congestion=congestion_nodes,
        congestion_summary=congestion_summary,
        port_calls=port_calls,
        inbound_voyages=inbound_voyages,
        messages=messages,
        gaps=gaps
    )
    return render_port_context(result)


# =============================================================================
# Legacy preserved helpers
# =============================================================================

def search_ports(client: DatabaseClientProtocol, query: Optional[str] = None) -> Dict[str, Any]:
    """Legacy helper searching seaports."""
    cypher = """
    MATCH (p:Port)
    WHERE ($query IS NULL
           OR toLower(p.port_code) CONTAINS toLower($query)
           OR toLower(p.name) CONTAINS toLower($query)
           OR toLower(p.country) CONTAINS toLower($query))
    RETURN p.port_code AS port_code,
           p.name AS name,
           p.country AS country,
           p.timezone AS timezone
    ORDER BY p.port_code
    """
    records = client.execute_read_query(cypher, {"query": query})
    return {"total": len(records), "ports": records}


def get_port_congestion(
    client: DatabaseClientProtocol, port_code: str, date: Optional[str] = None, limit: int = 14
) -> Dict[str, Any]:
    """Legacy helper for port congestion."""
    cypher = """
    MATCH (p:Port {port_code: $port_code})-[:HAS_CONGESTION]->(c:Congestion)
    WHERE ($date IS NULL OR toString(c.date_utc) = $date)
    RETURN c.congestion_id AS congestion_id,
           toString(c.date_utc) AS date_utc,
           c.congestion_level AS congestion_level,
           c.avg_wait_hours AS avg_wait_hours,
           c.vessels_at_anchor AS vessels_at_anchor,
           c.source AS source
    ORDER BY c.date_utc DESC
    LIMIT $limit
    """
    records = client.execute_read_query(cypher, {"port_code": port_code, "date": date, "limit": limit})
    return {"port_code": port_code, "records": records}
