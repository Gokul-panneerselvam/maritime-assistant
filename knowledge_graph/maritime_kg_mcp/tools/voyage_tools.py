import logging
from typing import Any, Dict, Optional
from knowledge_graph.database import Neo4jClient

logger = logging.getLogger(__name__)

SEARCH_VOYAGES_CYPHER = """
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

GET_VOYAGE_TIMELINE_CYPHER = """
MATCH (voy:Voyage {voyage_id: $voyage_id})
MATCH (v:Vessel)-[:OPERATES_VOYAGE]->(voy)
MATCH (voy)-[:DEPARTS_FROM]->(orig:Port)
MATCH (voy)-[:ARRIVES_AT]->(dest:Port)

OPTIONAL MATCH (voy)-[:HAS_PORT_CALL]->(pc:PortCall)
OPTIONAL MATCH (pc)-[:AT_PORT]->(pcPort:Port)
WITH voy, v, orig, dest, pc, pcPort
ORDER BY pc.anchorage_arrival_utc ASC, pc.berthing_utc ASC
WITH voy, v, orig, dest,
     collect(DISTINCT {
         call_id: pc.call_id,
         call_type: pc.call_type,
         port: pcPort.port_code,
         port_name: pcPort.name,
         anchorage_arrival_utc: toString(pc.anchorage_arrival_utc),
         berth_scheduled_utc: toString(pc.berth_scheduled_utc),
         berthing_utc: toString(pc.berthing_utc),
         departure_utc: toString(pc.departure_utc),
         anchorage_wait_hours: pc.anchorage_wait_hours,
         port_stay_hours: pc.port_stay_hours
     }) AS port_calls

OPTIONAL MATCH (voy)-[:EXPERIENCED_INCIDENT]->(inc:Incident)
WITH voy, v, orig, dest, port_calls,
     collect(DISTINCT {
         incident_id: inc.incident_id,
         type: inc.type,
         severity: inc.severity,
         status: inc.status,
         reported_utc: toString(inc.reported_utc),
         attributed_delay_hours: inc.attributed_delay_hours,
         source: inc.source
     }) AS incidents

OPTIONAL MATCH (b:Booking)-[:BOOKED_ON]->(voy)
OPTIONAL MATCH (c:Customer)-[:PLACED_BOOKING]->(b)
OPTIONAL MATCH (b)-[:ROLLED_TO]->(rolledVoy:Voyage)
WITH voy, v, orig, dest, port_calls, incidents,
     collect(DISTINCT {
         booking_id: b.booking_id,
         customer: c.name,
         containers: b.containers,
         status: b.status,
         promised_delivery_date_utc: toString(b.promised_delivery_date_utc),
         is_rolled: b.is_rolled,
         rolled_to_voyage: rolledVoy.voyage_id
     }) AS bookings

RETURN voy.voyage_id AS voyage_id,
       v.vessel_id AS vessel_id,
       v.name AS vessel_name,
       orig.port_code AS origin_code,
       orig.name AS origin_port,
       dest.port_code AS destination_code,
       dest.name AS destination_port,
       voy.departure_local AS departure_local,
       toString(voy.departure_utc) AS departure_utc,
       voy.original_eta_local AS original_eta_local,
       toString(voy.original_eta_utc) AS original_eta_utc,
       voy.revised_eta_local AS revised_eta_local,
       toString(voy.revised_eta_utc) AS revised_eta_utc,
       voy.status AS status,
       voy.recorded_delay_hours AS recorded_delay_hours,
       port_calls,
       incidents,
       bookings
"""

def search_voyages(
    client: Neo4jClient,
    voyage_id: Optional[str] = None,
    vessel_id: Optional[str] = None,
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    status: Optional[str] = None,
    min_delay_hours: Optional[float] = None,
    limit: int = 50
) -> Dict[str, Any]:
    """Search operational voyages with origin, destination, status, or delay filters."""
    params = {
        "voyage_id": voyage_id,
        "vessel_id": vessel_id,
        "origin": origin,
        "destination": destination,
        "status": status,
        "min_delay_hours": min_delay_hours,
        "limit": min(limit, 100)
    }
    try:
        results = client.execute_read_query(SEARCH_VOYAGES_CYPHER, params)
        if not results:
            return {
                "status": "NO_DATA",
                "message": "NO_DATA_FOUND: No voyages matched the specified search criteria.",
                "count": 0,
                "voyages": []
            }
        return {"status": "SUCCESS", "success": True, "count": len(results), "voyages": results}
    except Exception as e:
        logger.error("Error searching voyages: %s", e)
        return {"status": "NO_DATA", "success": False, "error": str(e), "message": "NO_DATA_FOUND due to query error.", "count": 0, "voyages": []}

def get_voyage_timeline(client: Neo4jClient, voyage_id: str) -> Dict[str, Any]:
    """Retrieves end-to-end voyage timeline, milestones, incidents, and freight bookings."""
    try:
        results = client.execute_read_query(GET_VOYAGE_TIMELINE_CYPHER, {"voyage_id": voyage_id.strip()})
        if not results:
            return {
                "status": "NO_DATA",
                "message": f"NO_DATA_FOUND: Voyage '{voyage_id}' was not found in the Maritime Knowledge Graph.",
                "success": False,
                "error": f"Voyage '{voyage_id}' not found.",
                "voyage_timeline": None
            }
        return {"status": "SUCCESS", "success": True, "voyage_timeline": results[0]}
    except Exception as e:
        logger.error("Error getting voyage timeline: %s", e)
        return {"status": "NO_DATA", "success": False, "error": str(e), "voyage_timeline": None}

