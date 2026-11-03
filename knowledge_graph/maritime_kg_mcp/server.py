import logging
from typing import Any, Dict, List, Optional
from fastmcp import FastMCP
from knowledge_graph.database import Neo4jClient
from knowledge_graph.config import Neo4jConfig
from knowledge_graph.maritime_kg_mcp.tools.cypher_tool import execute_read_cypher
from knowledge_graph.maritime_kg_mcp.tools.schema_tool import get_graph_schema as fetch_schema
from knowledge_graph.maritime_kg_mcp.tools.vessel_tools import (
    search_vessels as fetch_vessels,
    get_vessel_details as fetch_vessel_details,
)
from knowledge_graph.maritime_kg_mcp.tools.voyage_tools import (
    search_voyages as fetch_voyages,
    get_voyage_timeline as fetch_voyage_timeline,
)
from knowledge_graph.maritime_kg_mcp.tools.port_tools import (
    search_ports as fetch_ports,
    get_port_congestion as fetch_port_congestion,
)
from knowledge_graph.maritime_kg_mcp.tools.incident_tools import search_incidents as fetch_incidents
from knowledge_graph.maritime_kg_mcp.tools.booking_tools import (
    track_booking as fetch_booking,
    get_rolled_bookings as fetch_rolled_bookings,
)
from knowledge_graph.maritime_kg_mcp.tools.summary_tool import get_operational_summary as fetch_summary
from knowledge_graph.maritime_kg_mcp.tools.node_tools import (
    create_nodes as create_nodes_impl,
    update_nodes as update_nodes_impl,
)

logger = logging.getLogger(__name__)

# Initialize FastMCP Server
mcp = FastMCP(
    name="Maritime Operations Knowledge Graph Server",
)

_client: Optional[Neo4jClient] = None

def get_db_client() -> Neo4jClient:
    """Provides a lazy-loaded, thread-safe Neo4jClient instance."""
    global _client
    if _client is None:
        _client = Neo4jClient(Neo4jConfig())
        try:
            _client.connect()
        except Exception as e:
            logger.warning("Neo4j database not reachable yet: %s", e)
    return _client


@mcp.tool(output_schema=None)
def execute_read_query(
    query: str,
    parameters: Optional[Dict[str, Any]] = None,
    limit: int = 100
) -> Dict[str, Any]:
    """
    Executes a validated read-only Cypher query against the Maritime Knowledge Graph.
    Mutating statements (CREATE, MERGE, SET, DELETE, DROP, etc.) are strictly forbidden.
    Results are capped to a maximum of 500 rows.

    TEMPORAL & DATE FORMAT SPECIFICATION:
    - ALL datetime values stored in the Maritime Knowledge Graph strictly use the UTC ISO-8601 format:
      ("%Y-%m-%dT%H:%M:%SZ") (e.g. "2026-10-26T12:00:00Z").
    - Filter datetime fields using datetime("..."):
      WHERE voy.revised_eta_utc >= datetime("2026-10-31T00:00:00Z") AND voy.revised_eta_utc <= datetime("2026-11-06T23:59:59Z")
    - Date-only fields (Congestion.date_utc, Booking.promised_delivery_date_utc) use ("%Y-%m-%d"): date("2026-10-20").
    - Operational anchor date: 2026-10-26 12:00 UTC.
    """
    client = get_db_client()
    return execute_read_cypher(client, query, parameters, limit=limit)


@mcp.tool()
def get_knowledge_graph_schema() -> Dict[str, Any]:
    """
    Returns the schema of the Maritime Knowledge Graph, including node labels,
    relationship types, property keys, and database constraints.
    """
    client = get_db_client()
    return fetch_schema(client)


@mcp.tool()
def search_vessels(
    vessel_id: Optional[str] = None,
    name: Optional[str] = None,
    imo: Optional[int] = None,
    vessel_type: Optional[str] = None,
    vessel_class: Optional[str] = None,
    limit: int = 50
) -> Dict[str, Any]:
    """
    Searches fleet vessels with filters for vessel ID, vessel name, IMO number,
    vessel type (e.g. 'Container ship'), or structural class (e.g. 'Meridian 8500').
    """
    client = get_db_client()
    return fetch_vessels(client, vessel_id, name, imo, vessel_type, vessel_class, limit=limit)


