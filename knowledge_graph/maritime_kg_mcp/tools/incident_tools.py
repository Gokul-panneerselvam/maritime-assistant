import logging
from typing import Any, Dict, Optional
from knowledge_graph.database import Neo4jClient

logger = logging.getLogger(__name__)

SEARCH_INCIDENTS_CYPHER = """
MATCH (voy:Voyage)-[:EXPERIENCED_INCIDENT]->(inc:Incident)
MATCH (v:Vessel)-[:OPERATES_VOYAGE]->(voy)
MATCH (voy)-[:DEPARTS_FROM]->(orig:Port)
MATCH (voy)-[:ARRIVES_AT]->(dest:Port)
WHERE ($severity IS NULL OR toLower(inc.severity) = toLower($severity))
  AND ($incident_type IS NULL OR toLower(inc.type) CONTAINS toLower($incident_type))
  AND ($status IS NULL OR toLower(inc.status) = toLower($status))
  AND ($voyage_id IS NULL OR voy.voyage_id = $voyage_id)
  AND ($vessel_id IS NULL OR v.vessel_id = $vessel_id)
RETURN inc.incident_id AS incident_id,
       inc.type AS type,
       inc.severity AS severity,
       inc.status AS status,
       toString(inc.reported_utc) AS reported_utc,
       inc.source AS source,
       inc.attributed_delay_hours AS attributed_delay_hours,
       voy.voyage_id AS voyage_id,
       v.vessel_id AS vessel_id,
       v.name AS vessel_name,
       orig.port_code AS origin,
       dest.port_code AS destination
ORDER BY inc.reported_utc DESC
LIMIT $limit
"""

def search_incidents(
    client: Neo4jClient,
    severity: Optional[str] = None,
    incident_type: Optional[str] = None,
    status: Optional[str] = None,
    voyage_id: Optional[str] = None,
    vessel_id: Optional[str] = None,
    limit: int = 50
) -> Dict[str, Any]:
    """Filters maritime operational disruptions (engine faults, weather diversions, customs queries)."""
    params = {
        "severity": severity,
        "incident_type": incident_type,
        "status": status,
        "voyage_id": voyage_id,
        "vessel_id": vessel_id,
        "limit": min(limit, 100)
    }
    try:
        results = client.execute_read_query(SEARCH_INCIDENTS_CYPHER, params)
        return {"success": True, "count": len(results), "incidents": results}
    except Exception as e:
        logger.error("Error searching incidents: %s", e)
        return {"success": False, "error": str(e), "incidents": []}

