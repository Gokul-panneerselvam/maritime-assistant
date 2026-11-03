"""Graph-text renderer for Maritime Knowledge Graph tool results.
Transforms typed Pydantic result models into structured graph-text with nodes,
relationships, evidence tiers, and standardized citable tags.
Adheres to SOLID principles: Single responsibility for formatting agent responses.
"""

from __future__ import annotations

from typing import List, Set
from knowledge_graph.maritime_kg_mcp.models import (
    AmbiguityOption,
    GetCargoExposureResult,
    GetIncidentHistoryResult,
    GetPortContextResult,
    GetVesselContextResult,
    GetVoyageContextResult,
    ScanVoyagesResult,
    SearchMessagesResult,
    Status,
    Tier,
    ToolResponse,
)


def _fmt_dt(dt) -> str:
    if dt is None:
        return "None"
    if hasattr(dt, "strftime"):
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(dt)


def render_no_data(searched: dict) -> ToolResponse:
    """Produces a standard NO_DATA envelope."""
    return ToolResponse(
        status=Status.NO_DATA,
        text="",
        citations=[],
        searched=searched
    )


def render_ambiguous(options: List[AmbiguityOption]) -> ToolResponse:
    """Produces a standard AMBIGUOUS envelope."""
    return ToolResponse(
        status=Status.AMBIGUOUS,
        text="",
        citations=[],
        ambiguity=options
    )


def render_error(error_message: str) -> ToolResponse:
    """Produces a standard ERROR envelope."""
    return ToolResponse(
        status=Status.ERROR,
        text=error_message,
        citations=[]
    )


# =============================================================================
# 1. Render Voyage Context
# =============================================================================

