"""Voyage domain tools for Maritime Knowledge Graph MCP server.
Provides get_voyage_context (deep multi-hop voyage dossier)
and scan_voyages (fleet-wide voyage discovery and risk ranking).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from utility.dependencies import DatabaseClientProtocol
from utility.logger import get_logger
from knowledge_graph.maritime_kg_mcp.models import (
    BerthVerdict,
    BerthWindowAssessment,
    BookingsSummary,
    CongestionNode,
    DateWindow,
    DelayReconciliation,
    Gap,
    GetVoyageContextInput,
    GetVoyageContextResult,
    IncidentEvidence,
    IncidentNode,
    MessageLink,
    MessageNode,
    PortCallNode,
    PortNode,
    RiskFactor,
    ScanRow,
    ScanVoyagesInput,
    ScanVoyagesResult,
    Tier,
    ToolResponse,
    VesselProfile,
    VoyageDossier,
    VoyageNode,
)
from knowledge_graph.maritime_kg_mcp.renderer import (
    render_ambiguous,
    render_no_data,
    render_scan_voyages,
    render_voyage_context,
)
from knowledge_graph.maritime_kg_mcp.resolver import resolve_port, resolve_vessel

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


# =============================================================================
# 1. get_voyage_context
# =============================================================================

def get_voyage_context(
    client: DatabaseClientProtocol, args: GetVoyageContextInput
) -> ToolResponse:
    """Fetches complete operational context for one or a few matching voyages."""
    voyage_ids: List[str] = []

    if args.voyage_id:
        voyage_ids = [args.voyage_id.strip()]
    else:
        # Resolve selectors
        vessel_id: Optional[str] = None
        if args.vessel:
            v_node, ambiguity = resolve_vessel(client, args.vessel)
            if ambiguity:
                return render_ambiguous(ambiguity)
            if not v_node:
                return render_no_data({"vessel": args.vessel})
            vessel_id = v_node.vessel_id

        dest_code: Optional[str] = None
        if args.dest_port:
            p_node, p_amb = resolve_port(client, args.dest_port)
            if p_amb:
                return render_ambiguous(p_amb)
            if not p_node:
                return render_no_data({"dest_port": args.dest_port})
            dest_code = p_node.port_code

        orig_code: Optional[str] = None
        if args.origin_port:
            p_node, p_amb = resolve_port(client, args.origin_port)
            if p_amb:
                return render_ambiguous(p_amb)
            if not p_node:
                return render_no_data({"origin_port": args.origin_port})
            orig_code = p_node.port_code

        # Dynamic voyage selector query
        selector_cypher = """
        MATCH (voy:Voyage)
        MATCH (v:Vessel)-[:OPERATES_VOYAGE]->(voy)
        MATCH (voy)-[:DEPARTS_FROM]->(orig:Port)
        MATCH (voy)-[:ARRIVES_AT]->(dest:Port)
        WHERE ($vessel_id IS NULL OR v.vessel_id = $vessel_id)
          AND ($dest_code IS NULL OR dest.port_code = $dest_code)
          AND ($orig_code IS NULL OR orig.port_code = $orig_code)
          AND (
            $which <> 'current' OR (voy.status IN ['Delayed', 'On schedule'])
          )
          AND (
            $which <> 'next' OR voy.status = 'Scheduled'
          )
          AND (
            $start_utc IS NULL OR voy.revised_eta_utc >= datetime($start_utc)
          )
          AND (
            $end_utc IS NULL OR voy.revised_eta_utc <= datetime($end_utc)
          )
        RETURN voy.voyage_id AS voyage_id
        ORDER BY voy.departure_utc DESC
        LIMIT $max_voyages
        """
        start_iso = args.window.start_utc.isoformat() if args.window else None
        end_iso = args.window.end_utc.isoformat() if args.window else None

        records = client.execute_read_query(selector_cypher, {
            "vessel_id": vessel_id,
            "dest_code": dest_code,
            "orig_code": orig_code,
            "which": args.which,
            "start_utc": start_iso,
            "end_utc": end_iso,
            "max_voyages": args.max_voyages
        })
        voyage_ids = [r["voyage_id"] for r in records]

    if not voyage_ids:
        return render_no_data({"args": args.model_dump(exclude_none=True)})

    dossiers: List[VoyageDossier] = []

    for vid in voyage_ids:
        # 1. Fetch Voyage Core, Vessel, Ports
        voy_cypher = """
        MATCH (voy:Voyage {voyage_id: $vid})
        MATCH (v:Vessel)-[:OPERATES_VOYAGE]->(voy)
        OPTIONAL MATCH (v)-[:OF_TYPE]->(vt:VesselType)
        OPTIONAL MATCH (v)-[:OF_CLASS]->(vc:VesselClass)
        OPTIONAL MATCH (v)-[:MANAGED_BY]->(tm:TechnicalManager)
        MATCH (voy)-[:DEPARTS_FROM]->(orig:Port)
        MATCH (voy)-[:ARRIVES_AT]->(dest:Port)
        RETURN voy.voyage_id AS voyage_id,
               voy.status AS status,
               voy.departure_utc AS departure_utc,
               voy.original_eta_utc AS original_eta_utc,
               voy.revised_eta_utc AS revised_eta_utc,
               voy.berth_window_start_utc AS berth_window_start_utc,
               voy.berth_window_end_utc AS berth_window_end_utc,
               voy.recorded_delay_hours AS recorded_delay_hours,
               voy.revised_eta_local AS revised_eta_local,
               v.vessel_id AS vessel_id, v.name AS vessel_name, v.imo AS vessel_imo,
               coalesce(vt.name, 'Unknown') AS type_name,
               coalesce(vc.name, 'Unknown') AS class_name,
               coalesce(tm.name, 'Unknown') AS manager_name,
               orig.port_code AS orig_code, orig.name AS orig_name, orig.country AS orig_country, orig.timezone AS orig_tz,
               dest.port_code AS dest_code, dest.name AS dest_name, dest.country AS dest_country, dest.timezone AS dest_tz
        """
        v_rec = client.execute_read_query(voy_cypher, {"vid": vid})
        if not v_rec:
            continue
        v_data = v_rec[0]

        voyage_node = VoyageNode(
            voyage_id=v_data["voyage_id"],
            status=v_data["status"],
            departure_utc=v_data.get("departure_utc"),
            original_eta_utc=v_data.get("original_eta_utc"),
            revised_eta_utc=v_data.get("revised_eta_utc"),
            berth_window_start_utc=v_data.get("berth_window_start_utc"),
            berth_window_end_utc=v_data.get("berth_window_end_utc"),
            recorded_delay_hours=v_data.get("recorded_delay_hours"),
            revised_eta_local=v_data.get("revised_eta_local"),
        )
        vessel_profile = VesselProfile(
            vessel_id=v_data["vessel_id"],
            name=v_data["vessel_name"],
            imo=v_data["vessel_imo"],
            type_name=v_data["type_name"],
            class_name=v_data["class_name"],
            manager_name=v_data["manager_name"]
        )
        orig_port = PortNode(
            port_code=v_data["orig_code"],
            name=v_data["orig_name"],
            country=v_data["orig_country"],
            timezone=v_data.get("orig_tz", "UTC")
        )
        dest_port = PortNode(
            port_code=v_data["dest_code"],
            name=v_data["dest_name"],
            country=v_data["dest_country"],
            timezone=v_data.get("dest_tz", "UTC")
        )

        # 2. Port Calls
        pc_cypher = """
        MATCH (voy:Voyage {voyage_id: $vid})-[:HAS_PORT_CALL]->(pc:PortCall)
        MATCH (pc)-[:AT_PORT]->(p:Port)
        RETURN pc.call_id AS call_id,
               pc.call_type AS call_type,
               p.port_code AS port_code,
               pc.anchorage_arrival_utc AS anchorage_arrival_utc,
               pc.berth_scheduled_utc AS berth_scheduled_utc,
               pc.berthing_utc AS berthing_utc,
               pc.departure_utc AS departure_utc,
               pc.anchorage_wait_hours AS anchorage_wait_hours,
               pc.port_stay_hours AS port_stay_hours
        ORDER BY pc.anchorage_arrival_utc ASC
        """
        pc_recs = client.execute_read_query(pc_cypher, {"vid": vid})
        port_calls: List[PortCallNode] = [
            PortCallNode(
                call_id=r["call_id"],
                call_type=r["call_type"],
                port_code=r["port_code"],
                vessel_id=vessel_profile.vessel_id,
                anchorage_arrival_utc=r.get("anchorage_arrival_utc"),
                berth_scheduled_utc=r.get("berth_scheduled_utc"),
                berthing_utc=r.get("berthing_utc"),
                departure_utc=r.get("departure_utc"),
                anchorage_wait_hours=r.get("anchorage_wait_hours"),
                port_stay_hours=r.get("port_stay_hours")
            )
            for r in pc_recs
        ]

        # 3. Congestion around revised ETA at destination
        dest_congestion: List[CongestionNode] = []
        if voyage_node.revised_eta_utc:
            eta_dt = voyage_node.revised_eta_utc
            c_start = (eta_dt - timedelta(days=args.congestion_days_around_eta)).date().isoformat()
            c_end = (eta_dt + timedelta(days=args.congestion_days_around_eta)).date().isoformat()

            cg_cypher = """
            MATCH (p:Port {port_code: $dest_code})-[:HAS_CONGESTION]->(cg:Congestion)
            WHERE toString(cg.date_utc) >= $start_date AND toString(cg.date_utc) <= $end_date
            RETURN cg.congestion_id AS congestion_id,
                   $dest_code AS port_code,
                   cg.date_utc AS date_utc,
                   cg.congestion_level AS congestion_level,
                   cg.avg_wait_hours AS avg_wait_hours,
                   cg.vessels_at_anchor AS vessels_at_anchor
            ORDER BY cg.date_utc ASC
            """
            cg_recs = client.execute_read_query(cg_cypher, {
                "dest_code": dest_port.port_code,
                "start_date": c_start,
                "end_date": c_end
            })
            for r in cg_recs:
                d_val = r["date_utc"]
                if hasattr(d_val, "to_native"):
                    d_val = d_val.to_native()
                elif isinstance(d_val, str):
                    d_val = datetime.strptime(d_val[:10], "%Y-%m-%d").date()
                dest_congestion.append(CongestionNode(
                    congestion_id=r["congestion_id"],
                    port_code=r["port_code"],
                    date_utc=d_val,
                    congestion_level=r["congestion_level"],
                    avg_wait_hours=r.get("avg_wait_hours"),
                    vessels_at_anchor=r.get("vessels_at_anchor")
                ))

        # 4. Incidents on this voyage
        inc_cypher = """
        MATCH (voy:Voyage {voyage_id: $vid})-[:EXPERIENCED_INCIDENT]->(inc:Incident)
        OPTIONAL MATCH (m:Message)-[r:REPORTS_INCIDENT|CORROBORATES_INCIDENT|REVISES|CORRECTS_INCIDENT]->(inc)
        WITH inc, collect(DISTINCT {
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
        RETURN inc.incident_id AS incident_id,
               inc.type AS type,
               inc.status AS status,
               coalesce(inc.severity, 'Unknown') AS severity,
               inc.reported_utc AS reported_utc,
               coalesce(inc.source, 'Unknown') AS source,
               inc.attributed_delay_hours AS attributed_delay_hours,
               raw_links
        """
        inc_recs = client.execute_read_query(inc_cypher, {"vid": vid})
        incidents: List[IncidentEvidence] = []
        confirmed_delay_hours = 0.0
        unverified_delay_hours = 0.0

        for r in inc_recs:
            status_val = r["status"]
            tier = Tier.CONFIRMED if status_val == "Confirmed" else (
                Tier.DISMISSED if status_val == "Dismissed" else Tier.UNVERIFIED
            )
            attr_h = float(r.get("attributed_delay_hours") or 0.0)
            if tier == Tier.CONFIRMED:
                confirmed_delay_hours += attr_h
            elif tier == Tier.UNVERIFIED:
                unverified_delay_hours += attr_h

            inc_node = IncidentNode(
                incident_id=r["incident_id"],
                type=r["type"],
                status=status_val,
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

            incidents.append(IncidentEvidence(
                incident=inc_node,
                tier=tier,
                voyage_id=vid,
                vessel=vessel_profile,
                links=links
            ))

        # 5. Bookings Summary
        bookings_summary: Optional[BookingsSummary] = None
        if args.include_bookings_summary:
            bk_cypher = """
            MATCH (b:Booking)-[:BOOKED_ON]->(voy:Voyage {voyage_id: $vid})
            MATCH (c:Customer)-[:PLACED_BOOKING]->(b)
            RETURN count(DISTINCT c) AS customer_count,
                   sum(CASE WHEN b.status = 'Confirmed' AND NOT coalesce(b.is_rolled, false) THEN b.containers ELSE 0 END) AS confirmed_teu,
                   sum(CASE WHEN coalesce(b.is_rolled, false) OR b.status STARTS WITH 'Rolled' THEN b.containers ELSE 0 END) AS rolled_teu,
                   sum(CASE WHEN b.status = 'Cancelled' THEN b.containers ELSE 0 END) AS cancelled_teu
            """
            bk_recs = client.execute_read_query(bk_cypher, {"vid": vid})
            if bk_recs:
                br = bk_recs[0]
                bookings_summary = BookingsSummary(
                    customers=br.get("customer_count", 0),
                    total_containers_confirmed=br.get("confirmed_teu", 0),
                    total_containers_rolled=br.get("rolled_teu", 0),
                    total_containers_cancelled=br.get("cancelled_teu", 0)
                )

        # 6. Berth Window & Delay Reconciliation
        bw = _eval_bw(voyage_node.revised_eta_utc, voyage_node.berth_window_start_utc, voyage_node.berth_window_end_utc)

        recorded_delay = voyage_node.recorded_delay_hours
        eta_slip: Optional[float] = None
        if voyage_node.revised_eta_utc and voyage_node.original_eta_utc:
            eta_slip = round((voyage_node.revised_eta_utc - voyage_node.original_eta_utc).total_seconds() / 3600.0, 2)

        anchorage_wait_sum = sum(pc.anchorage_wait_hours or 0.0 for pc in port_calls)
        unexplained: Optional[float] = None
        if recorded_delay is not None:
            unexplained = round(recorded_delay - confirmed_delay_hours - anchorage_wait_sum, 2)

        discrepancy = False
        if recorded_delay is not None and eta_slip is not None:
            discrepancy = abs(recorded_delay - eta_slip) > 0.5

        delay_rec = DelayReconciliation(
            recorded_delay_hours=recorded_delay,
            eta_slip_hours=eta_slip,
            confirmed_attributed_hours=round(confirmed_delay_hours, 2),
            unverified_attributed_hours=round(unverified_delay_hours, 2),
            anchorage_wait_hours=round(anchorage_wait_sum, 2),
            unexplained_hours=unexplained,
            discrepancy=discrepancy
        )

        # 7. Identify Gaps
        gaps: List[Gap] = []
        if unexplained is not None and unexplained > 2.0:
            gaps.append(Gap(
                kind="DELAY_UNEXPLAINED",
                detail=f"{unexplained:.1f} hours of recorded delay remain unexplained by confirmed incidents or anchorage waits.",
                related_ids=[vid]
            ))
        for inc_ev in incidents:
            if inc_ev.tier == Tier.UNVERIFIED:
                gaps.append(Gap(
                    kind="INCIDENT_UNDER_REVIEW",
                    detail=f"Incident {inc_ev.incident.incident_id} ({inc_ev.incident.type}) is unverified or under review.",
                    related_ids=[inc_ev.incident.incident_id]
                ))
            if not inc_ev.links:
                gaps.append(Gap(
                    kind="INCIDENT_UNCORROBORATED",
                    detail=f"Incident {inc_ev.incident.incident_id} has no linked backing messages.",
                    related_ids=[inc_ev.incident.incident_id]
                ))

        dossiers.append(VoyageDossier(
            voyage=voyage_node,
            vessel=vessel_profile,
            origin=orig_port,
            destination=dest_port,
            port_calls=port_calls,
            destination_congestion=dest_congestion,
            incidents=incidents,
            messages_about_voyage=[],
            bookings=bookings_summary,
            berth_window=bw,
            delay=delay_rec,
            gaps=gaps
        ))

    result = GetVoyageContextResult(dossiers=dossiers, matched_total=len(dossiers))
    return render_voyage_context(result)


# =============================================================================
# 2. scan_voyages
# =============================================================================

def scan_voyages(
    client: DatabaseClientProtocol, args: ScanVoyagesInput
) -> ToolResponse:
    """Fleet-wide discovery and ranking of voyages across a date window."""
    dest_code: Optional[str] = None
    if args.dest_port:
        p_node, p_amb = resolve_port(client, args.dest_port)
        if p_amb:
            return render_ambiguous(p_amb)
        if not p_node:
            return render_no_data({"dest_port": args.dest_port})
        dest_code = p_node.port_code

    orig_code: Optional[str] = None
    if args.origin_port:
        p_node, p_amb = resolve_port(client, args.origin_port)
        if p_amb:
            return render_ambiguous(p_amb)
        if not p_node:
            return render_no_data({"origin_port": args.origin_port})
        orig_code = p_node.port_code

    start_iso = args.window.start_utc.isoformat()
    end_iso = args.window.end_utc.isoformat()

    scan_cypher = """
    MATCH (voy:Voyage)
    MATCH (v:Vessel)-[:OPERATES_VOYAGE]->(voy)
    OPTIONAL MATCH (v)-[:OF_TYPE]->(vt:VesselType)
    OPTIONAL MATCH (v)-[:OF_CLASS]->(vc:VesselClass)
    OPTIONAL MATCH (v)-[:MANAGED_BY]->(tm:TechnicalManager)
    MATCH (voy)-[:DEPARTS_FROM]->(orig:Port)
    MATCH (voy)-[:ARRIVES_AT]->(dest:Port)
    WHERE voy.status IN $statuses
      AND ($dest_code IS NULL OR dest.port_code = $dest_code)
      AND ($orig_code IS NULL OR orig.port_code = $orig_code)
      AND ($vessel_class IS NULL OR toLower(vc.name) CONTAINS toLower($vessel_class))
      AND ($manager IS NULL OR toLower(tm.name) CONTAINS toLower($manager))
      AND ($vessel_type IS NULL OR toLower(vt.name) CONTAINS toLower($vessel_type))
      AND (
        CASE $field
          WHEN 'revised_eta' THEN voy.revised_eta_utc >= datetime($start_iso) AND voy.revised_eta_utc <= datetime($end_iso)
          WHEN 'original_eta' THEN voy.original_eta_utc >= datetime($start_iso) AND voy.original_eta_utc <= datetime($end_iso)
          WHEN 'departure' THEN voy.departure_utc >= datetime($start_iso) AND voy.departure_utc <= datetime($end_iso)
          ELSE voy.revised_eta_utc >= datetime($start_iso) AND voy.revised_eta_utc <= datetime($end_iso)
        END
      )
    OPTIONAL MATCH (voy)-[:EXPERIENCED_INCIDENT]->(inc:Incident)
    WITH voy, v, vt, vc, tm, orig, dest, collect(inc) AS incs
    RETURN voy.voyage_id AS voyage_id,
           voy.status AS status,
           voy.departure_utc AS departure_utc,
           voy.original_eta_utc AS original_eta_utc,
           voy.revised_eta_utc AS revised_eta_utc,
           voy.berth_window_start_utc AS berth_window_start_utc,
           voy.berth_window_end_utc AS berth_window_end_utc,
           voy.recorded_delay_hours AS recorded_delay_hours,
           v.vessel_id AS vessel_id, v.name AS vessel_name, v.imo AS vessel_imo,
           coalesce(vt.name, 'Unknown') AS type_name,
           coalesce(vc.name, 'Unknown') AS class_name,
           coalesce(tm.name, 'Unknown') AS manager_name,
           orig.port_code AS orig_code,
           dest.port_code AS dest_code,
           [i IN incs | {id: i.incident_id, status: i.status, type: i.type}] AS incident_items
    LIMIT 100
    """
    records = client.execute_read_query(scan_cypher, {
        "statuses": args.statuses,
        "dest_code": dest_code,
        "orig_code": orig_code,
        "vessel_class": args.vessel_class,
        "manager": args.manager,
        "vessel_type": args.vessel_type,
        "field": args.window_field,
        "start_iso": start_iso,
        "end_iso": end_iso
    })

    rows: List[ScanRow] = []

    for r in records:
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
        v_prof = VesselProfile(
            vessel_id=r["vessel_id"],
            name=r["vessel_name"],
            imo=r["vessel_imo"],
            type_name=r["type_name"],
            class_name=r["class_name"],
            manager_name=r["manager_name"]
        )
        bw = _eval_bw(voy.revised_eta_utc, voy.berth_window_start_utc, voy.berth_window_end_utc)

        # Risk scoring
        risk_score = 0
        risk_factors: List[RiskFactor] = []

        if bw.verdict in (BerthVerdict.LATE, BerthVerdict.EARLY):
            pts = 35
            risk_score += pts
            risk_factors.append(RiskFactor(
                kind="ETA_OUTSIDE_WINDOW",
                detail=f"ETA misses berth window ({bw.verdict.value}, margin: {bw.margin_hours}h)",
                points=pts,
                tier=Tier.RECORD
            ))

        if voy.recorded_delay_hours and voy.recorded_delay_hours >= 12.0:
            pts = 25
            risk_score += pts
            risk_factors.append(RiskFactor(
                kind="LARGE_ETA_SLIP",
                detail=f"Recorded delay of {voy.recorded_delay_hours}h",
                points=pts,
                tier=Tier.RECORD
            ))

        for inc in r.get("incident_items", []):
            if inc.get("status") == "Confirmed":
                pts = 25
                risk_score += pts
                risk_factors.append(RiskFactor(
                    kind="CONFIRMED_INCIDENT",
                    detail=f"Confirmed incident {inc.get('id')}: {inc.get('type')}",
                    points=pts,
                    tier=Tier.CONFIRMED
                ))
            else:
                pts = 10
                risk_score += pts
                risk_factors.append(RiskFactor(
                    kind="UNVERIFIED_INCIDENT",
                    detail=f"Unverified/Reported incident {inc.get('id')}: {inc.get('type')}",
                    points=pts,
                    tier=Tier.UNVERIFIED
                ))

        risk_score = min(risk_score, 100)

        if args.only_risky and (bw.verdict == BerthVerdict.INSIDE_WINDOW and risk_score < max(args.min_risk, 1)):
            continue
        if risk_score < args.min_risk:
            continue

        rows.append(ScanRow(
            rank=0,
            voyage=voy,
            vessel=v_prof,
            origin_code=r["orig_code"],
            dest_code=r["dest_code"],
            berth_window=bw,
            risk_score=risk_score,
            risk_factors=risk_factors
        ))

    # Sorting
    if args.rank_by == "berth_risk":
        rows.sort(key=lambda x: (x.risk_score, x.berth_window.margin_hours or 0.0), reverse=True)
    elif args.rank_by == "delay":
        rows.sort(key=lambda x: x.voyage.recorded_delay_hours or 0.0, reverse=True)
    elif args.rank_by == "eta":
        rows.sort(key=lambda x: x.voyage.revised_eta_utc or datetime.max.replace(tzinfo=timezone.utc))

    # Assign ranks
    matched_total = len(rows)
    trimmed_rows = rows[:args.limit]
    for idx, row in enumerate(trimmed_rows, start=1):
        row.rank = idx

    # Congestion snapshot at dest_port if requested
    dest_cg: List[CongestionNode] = []
    if dest_code:
        cg_cypher = """
        MATCH (p:Port {port_code: $dest_code})-[:HAS_CONGESTION]->(cg:Congestion)
        WHERE toString(cg.date_utc) <= '2026-10-26'
        RETURN cg.congestion_id AS congestion_id,
               $dest_code AS port_code,
               cg.date_utc AS date_utc,
               cg.congestion_level AS congestion_level,
               cg.avg_wait_hours AS avg_wait_hours,
               cg.vessels_at_anchor AS vessels_at_anchor
        ORDER BY cg.date_utc DESC
        LIMIT 3
        """
        recs = client.execute_read_query(cg_cypher, {"dest_code": dest_code})
        for rec in recs:
            d_val = rec["date_utc"]
            if hasattr(d_val, "to_native"):
                d_val = d_val.to_native()
            elif isinstance(d_val, str):
                d_val = datetime.strptime(d_val[:10], "%Y-%m-%d").date()
            dest_cg.append(CongestionNode(
                congestion_id=rec["congestion_id"],
                port_code=rec["port_code"],
                date_utc=d_val,
                congestion_level=rec["congestion_level"],
                avg_wait_hours=rec.get("avg_wait_hours"),
                vessels_at_anchor=rec.get("vessels_at_anchor")
            ))

    res = ScanVoyagesResult(
        rows=trimmed_rows,
        matched_total=matched_total,
        dest_congestion_snapshot=dest_cg
    )
    return render_scan_voyages(res)


# =============================================================================
# Legacy preserved helpers
# =============================================================================

def search_voyages(
    client: DatabaseClientProtocol,
    voyage_id: Optional[str] = None,
    vessel_id: Optional[str] = None,
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    status: Optional[str] = None,
    min_delay_hours: Optional[float] = None,
    limit: int = 50
) -> Dict[str, Any]:
    """Legacy helper for search_voyages."""
    cypher = """
    MATCH (v:Vessel)-[:OPERATES_VOYAGE]->(voy:Voyage)
    MATCH (voy)-[:DEPARTS_FROM]->(orig:Port)
    MATCH (voy)-[:ARRIVES_AT]->(dest:Port)
    WHERE ($voyage_id IS NULL OR voy.voyage_id = $voyage_id)
      AND ($vessel_id IS NULL OR v.vessel_id = $vessel_id)
      AND ($origin IS NULL OR orig.port_code = $origin OR toLower(orig.name) CONTAINS toLower($origin))
      AND ($destination IS NULL OR dest.port_code = $destination OR toLower(dest.name) CONTAINS toLower($destination))
      AND ($status IS NULL OR toLower(voy.status) = toLower($status))
      AND ($min_delay_hours IS NULL OR voy.recorded_delay_hours >= $min_delay_hours)
    RETURN voy.voyage_id AS voyage_id,
           v.vessel_id AS vessel_id,
           v.name AS vessel_name,
           orig.port_code AS origin_code,
           orig.name AS origin_port,
           dest.port_code AS destination_code,
           dest.name AS destination_port,
           toString(voy.departure_utc) AS departure_utc,
           toString(voy.revised_eta_utc) AS revised_eta_utc,
           voy.status AS status,
           voy.recorded_delay_hours AS recorded_delay_hours
    ORDER BY voy.departure_utc DESC
    LIMIT $limit
    """
    records = client.execute_read_query(cypher, {
        "voyage_id": voyage_id,
        "vessel_id": vessel_id,
        "origin": origin,
        "destination": destination,
        "status": status,
        "min_delay_hours": min_delay_hours,
        "limit": limit
    })
    return {"status": "SUCCESS", "success": True, "count": len(records), "voyages": records}


def get_voyage_timeline(client: DatabaseClientProtocol, voyage_id: str) -> Dict[str, Any]:
    """Legacy helper for voyage timeline."""
    args = GetVoyageContextInput(voyage_id=voyage_id)
    resp = get_voyage_context(client, args)
    return {"voyage_id": voyage_id, "text": resp.to_agent_text(), "status": resp.status.value}