@mcp.tool()
def get_vessel_details(vessel_id: str) -> Dict[str, Any]:
    """
    Retrieves a comprehensive 360-degree profile of a physical vessel, including
    its IMO, class, type, technical management company, all executed voyages,
    and historical incidents.
    """
    client = get_db_client()
    return fetch_vessel_details(client, vessel_id)


@mcp.tool()
def search_voyages(
    voyage_id: Optional[str] = None,
    vessel_id: Optional[str] = None,
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    status: Optional[str] = None,
    min_delay_hours: Optional[float] = None,
    limit: int = 50
) -> Dict[str, Any]:
    """
    Searches operational voyages. Filter by origin port code/name, destination port,
    status ('Completed', 'Delayed', 'Scheduled'), operating vessel, or minimum delay hours.
    All timestamps are standardized to UTC.
    """
    client = get_db_client()
    return fetch_voyages(client, voyage_id, vessel_id, origin, destination, status, min_delay_hours, limit=limit)


@mcp.tool()
def get_voyage_timeline(voyage_id: str) -> Dict[str, Any]:
    """
    Retrieves the complete operational timeline of a voyage transit: origin/destination ports,
    local and UTC departure/ETA, terminal port calls (anchorage arrival, berthing, departure,
    and computed wait hours), reported incidents, and freight cargo bookings.
    """
    client = get_db_client()
    return fetch_voyage_timeline(client, voyage_id)


@mcp.tool()
def search_ports(query: Optional[str] = None) -> Dict[str, Any]:
    """
    Lists or searches seaports by 5-letter UN/LOCODE (e.g., 'SGSIN', 'NLRTM'),
    port name, or country, along with their native IANA timezones.
    """
    client = get_db_client()
    return fetch_ports(client, query)


@mcp.tool()
def get_port_congestion(
    port_code: str,
    date: Optional[str] = None,
    limit: int = 14
) -> Dict[str, Any]:
    """
    Retrieves daily port-wide water-side congestion records for a port:
    average anchorage wait hours, count of vessels queued at anchor, and congestion level.
    """
    client = get_db_client()
    return fetch_port_congestion(client, port_code, date, limit=limit)


@mcp.tool()
def search_incidents(
    severity: Optional[str] = None,
    incident_type: Optional[str] = None,
    status: Optional[str] = None,
    voyage_id: Optional[str] = None,
    vessel_id: Optional[str] = None,
    limit: int = 50
) -> Dict[str, Any]:
    """
    Searches operational disruptions, mechanical faults (e.g. engine cooling faults),
    weather reroutings, and customs queries across voyages and affected vessels.
    """
    client = get_db_client()
    return fetch_incidents(client, severity, incident_type, status, voyage_id, vessel_id, limit=limit)


@mcp.tool()
def track_booking(
    booking_id: Optional[str] = None,
    customer_name: Optional[str] = None,
    voyage_id: Optional[str] = None,
    limit: int = 50
) -> Dict[str, Any]:
    """
    Tracks commercial cargo bookings by booking ID, customer name, or assigned voyage.
    Returns container volume, promised delivery deadline, and rolled status.
    """
    client = get_db_client()
    return fetch_booking(client, booking_id, customer_name, voyage_id, limit=limit)


@mcp.tool()
def get_rolled_bookings(limit: int = 50) -> Dict[str, Any]:
    """
    Retrieves all container bookings that were rolled to later sailings,
    including the original voyage and re-assigned target voyage where available.
    """
    client = get_db_client()
    return fetch_rolled_bookings(client, limit=limit)


@mcp.tool()
def get_operational_summary() -> Dict[str, Any]:
    """
    Returns an executive KPI summary: total fleet vessels, total transits,
    number of delayed voyages, total logged incidents, and rolled booking volumes.
    """
    client = get_db_client()
    return fetch_summary(client)