def render_voyage_context(res: GetVoyageContextResult) -> ToolResponse:
    if not res.dossiers:
        return render_no_data({"query": "voyage_context"})

    lines: List[str] = []
    citations: Set[str] = set()
    hints: List[str] = []

    for dossier in res.dossiers:
        v = dossier.vessel
        voy = dossier.voyage
        citations.add(f"Voyage:{voy.voyage_id}")
        citations.add(f"Vessel:{v.vessel_id}")
        citations.add(f"Port:{dossier.origin.port_code}")
        citations.add(f"Port:{dossier.destination.port_code}")

        lines.append(f"VOYAGE: {voy.voyage_id} [RECORD]")
        lines.append(f"  status: {voy.status}")
        lines.append(f"  vessel: {v.name} ({v.vessel_id}, IMO: {v.imo}) | class: {v.class_name} | manager: {v.manager_name}")
        lines.append(f"  route: {dossier.origin.name} ({dossier.origin.port_code}) -> {dossier.destination.name} ({dossier.destination.port_code})")
        lines.append(f"  departure_utc: {_fmt_dt(voy.departure_utc)}")
        lines.append(f"  original_eta_utc: {_fmt_dt(voy.original_eta_utc)}")
        lines.append(f"  revised_eta_utc: {_fmt_dt(voy.revised_eta_utc)} (local: {voy.revised_eta_local or 'N/A'})")
        lines.append(f"  berth_window_utc: {_fmt_dt(voy.berth_window_start_utc)} .. {_fmt_dt(voy.berth_window_end_utc)}")

        # Computed berth verdict
        bw = dossier.berth_window
        margin_str = f" ({bw.margin_hours:+.1f}h)" if bw.margin_hours is not None else ""
        lines.append(f"  computed: berth_window_verdict = {bw.verdict.value}{margin_str}")

        # Computed delay reconciliation
        d = dossier.delay
        discrep_str = " [DISCREPANCY DETECTED]" if d.discrepancy else ""
        lines.append(f"  computed: delay_reconciliation = recorded:{d.recorded_delay_hours}h | eta_slip:{d.eta_slip_hours}h | confirmed_incidents:{d.confirmed_attributed_hours}h | anchorage_wait:{d.anchorage_wait_hours}h | unexplained:{d.unexplained_hours}h{discrep_str}")

        # Port calls
        if dossier.port_calls:
            lines.append("  PORT CALLS:")
            for pc in dossier.port_calls:
                citations.add(f"PortCall:{pc.call_id}")
                lines.append(f"    - [{pc.call_id}] {pc.call_type} @ {pc.port_code} | anchor: {_fmt_dt(pc.anchorage_arrival_utc)} | berth: {_fmt_dt(pc.berthing_utc)} | wait: {pc.anchorage_wait_hours or 0.0}h")

        # Congestion around ETA
        if dossier.destination_congestion:
            lines.append("  DESTINATION CONGESTION AROUND ETA:")
            for c in dossier.destination_congestion:
                citations.add(f"Congestion:{c.congestion_id}")
                lines.append(f"    - {c.date_utc}: {c.congestion_level} (avg wait: {c.avg_wait_hours or 0.0}h, at anchor: {c.vessels_at_anchor or 0})")

        # Incidents
        if dossier.incidents:
            lines.append("  INCIDENTS:")
            for inc_ev in dossier.incidents:
                inc = inc_ev.incident
                citations.add(f"Incident:{inc.incident_id}")
                lines.append(f"    - [{inc.incident_id}] [{inc_ev.tier.value}] {inc.type} | severity: {inc.severity} | status: {inc.status} | delay: {inc.attributed_delay_hours or 0.0}h | source: {inc.source}")
                for link in inc_ev.links:
                    msg = link.message
                    citations.add(f"File:{msg.filename}")
                    body_hint = f"\"{msg.snippet}\"" if msg.snippet else ""
                    lines.append(f"        -> [{link.edge_type}] File:{msg.filename} ({msg.trust_tier}, {_fmt_dt(msg.sent_at_utc)}): {body_hint}")
                for note in inc_ev.superseded_notes:
                    lines.append(f"        * correction: {note}")

        # Messages about voyage
        if dossier.messages_about_voyage:
            lines.append("  VOYAGE MESSAGES:")
            for link in dossier.messages_about_voyage:
                msg = link.message
                citations.add(f"File:{msg.filename}")
                lines.append(f"    - [{link.edge_type}] File:{msg.filename} ({msg.trust_tier}, {_fmt_dt(msg.sent_at_utc)}): {msg.subject}")

        # Bookings Summary
        if dossier.bookings:
            b = dossier.bookings
            lines.append(f"  BOOKINGS SUMMARY: {b.customers} customers | confirmed: {b.total_containers_confirmed} TEU | rolled: {b.total_containers_rolled} TEU | cancelled: {b.total_containers_cancelled} TEU")

        # Gaps
        if dossier.gaps:
            lines.append("  OPERATIONAL GAPS TO CHECK:")
            for g in dossier.gaps:
                lines.append(f"    - [{g.kind}] {g.detail} (related: {', '.join(g.related_ids)})")

        lines.append("")

    if res.matched_total > len(res.dossiers):
        hints.append(f"Matched {res.matched_total} voyages in total; showing top {len(res.dossiers)}. Narrow filters to inspect others.")

    return ToolResponse(
        status=Status.OK,
        text="\n".join(lines).strip(),
        citations=sorted(list(citations)),
        truncated=(res.matched_total > len(res.dossiers)),
        next_hints=hints
    )


# =============================================================================
# 2. Render Vessel Context
# =============================================================================

