import logging
from typing import Any, Dict, Optional
from knowledge_graph.database import Neo4jClient

logger = logging.getLogger(__name__)

SEARCH_VESSELS_CYPHER = """
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

GET_VESSEL_DETAILS_CYPHER = """
MATCH (v:Vessel {vessel_id: $vessel_id})
OPTIONAL MATCH (v)-[:OF_TYPE]->(vt:VesselType)
OPTIONAL MATCH (v)-[:OF_CLASS]->(vc:VesselClass)
OPTIONAL MATCH (v)-[:MANAGED_BY]->(tm:TechnicalManager)

OPTIONAL MATCH (v)-[:OPERATES_VOYAGE]->(voy:Voyage)
OPTIONAL MATCH (voy)-[:DEPARTS_FROM]->(orig:Port)
OPTIONAL MATCH (voy)-[:ARRIVES_AT]->(dest:Port)

WITH v, vt, vc, tm, voy, orig, dest
ORDER BY voy.departure_utc DESC
WITH v, vt, vc, tm,
     collect(DISTINCT {
         voyage_id: voy.voyage_id,
         origin: orig.port_code,
         destination: dest.port_code,
         status: voy.status,
         departure_utc: toString(voy.departure_utc),
         revised_eta_utc: toString(voy.revised_eta_utc),
         delay_hours: voy.recorded_delay_hours
     }) AS voyages

OPTIONAL MATCH (inc:Incident)-[:AFFECTS_VESSEL]->(v)
WITH v, vt, vc, tm, voyages,
     collect(DISTINCT {
         incident_id: inc.incident_id,
         type: inc.type,
         severity: inc.severity,
         status: inc.status,
         reported_utc: toString(inc.reported_utc),
         attributed_delay_hours: inc.attributed_delay_hours
     }) AS incidents

RETURN v.vessel_id AS vessel_id,
       v.name AS name,
       v.imo AS imo,
       vt.name AS type,
       vc.name AS vessel_class,
       tm.name AS technical_manager,
       voyages,
       incidents
"""

def search_vessels(
    client: Neo4jClient,
    vessel_id: Optional[str] = None,
    name: Optional[str] = None,
    imo: Optional[int] = None,
    vessel_type: Optional[str] = None,
    vessel_class: Optional[str] = None,
    limit: int = 50
) -> Dict[str, Any]:
    """Search fleet vessels with filters for ID, name, IMO, type, or class."""
    params = {
        "vessel_id": vessel_id,
        "name": name,
        "imo": imo,
        "vessel_type": vessel_type,
        "vessel_class": vessel_class,
        "limit": min(limit, 100)
    }
    try:
        results = client.execute_read_query(SEARCH_VESSELS_CYPHER, params)
        return {"success": True, "count": len(results), "vessels": results}
    except Exception as e:
        logger.error("Error searching vessels: %s", e)
        return {"success": False, "error": str(e), "vessels": []}

def get_vessel_details(client: Neo4jClient, vessel_id: str) -> Dict[str, Any]:
    """Retrieves 360-degree vessel profile, including technical management, voyages, and incidents."""
    try:
        results = client.execute_read_query(GET_VESSEL_DETAILS_CYPHER, {"vessel_id": vessel_id.strip()})
        if not results:
            return {"success": False, "error": f"Vessel '{vessel_id}' not found."}
        return {"success": True, "vessel": results[0]}
    except Exception as e:
        logger.error("Error getting vessel details: %s", e)
        return {"success": False, "error": str(e)}

