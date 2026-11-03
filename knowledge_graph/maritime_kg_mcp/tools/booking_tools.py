import logging
from typing import Any, Dict, Optional
from knowledge_graph.database import Neo4jClient

logger = logging.getLogger(__name__)

TRACK_BOOKING_CYPHER = """
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
       b.is_rolled AS is_rolled,
       voy.voyage_id AS booked_voyage_id,
       v.name AS vessel_name,
       orig.port_code AS origin,
       dest.port_code AS destination,
       toString(voy.revised_eta_utc) AS scheduled_eta_utc,
       rolledVoy.voyage_id AS rolled_to_voyage_id
ORDER BY b.booking_id
LIMIT $limit
"""

GET_ROLLED_BOOKINGS_CYPHER = """
MATCH (b:Booking {is_rolled: true})
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

def track_booking(
    client: Neo4jClient,
    booking_id: Optional[str] = None,
    customer_name: Optional[str] = None,
    voyage_id: Optional[str] = None,
    limit: int = 50
) -> Dict[str, Any]:
    """Tracks customer container freight shipments and delivery estimates."""
    params = {
        "booking_id": booking_id.strip() if booking_id else None,
        "customer_name": customer_name.strip() if customer_name else None,
        "voyage_id": voyage_id.strip() if voyage_id else None,
        "limit": min(limit, 100)
    }
    try:
        results = client.execute_read_query(TRACK_BOOKING_CYPHER, params)
        if not results:
            return {
                "status": "NO_DATA",
                "message": "NO_DATA_FOUND: No freight bookings matched the specified search criteria.",
                "count": 0,
                "bookings": []
            }
        return {"status": "SUCCESS", "success": True, "count": len(results), "bookings": results}
    except Exception as e:
        logger.error("Error tracking booking: %s", e)
        return {"status": "NO_DATA", "success": False, "error": str(e), "message": "NO_DATA_FOUND due to query error.", "count": 0, "bookings": []}

def get_rolled_bookings(client: Neo4jClient, limit: int = 50) -> Dict[str, Any]:
    """Retrieves all container shipments that were rolled to later sailings."""
    try:
        results = client.execute_read_query(GET_ROLLED_BOOKINGS_CYPHER, {"limit": min(limit, 100)})
        if not results:
            return {
                "status": "NO_DATA",
                "message": "NO_DATA_FOUND: No rolled bookings found in the Maritime Knowledge Graph.",
                "count": 0,
                "rolled_bookings": []
            }
        return {"status": "SUCCESS", "success": True, "count": len(results), "rolled_bookings": results}
    except Exception as e:
        logger.error("Error getting rolled bookings: %s", e)
        return {"status": "NO_DATA", "success": False, "error": str(e), "message": "NO_DATA_FOUND due to query error.", "count": 0, "rolled_bookings": []}