def render_vessel_context(res: GetVesselContextResult) -> ToolResponse:
    v = res.vessel
    citations: Set[str] = {f"Vessel:{v.vessel_id}"}
    lines: List[str] = [
        f"VESSEL PROFILE: {v.name} ({v.vessel_id}) [RECORD]",
        f"  imo: {v.imo} | type: {v.type_name} | class: {v.class_name} | manager: {v.manager_name}",
    ]

    if res.current_voyage_id:
        citations.add(f"Voyage:{res.current_voyage_id}")
        lines.append(f"  current_active_voyage: {res.current_voyage_id}")

    if res.sister_vessels:
        sister_names = [f"{s.name} ({s.vessel_id})" for s in res.sister_vessels]
        lines.append(f"  sister_ships ({v.class_name}): {', '.join(sister_names)}")

    if res.manager_fleet:
        fleet_names = [f"{m.name} ({m.vessel_id})" for m in res.manager_fleet]
        lines.append(f"  manager_fleet ({v.manager_name}): {', '.join(fleet_names)}")

    if res.timeline:
        lines.append("  VOYAGE TIMELINE:")
        for row in res.timeline:
            voy = row.voyage
            citations.add(f"Voyage:{voy.voyage_id}")
            bw = row.berth_window
            lines.append(f"    - [{voy.voyage_id}] {row.origin_code} -> {row.dest_code} | status: {voy.status} | ETA: {_fmt_dt(voy.revised_eta_utc)} | berth: {bw.verdict.value} | incidents: {len(row.incident_ids)}")

    if res.incidents:
        lines.append("  VESSEL INCIDENT HISTORY:")
        for inc_ev in res.incidents:
            inc = inc_ev.incident
            citations.add(f"Incident:{inc.incident_id}")
            lines.append(f"    - [{inc.incident_id}] [{inc_ev.tier.value}] {inc.type} | status: {inc.status} | delay: {inc.attributed_delay_hours or 0.0}h")

    if res.class_messages:
        lines.append(f"  CLASS BULLETINS ({v.class_name}):")
        for link in res.class_messages:
            msg = link.message
            citations.add(f"File:{msg.filename}")
            lines.append(f"    - [{link.edge_type}] File:{msg.filename} ({msg.trust_tier}): {msg.subject}")

    if res.vessel_messages:
        lines.append("  RECENT MESSAGES:")
        for link in res.vessel_messages:
            msg = link.message
            citations.add(f"File:{msg.filename}")
            lines.append(f"    - [{link.edge_type}] File:{msg.filename} ({msg.trust_tier}, {_fmt_dt(msg.sent_at_utc)}): {msg.subject}")

    return ToolResponse(
        status=Status.OK,
        text="\n".join(lines).strip(),
        citations=sorted(list(citations)),
        next_hints=["Call get_voyage_context(voyage_id=...) for deep operational analysis on specific voyages."]
    )


# =============================================================================
# 3. Render Incident History
# =============================================================================

def render_incident_history(res: GetIncidentHistoryResult) -> ToolResponse:
    lines: List[str] = [
        f"INCIDENT RECURRENCE ANALYSIS",
        f"  pattern: {res.pattern}"
    ]
    citations: Set[str] = set()

    for sc in res.scopes:
        lines.append(f"  SCOPE [{sc.scope.upper()}]: {sc.scope_label}")
        lines.append(f"    matches: {sc.total_matches} across {sc.distinct_vessels} distinct vessels | confirmed delay sum: {sc.total_attributed_delay_hours:.1f}h")
        for inc_ev in sc.incidents:
            inc = inc_ev.incident
            citations.add(f"Incident:{inc.incident_id}")
            v_str = f"vessel: {inc_ev.vessel.name} ({inc_ev.vessel.vessel_id})" if inc_ev.vessel else ""
            lines.append(f"      - [{inc.incident_id}] [{inc_ev.tier.value}] {inc.type} | status: {inc.status} | delay: {inc.attributed_delay_hours or 0.0}h | {v_str}")
            for link in inc_ev.links:
                citations.add(f"File:{link.message.filename}")
                lines.append(f"          -> File:{link.message.filename} ({link.message.trust_tier}): {link.message.subject}")

    if res.bulletins:
        lines.append("  MATCHING BULLETINS & TECHNICAL ADVISORIES:")
        for link in res.bulletins:
            msg = link.message
            citations.add(f"File:{msg.filename}")
            lines.append(f"    - File:{msg.filename} ({msg.trust_tier}): {msg.subject}")

    if res.correction_chain_notes:
        lines.append("  CORRECTION CHAINS:")
        for note in res.correction_chain_notes:
            lines.append(f"    * {note}")

    return ToolResponse(
        status=Status.OK,
        text="\n".join(lines).strip(),
        citations=sorted(list(citations))
    )


# =============================================================================
# 4. Render Cargo Exposure
# =============================================================================

