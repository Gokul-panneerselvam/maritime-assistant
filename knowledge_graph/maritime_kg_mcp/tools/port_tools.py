import logging
from typing import Any, Dict, Optional
from knowledge_graph.database import Neo4jClient

logger = logging.getLogger(__name__)

SEARCH_PORTS_CYPHER = """
MATCH (p:Port)
WHERE ($query IS NULL OR toLower(p.port_code) CONTAINS toLower($query) OR toLower(p.name) CONTAINS toLower($query) OR toLower(p.country) CONTAINS toLower($query))
RETURN p.port_code AS port_code,
       p.name AS name,
       p.country AS country,
       p.timezone AS timezone
ORDER BY p.port_code
"""

GET_PORT_CONGESTION_CYPHER = """
MATCH (p:Port {port_code: $port_code})-[:HAS_CONGESTION]->(cg:Congestion)
WHERE ($date IS NULL OR toString(cg.date_utc) = $date)
RETURN p.port_code AS port_code,
       p.name AS port_name,
       toString(cg.date_utc) AS date_utc,
       cg.congestion_level AS congestion_level,
       cg.avg_wait_hours AS avg_wait_hours,
       cg.vessels_at_anchor AS vessels_at_anchor,
       cg.source AS source
ORDER BY cg.date_utc DESC
LIMIT $limit
"""

def search_ports(client: Neo4jClient, query: Optional[str] = None) -> Dict[str, Any]:
    """Lists or searches ports by port code, name, or country."""
    try:
        results = client.execute_read_query(SEARCH_PORTS_CYPHER, {"query": query})
        return {"success": True, "count": len(results), "ports": results}
    except Exception as e:
        logger.error("Error searching ports: %s", e)
        return {"success": False, "error": str(e), "ports": []}

def get_port_congestion(
    client: Neo4jClient,
    port_code: str,
    date: Optional[str] = None,
    limit: int = 14
) -> Dict[str, Any]:
    """Retrieves port-wide anchorage queues and average wait hours for a specified port."""
    params = {
        "port_code": port_code.strip().upper(),
        "date": date.strip() if date else None,
        "limit": min(limit, 100)
    }
    try:
        results = client.execute_read_query(GET_PORT_CONGESTION_CYPHER, params)
        return {"success": True, "count": len(results), "congestion_records": results}
    except Exception as e:
        logger.error("Error getting port congestion: %s", e)
        return {"success": False, "error": str(e), "congestion_records": []}

