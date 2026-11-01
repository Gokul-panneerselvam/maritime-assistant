import logging
from typing import Any, Dict
from knowledge_graph.database import Neo4jClient

logger = logging.getLogger(__name__)

SCHEMA_METADATA_QUERY = """
CALL db.labels() YIELD label
RETURN collect(label) AS labels
"""

REL_TYPES_QUERY = """
CALL db.relationshipTypes() YIELD relationshipType
RETURN collect(relationshipType) AS relationship_types
"""

CONSTRAINTS_QUERY = """
SHOW CONSTRAINTS YIELD name, type, entityType, labelsOrTypes, properties
RETURN name, type, entityType, labelsOrTypes, properties
"""

def get_graph_schema(client: Neo4jClient) -> Dict[str, Any]:
    """
    Returns the Knowledge Graph schema definition, node labels, relationship types,
    and schema constraints to inform client queries.
    """
    try:
        labels_res = client.execute_read_query(SCHEMA_METADATA_QUERY)
        labels = labels_res[0]["labels"] if labels_res else []

        rels_res = client.execute_read_query(REL_TYPES_QUERY)
        rels = rels_res[0]["relationship_types"] if rels_res else []

        try:
            constraints_res = client.execute_read_query(CONSTRAINTS_QUERY)
        except Exception:
            constraints_res = []

        return {
            "success": True,
            "node_labels": labels,
            "relationship_types": rels,
            "constraints": constraints_res,
            "domain_overview": {
                "Vessel": "Fleet ships with IMO, class, type, technical manager",
                "Voyage": "Sea transits between origin and destination ports with UTC timestamps",
                "Port": "Seaports with IANA timezone",
                "PortCall": "Terminal and anchorage milestones with wait/stay hours",
                "Incident": "Operational defects, weather delays, and technical faults",
                "Congestion": "Daily port-wide anchorage queues and average wait times",
                "Booking": "Customer container freight allocations and rolled statuses",
                "Customer": "Shippers and cargo owners placing freight bookings"
            }
        }
    except Exception as e:
        logger.error("Failed to retrieve graph schema: %s", e)
        return {
            "success": False,
            "error": str(e),
            "node_labels": [],
            "relationship_types": []
        }