def render_cargo_exposure(res: GetCargoExposureResult) -> ToolResponse:
    voy = res.voyage
    v = res.vessel
    p = res.destination
    citations: Set[str] = {f"Voyage:{voy.voyage_id}", f"Vessel:{v.vessel_id}", f"Port:{p.port_code}"}

    lines: List[str] = [
        f"CARGO EXPOSURE: Voyage {voy.voyage_id} ({v.name}) -> {p.name} ({p.port_code})",
        f"  revised_eta_utc: {_fmt_dt(voy.revised_eta_utc)} | recorded_delay: {voy.recorded_delay_hours or 0.0}h",
        f"  TOTAL CONTAINERS: on-board: {res.total_on_board} TEU | rolled: {res.total_rolled} TEU | cancelled: {res.total_cancelled} TEU",
        "  (RULE: Rolled containers have been pushed to later sailings and are NOT on board)",
        "  CUSTOMER BREAKDOWN:"
    ]

    for cust_exp in res.customers:
        c = cust_exp.customer
        citations.add(f"Customer:{c.customer_id}")
        lines.append(f"    - CUSTOMER: {c.name} ({c.industry_segment or 'General Cargo'})")
        lines.append(f"      on-board: {cust_exp.on_board_containers} TEU | rolled: {cust_exp.rolled_containers} TEU | cancelled: {cust_exp.cancelled_containers} TEU")
        for b_line in cust_exp.bookings:
            b = b_line.booking
            citations.add(f"Booking:{b.booking_id}")
            risk_label = " [AT RISK / LATE]" if b_line.promise_at_risk else " [ON TRACK]"
            margin_str = f" ({b_line.days_between_eta_and_promise:+.1f} days margin)" if b_line.days_between_eta_and_promise is not None else ""
            rolled_str = f" -> rolled to {b_line.rolled_to_voyage_id}" if b_line.rolled_to_voyage_id else ""
            lines.append(f"        * [{b.booking_id}] {b.containers} TEU | status: {b.status}{rolled_str} | promised: {b.promised_delivery_date_utc}{margin_str}{risk_label}")

    return ToolResponse(
        status=Status.OK,
        text="\n".join(lines).strip(),
        citations=sorted(list(citations))
    )


# =============================================================================
# 5. Render Scan Voyages
# =============================================================================

def render_scan_voyages(res: ScanVoyagesResult) -> ToolResponse:
    lines: List[str] = [
        f"VOYAGE SCAN RESULTS: {len(res.rows)} of {res.matched_total} matched voyages",
        f"  note: {res.scoring_note}"
    ]
    citations: Set[str] = set()

    if res.dest_congestion_snapshot:
        lines.append("  DESTINATION CONGESTION SNAPSHOT:")
        for cg in res.dest_congestion_snapshot:
            citations.add(f"Congestion:{cg.congestion_id}")
            lines.append(f"    - {cg.date_utc} @ {cg.port_code}: {cg.congestion_level} (avg wait: {cg.avg_wait_hours or 0.0}h, at anchor: {cg.vessels_at_anchor or 0})")

    lines.append("  RANKED VOYAGES:")
    for r in res.rows:
        voy = r.voyage
        v = r.vessel
        citations.add(f"Voyage:{voy.voyage_id}")
        citations.add(f"Vessel:{v.vessel_id}")
        bw = r.berth_window
        lines.append(f"    #{r.rank} [{voy.voyage_id}] {v.name} ({v.vessel_id}, {v.class_name}) | {r.origin_code} -> {r.dest_code}")
        lines.append(f"       status: {voy.status} | ETA: {_fmt_dt(voy.revised_eta_utc)} | berth: {bw.verdict.value} ({bw.margin_hours or 0.0:+.1f}h) | risk_score: {r.risk_score}/100")
        if r.risk_factors:
            for rf in r.risk_factors:
                lines.append(f"         * [{rf.tier.value}] +{rf.points} pts: {rf.kind} ({rf.detail})")

    return ToolResponse(
        status=Status.OK,
        text="\n".join(lines).strip(),
        citations=sorted(list(citations)),
        truncated=(res.matched_total > len(res.rows)),
        next_hints=["Call get_voyage_context(voyage_id=...) on top-ranked risky voyages for full investigation."]
    )


# =============================================================================
# 6. Render Port Context
# =============================================================================