@mcp.tool()
def create_nodes(
    label: Optional[str] = None,
    properties: Optional[Dict[str, Any]] = None,
    edges: Optional[List[Dict[str, Any]]] = None,
    nodes: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Creates new nodes in the Maritime Knowledge Graph with duplicate checks and schema constraints.
    Supports single-node creation or batch creation via the 'nodes' parameter.
    
    Validates against existing unique keys (e.g. incident_id, imo, port_code, voyage_id) to prevent duplicate creation.
    Supports adding edges to existing nodes at creation time.
    Returns rich node information and identifiers for subsequent agent reasoning and relationship linking.

    Parameters:
    - label: Node label (e.g. 'Incident', 'Message', 'Voyage', 'PortCall', 'Organization', 'Port').
    - properties: Attributes of the new node including primary key (e.g. {'incident_id': 'INC-501', 'type': 'Pilot boarding delay', 'severity': 'Low', 'reported_utc': '2026-06-11T12:00:00Z'}).
    - edges: Optional list of edges to establish upon creation. Each item:
        - 'relationship_type': e.g. 'EXPERIENCED_INCIDENT', 'AFFECTS_VESSEL', 'REPORTS_INCIDENT', 'BASED_AT'
        - 'target_label': Target node label (e.g. 'Voyage', 'Vessel', 'Port')
        - 'target_value': Target node primary key value (e.g. 'VG-2002')
        - 'target_key': Optional target lookup property (defaults to target label's PK)
        - 'direction': 'OUTGOING' (default, source -> target) or 'INCOMING' (target -> source)
        - 'properties': Optional edge properties (e.g. {'temporal': 'past', 'event_time_utc': '2026-06-11T12:00:00Z'})
    - nodes: Optional list of node definitions [{'label': ..., 'properties': ..., 'edges': ...}] for batch creation.
    """
    client = get_db_client()
    return create_nodes_impl(client, label=label, properties=properties, edges=edges, nodes=nodes)


@mcp.tool()
def update_nodes(
    label: Optional[str] = None,
    key_value: Optional[Any] = None,
    key_field: Optional[str] = None,
    properties: Optional[Dict[str, Any]] = None,
    edges: Optional[List[Dict[str, Any]]] = None,
    nodes: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Updates existing valid nodes in the Maritime Knowledge Graph and attaches/modifies relationships.
    Strictly modifies existing nodes only (returns NodeNotFoundError if the target node does not exist).
    
    Allows updating all node attributes, establishing new edges, or batch updating via 'nodes'.
    Returns comprehensive node details, updated properties, and connected edges for agent multi-hop reasoning.

    Parameters:
    - label: Target node label to update (e.g. 'Incident', 'Voyage', 'PortCall', 'Message').
    - key_value: The identifier value matching the target node (e.g. 'INC-202', 'VG-1042', 'PC-7004').
    - key_field: Optional property name to match on (defaults to label's primary key, e.g. 'incident_id').
    - properties: Attributes to set or update (e.g. {'status': 'Confirmed', 'attributed_delay_hours': 8.0}).
    - edges: Optional list of edges to connect to/from this existing node:
        - 'relationship_type': e.g. 'CORROBORATES_INCIDENT', 'ABOUT_VOYAGE', 'EXPERIENCED_INCIDENT'
        - 'target_label': Target node label (e.g. 'Incident', 'Voyage', 'Port')
        - 'target_value': Target node identifier value (e.g. 'INC-202')
        - 'target_key': Optional target property (defaults to target label's PK)
        - 'direction': 'OUTGOING' (default) or 'INCOMING'
        - 'properties': Optional edge properties (e.g. {'temporal': 'past'})
    - nodes: Optional list of updates [{'label': ..., 'key_value': ..., 'properties': ..., 'edges': ...}] for batch execution.
    """
    client = get_db_client()
    return update_nodes_impl(client, label=label, key_value=key_value, key_field=key_field, properties=properties, edges=edges, nodes=nodes)


def create_app() -> FastMCP:
    """Factory function returning the configured FastMCP server instance."""
    return mcp

