"""Booking and cargo exposure domain tools for Maritime Knowledge Graph MCP server.
Provides get_cargo_exposure (voyage and customer cargo impact analysis)
alongside preserved track_booking and get_rolled_bookings helpers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from utility.dependencies import DatabaseClientProtocol
from utility.logger import get_logger
from knowledge_graph.maritime_kg_mcp.models import (
    BookingLine,
    BookingNode,
    CustomerExposure,
    CustomerNode,
    DelayReconciliation,
    GetCargoExposureInput,
    GetCargoExposureResult,
    PortNode,
    ToolResponse,
    VesselNode,
    VoyageNode,
)
from knowledge_graph.maritime_kg_mcp.renderer import (
    render_ambiguous,
    render_cargo_exposure,
    render_no_data,
)
from knowledge_graph.maritime_kg_mcp.resolver import resolve_vessel

logger = get_logger(__name__)


def get_cargo_exposure(
    client: DatabaseClientProtocol, args: GetCargoExposureInput
) -> ToolResponse:
    """Calculates customer container volumes, rolled bookings, and promised-date delay risks for a voyage."""
    voyage_id = args.voyage_id

    # Resolve voyage from vessel if voyage_id is not provided directly
    if not voyage_id and args.vessel:
        v_node, amb = resolve_vessel(client, args.vessel)
        if amb:
            return render_ambiguous(amb)
        if not v_node:
            return render_no_data({"vessel": args.vessel})

        status_filter = "voy.status IN ['Delayed', 'On schedule']" if args.which == "current" else (
            "voy.status = 'Scheduled'" if args.which == "next" else "true"
        )
        voy_lookup = f"""
        MATCH (v:Vessel {{vessel_id: $vid}})-[:OPERATES_VOYAGE]->(voy:Voyage)
        WHERE {status_filter}
        RETURN voy.voyage_id AS voyage_id
        ORDER BY voy.departure_utc DESC
        LIMIT 1
        """
        recs = client.execute_read_query(voy_lookup, {"vid": v_node.vessel_id})
        if recs:
            voyage_id = recs[0]["voyage_id"]
        else:
            return render_no_data({"vessel": args.vessel, "which": args.which})

    if not voyage_id:
        return render_no_data({"voyage_id": "None provided"})

    # 1. Fetch Voyage Core Info
    voy_cypher = """
    MATCH (voy:Voyage {voyage_id: $vid})
    MATCH (v:Vessel)-[:OPERATES_VOYAGE]->(voy)
    MATCH (voy)-[:ARRIVES_AT]->(dest:Port)
    RETURN voy.voyage_id AS voyage_id,
           voy.status AS status,
           voy.departure_utc AS departure_utc,
           voy.original_eta_utc AS original_eta_utc,
           voy.revised_eta_utc AS revised_eta_utc,
           voy.recorded_delay_hours AS recorded_delay_hours,
           v.vessel_id AS vessel_id, v.name AS vessel_name, v.imo AS vessel_imo,
           dest.port_code AS dest_code, dest.name AS dest_name, dest.country AS dest_country, dest.timezone AS dest_tz
    """
    voy_recs = client.execute_read_query(voy_cypher, {"vid": voyage_id})
    if not voy_recs:
        return render_no_data({"voyage_id": voyage_id})

    vr = voy_recs[0]
    voy_node = VoyageNode(
        voyage_id=vr["voyage_id"],
        status=vr["status"],
        departure_utc=vr.get("departure_utc"),
        original_eta_utc=vr.get("original_eta_utc"),
        revised_eta_utc=vr.get("revised_eta_utc"),
        recorded_delay_hours=vr.get("recorded_delay_hours")
    )
    v_node = VesselNode(vessel_id=vr["vessel_id"], name=vr["vessel_name"], imo=vr["vessel_imo"])
    dest_node = PortNode(
        port_code=vr["dest_code"],
        name=vr["dest_name"],
        country=vr["dest_country"],
        timezone=vr.get("dest_tz", "UTC")
    )

    # 2. Fetch Bookings and Customers
    bk_cypher = """
    MATCH (b:Booking)-[:BOOKED_ON]->(voy:Voyage {voyage_id: $vid})
    MATCH (c:Customer)-[:PLACED_BOOKING]->(b)
    OPTIONAL MATCH (b)-[:ROLLED_TO]->(targetVoy:Voyage)
    WHERE ($customer IS NULL
           OR toLower(c.customer_id) = toLower($customer)
           OR toLower(c.name) CONTAINS toLower($customer))
    RETURN b.booking_id AS booking_id,
           b.containers AS containers,
           b.status AS status,
           b.promised_delivery_date_utc AS promised_delivery_date_utc,
           coalesce(b.is_rolled, false) AS is_rolled,
           targetVoy.voyage_id AS rolled_to_voyage_id,
           c.customer_id AS customer_id,
           c.name AS customer_name,
           c.industry_segment AS industry_segment
    ORDER BY c.name, b.booking_id
    """
    records = client.execute_read_query(bk_cypher, {"vid": voyage_id, "customer": args.customer})

    # Group bookings by customer
    customers_map: Dict[str, Dict[str, Any]] = {}
    total_on_board = 0
    total_rolled = 0
    total_cancelled = 0

    revised_eta = voy_node.revised_eta_utc

    for r in records:
        cid = r["customer_id"]
        if cid not in customers_map:
            customers_map[cid] = {
                "node": CustomerNode(
                    customer_id=cid,
                    name=r["customer_name"],
                    industry_segment=r.get("industry_segment")
                ),
                "on_board": 0,
                "rolled": 0,
                "cancelled": 0,
                "bookings": []
            }

        cnts = int(r["containers"] or 0)
        status_str = r["status"]
        is_rolled = bool(r["is_rolled"]) or status_str.startswith("Rolled")

        if is_rolled:
            customers_map[cid]["rolled"] += cnts
            total_rolled += cnts
        elif status_str == "Cancelled":
            customers_map[cid]["cancelled"] += cnts
            total_cancelled += cnts
        else:
            customers_map[cid]["on_board"] += cnts
            total_on_board += cnts

        p_date = r.get("promised_delivery_date_utc")
        if hasattr(p_date, "to_native"):
            p_date = p_date.to_native()
        elif isinstance(p_date, str):
            p_date = datetime.strptime(p_date[:10], "%Y-%m-%d").date()

        days_margin: Optional[float] = None
        promise_at_risk: Optional[bool] = None

        if p_date and revised_eta:
            # End of day UTC for promised date
            p_dt = datetime(p_date.year, p_date.month, p_date.day, 23, 59, 59, tzinfo=timezone.utc)
            days_margin = round((p_dt - revised_eta).total_seconds() / 86400.0, 1)
            promise_at_risk = days_margin < 0

        b_node = BookingNode(
            booking_id=r["booking_id"],
            containers=cnts,
            status=status_str,
            promised_delivery_date_utc=p_date,
            is_rolled=is_rolled
        )

        customers_map[cid]["bookings"].append(BookingLine(
            booking=b_node,
            rolled_to_voyage_id=r.get("rolled_to_voyage_id"),
            original_voyage_id=voyage_id,
            days_between_eta_and_promise=days_margin,
            promise_at_risk=promise_at_risk
        ))

    # Assemble CustomerExposure list, sorted by on_board_containers desc
    cust_exposures = [
        CustomerExposure(
            customer=data["node"],
            on_board_containers=data["on_board"],
            rolled_containers=data["rolled"],
            cancelled_containers=data["cancelled"],
            bookings=data["bookings"]
        )
        for data in customers_map.values()
    ]
    cust_exposures.sort(key=lambda x: x.on_board_containers, reverse=True)

    result = GetCargoExposureResult(
        voyage=voy_node,
        vessel=v_node,
        destination=dest_node,
        customers=cust_exposures,
        total_on_board=total_on_board,
        total_rolled=total_rolled,
        total_cancelled=total_cancelled,
        delay=DelayReconciliation(
            recorded_delay_hours=voy_node.recorded_delay_hours,
            discrepancy=False
        )
    )
    return render_cargo_exposure(result)


# =============================================================================
# Legacy preserved helpers
# =============================================================================

def track_booking(
    client: DatabaseClientProtocol,
    booking_id: Optional[str] = None,
    customer_name: Optional[str] = None,
    voyage_id: Optional[str] = None,
    limit: int = 50
) -> Dict[str, Any]:
    """Preserved tool for direct commercial booking tracking by ID, customer name, or assigned voyage."""
    cypher = """
    MATCH (b:Booking)
    MATCH (c:Customer)-[:PLACED_BOOKING]->(b)
    MATCH (b)-[:BOOKED_ON]->(voy:Voyage)
    MATCH (v:Vessel)-[:OPERATES_VOYAGE]->(voy)
    MATCH (voy)-[:DEPARTS_FROM]->(orig:Port)
    MATCH (voy)-[:ARRIVES_AT]->(dest:Port)
    OPTIONAL MATCH (b)-[:ROLLED_TO]->(rolledVoy:Voyage)
    WHERE ($booking_id IS NULL OR b.booking_id = $booking_id)
      AND ($customer_name IS NULL OR toLower(c.name) CONTAINS toLower($customer_name))
      AND ($voyage_id IS NULL OR voy.voyage_id = $voyage_id)
    RETURN b.booking_id AS booking_id,
           c.name AS customer,
           b.containers AS containers,
           b.status AS status,
           toString(b.promised_delivery_date_utc) AS promised_delivery_date_utc,
           coalesce(b.is_rolled, false) AS is_rolled,
           voy.voyage_id AS booked_voyage_id,
           v.name AS vessel_name,
           orig.port_code AS origin,
           dest.port_code AS destination,
           toString(voy.revised_eta_utc) AS scheduled_eta_utc,
           rolledVoy.voyage_id AS rolled_to_voyage_id
    ORDER BY b.booking_id
    LIMIT $limit
    """
    records = client.execute_read_query(cypher, {
        "booking_id": booking_id,
        "customer_name": customer_name,
        "voyage_id": voyage_id,
        "limit": limit
    })
    return {"status": "SUCCESS", "success": True, "count": len(records), "bookings": records}


def get_rolled_bookings(client: DatabaseClientProtocol, limit: int = 50) -> Dict[str, Any]:
    """Legacy helper retrieving rolled container bookings."""
    cypher = """
    MATCH (b:Booking)
    WHERE coalesce(b.is_rolled, false) = true OR b.status STARTS WITH 'Rolled'
    MATCH (c:Customer)-[:PLACED_BOOKING]->(b)
    MATCH (b)-[:BOOKED_ON]->(origVoy:Voyage)
    OPTIONAL MATCH (b)-[:ROLLED_TO]->(targetVoy:Voyage)
    RETURN b.booking_id AS booking_id,
           c.name AS customer,
           b.containers AS containers,
           b.status AS status,
           toString(b.promised_delivery_date_utc) AS promised_delivery_date_utc,
           origVoy.voyage_id AS original_voyage_id,
           targetVoy.voyage_id AS rolled_to_voyage_id
    ORDER BY b.booking_id
    LIMIT $limit
    """
    records = client.execute_read_query(cypher, {"limit": limit})
    return {"total": len(records), "rolled_bookings": records}
