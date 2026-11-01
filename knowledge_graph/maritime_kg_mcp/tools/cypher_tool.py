import logging
from typing import Any, Dict, Optional
from knowledge_graph.database import Neo4jClient
from knowledge_graph.maritime_kg_mcp.security import validate_read_only_cypher, enforce_query_limit

logger = logging.getLogger(__name__)

def execute_read_cypher(
    client: Neo4jClient,
    query: str,
    parameters: Optional[Dict[str, Any]] = None,
    limit: int = 100
) -> Dict[str, Any]:
    """
    Executes a validated read-only Cypher query against the Maritime Knowledge Graph.
    Blocks any modifying operations (CREATE, MERGE, SET, DELETE, DROP, etc.).
    """
    is_valid, error_msg = validate_read_only_cypher(query)
    if not is_valid:
        return {
            "success": False,
            "error": error_msg,
            "record_count": 0,
            "records": []
        }

    safe_query = enforce_query_limit(query, limit)
    logger.debug("Executing read Cypher query: %s with params %s", safe_query, parameters)

    try:
        records = client.execute_read_query(safe_query, parameters or {})
        return {
            "success": True,
            "record_count": len(records),
            "records": records,
            "executed_query": safe_query
        }
    except Exception as e:
        logger.error("Error executing Cypher query: %s", e)
        return {
            "success": False,
            "error": str(e),
            "record_count": 0,
            "records": []
        }

