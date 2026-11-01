import logging
from typing import Any, Dict
from knowledge_graph.database import Neo4jClient

logger = logging.getLogger(__name__)

SUMMARY_CYPHER = """
CALL {
    MATCH (v:Vessel) RETURN count(v) AS total_vessels
}
CALL {
    MATCH (voy:Voyage) RETURN count(voy) AS total_voyages,
                              count(CASE WHEN toLower(voy.status) = 'delayed' THEN 1 END) AS delayed_voyages
}
CALL {
    MATCH (inc:Incident) RETURN count(inc) AS total_incidents
}
CALL {
    MATCH (b:Booking) RETURN count(b) AS total_bookings,
                            count(CASE WHEN b.is_rolled = true THEN 1 END) AS rolled_bookings
}
RETURN total_vessels, total_voyages, delayed_voyages, total_incidents, total_bookings, rolled_bookings
"""

def get_operational_summary(client: Neo4jClient) -> Dict[str, Any]:
    """Retrieves high-level operational metrics across fleet, voyages, delays, and incidents."""
    try:
        results = client.execute_read_query(SUMMARY_CYPHER)
        if not results:
            return {"success": False, "error": "No operational metrics returned."}
        row = results[0]
        return {
            "success": True,
            "metrics": {
                "total_vessels": row.get("total_vessels", 0),
                "total_voyages": row.get("total_voyages", 0),
                "delayed_voyages": row.get("delayed_voyages", 0),
                "total_incidents": row.get("total_incidents", 0),
                "total_bookings": row.get("total_bookings", 0),
                "rolled_bookings": row.get("rolled_bookings", 0)
            }
        }
    except Exception as e:
        logger.error("Error getting operational summary: %s", e)
        return {"success": False, "error": str(e)}

