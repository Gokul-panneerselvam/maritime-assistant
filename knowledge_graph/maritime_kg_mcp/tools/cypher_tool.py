"""Cypher execution tool for Maritime Knowledge Graph.
Executes validated read-only Cypher queries with row limits and type serialization.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from utility.dependencies import DatabaseClientProtocol
from utility.logger import get_logger
from knowledge_graph.maritime_kg_mcp.security import enforce_query_limit, validate_read_only_cypher

logger = get_logger(__name__)


def serialize_neo4j_data(data: Any) -> Any:
    """Recursively converts Neo4j data structures (DateTime, Date, Time, Point, Node) to JSON-serializable primitives."""
    if data is None:
        return None
    if isinstance(data, (int, float, str, bool)):
        return data
    if hasattr(data, "iso_format"):
        return data.iso_format()
    if hasattr(data, "isoformat"):
        return data.isoformat()
    if isinstance(data, dict):
        return {str(k): serialize_neo4j_data(v) for k, v in data.items()}
    if isinstance(data, (list, tuple, set)):
        return [serialize_neo4j_data(v) for v in data]
    if hasattr(data, "items"):
        return {str(k): serialize_neo4j_data(v) for k, v in dict(data).items()}
    return str(data)


def execute_read_cypher(
    client: DatabaseClientProtocol,
    query: str,
    parameters: Optional[Dict[str, Any]] = None,
    limit: int = 100
) -> Dict[str, Any]:
    """Executes a validated read-only Cypher query against the Maritime Knowledge Graph.
    Blocks any modifying operations (CREATE, MERGE, SET, DELETE, DROP, etc.).
    Sanitizes all Neo4j data types into JSON-serializable types.
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
        raw_records = client.execute_read_query(safe_query, parameters or {})
        sanitized_records = [serialize_neo4j_data(r) for r in raw_records]
        if not sanitized_records:
            return {
                "status": "NO_DATA",
                "success": True,
                "message": "NO_DATA_FOUND: No matching records exist in the Maritime Knowledge Graph for this query.",
                "record_count": 0,
                "records": [],
                "executed_query": safe_query
            }
        return {
            "status": "SUCCESS",
            "success": True,
            "record_count": len(sanitized_records),
            "records": sanitized_records,
            "executed_query": safe_query
        }
    except Exception as e:
        logger.error("Error executing Cypher query: %s", e)
        return {
            "status": "ERROR",
            "success": False,
            "error": str(e),
            "message": "NO_DATA_FOUND: Cypher query execution error.",
            "record_count": 0,
            "records": []
        }