def render_port_context(res: GetPortContextResult) -> ToolResponse:
    p = res.port
    citations: Set[str] = {f"Port:{p.port_code}"}
    lines: List[str] = [
        f"PORT CONTEXT: {p.name} ({p.port_code}, {p.country}) [RECORD]",
        f"  timezone: {p.timezone}",
    ]

    if res.agents:
        agent_names = [f"{a.name} ({a.org_id})" for a in res.agents]
        lines.append(f"  port_agents: {', '.join(agent_names)}")

    if res.congestion_summary:
        cs = res.congestion_summary
        lines.append(f"  congestion_summary: peak: {cs.get('peak_level')} on {cs.get('peak_date')} | avg_wait: {cs.get('avg_wait_hours', 0.0):.1f}h | max_at_anchor: {cs.get('max_vessels_at_anchor', 0)}")

    if res.congestion:
        lines.append("  CONGESTION LOGS:")
        for c in res.congestion:
            citations.add(f"Congestion:{c.congestion_id}")
            lines.append(f"    - {c.date_utc}: {c.congestion_level} (avg wait: {c.avg_wait_hours or 0.0}h, vessels: {c.vessels_at_anchor or 0})")

    if res.inbound_voyages:
        lines.append("  INBOUND VOYAGES IN WINDOW:")
        for iv in res.inbound_voyages:
            citations.add(f"Voyage:{iv.voyage.voyage_id}")
            citations.add(f"Vessel:{iv.vessel.vessel_id}")
            lines.append(f"    - [{iv.voyage.voyage_id}] {iv.vessel.name} | ETA: {_fmt_dt(iv.voyage.revised_eta_utc)} | berth: {iv.berth_window.verdict.value}")

    if res.port_calls:
        lines.append("  RECORDED PORT CALLS:")
        for pc_row in res.port_calls:
            call = pc_row.call
            citations.add(f"PortCall:{call.call_id}")
            lines.append(f"    - [{call.call_id}] {call.call_type} by {pc_row.vessel.name} | anchor wait: {call.anchorage_wait_hours or 0.0}h | stay: {call.port_stay_hours or 0.0}h")

    if res.messages:
        lines.append("  PORT COMMUNICATIONS:")
        for link in res.messages:
            msg = link.message
            citations.add(f"File:{msg.filename}")
            lines.append(f"    - [{link.edge_type}] File:{msg.filename} ({msg.trust_tier}): {msg.subject}")

    if res.gaps:
        lines.append("  OPERATIONAL GAPS:")
        for g in res.gaps:
            lines.append(f"    - [{g.kind}] {g.detail}")

    return ToolResponse(
        status=Status.OK,
        text="\n".join(lines).strip(),
        citations=sorted(list(citations))
    )


# =============================================================================
# 7. Render Search Messages
# =============================================================================

def render_search_messages(res: SearchMessagesResult) -> ToolResponse:
    if not res.hits:
        return render_no_data({"query": "search_messages"})

    citations: Set[str] = set()
    lines: List[str] = [
        f"MESSAGE SEARCH RESULTS: {len(res.hits)} matching records (total: {res.total_matches})"
    ]

    if res.flagged_malicious_count > 0:
        lines.append(f"  [SECURITY WARNING: {res.flagged_malicious_count} message(s) flagged for potential malicious or prompt-injection content. Bodies withheld.]")

    for hit in res.hits:
        m = hit.message
        citations.add(f"File:{m.filename}")
        lines.append(f"  MESSAGE: File:{m.filename} (ID: {m.message_id})")
        lines.append(f"    trust_tier: {m.trust_tier} | kind: {m.message_kind} | sent_at_utc: {_fmt_dt(m.sent_at_utc)}")
        lines.append(f"    sender: {m.sender} | subject: {m.subject}")

        if hit.linked:
            lines.append(f"    connected_edges: {', '.join(hit.linked)}")

        # If detailed view (queried by message_id or filename)
        if res.detailed_view or hit.body:
            if m.is_malicious:
                lines.append("    body: [WITHHELD: Message flagged for potential security or injection content]")
            else:
                body_content = hit.body or m.cleaned_body or m.snippet or ""
                lines.append(f"    body:\n      " + body_content.replace("\n", "\n      "))
        else:
            if m.is_malicious:
                lines.append("    snippet: [WITHHELD: Message flagged for security]")
            elif m.snippet:
                lines.append(f"    snippet: \"{m.snippet}\"")

        lines.append("")

    return ToolResponse(
        status=Status.OK,
        text="\n".join(lines).strip(),
        citations=sorted(list(citations)),
        truncated=(res.total_matches > len(res.hits))
    )

