"""Maritime Operations Knowledge Graph FastMCP Server.
Exposes domain context tools, message intelligence, and preserved query/write tools.
Adheres to SOLID principles:
- Centralized configuration and JSON logging via utility package.
- Dependency injection via DatabaseClientProtocol provider.
- Structured graph-text responses wrapped in ToolResponse.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from fastmcp import FastMCP

from utility.config import get_config
from utility.dependencies import get_db_client
from utility.logger import get_logger
from knowledge_graph.maritime_kg_mcp.models import (
    GetCargoExposureInput,
    GetPortContextInput,
    GetVesselContextInput,
    GetVoyageContextInput,
    ScanVoyagesInput,
    SearchIncidentHistoryInput,
    SearchMessagesInput,
)
from knowledge_graph.maritime_kg_mcp.tools.booking_tools import (
    get_cargo_exposure as fetch_cargo_exposure,
    track_booking as fetch_booking,
)
from knowledge_graph.maritime_kg_mcp.tools.cypher_tool import execute_read_cypher
from knowledge_graph.maritime_kg_mcp.tools.incident_tools import (
    search_incident_history as fetch_incident_history,
)
from knowledge_graph.maritime_kg_mcp.tools.message_tools import (
    search_messages as fetch_messages,
)
from knowledge_graph.maritime_kg_mcp.tools.node_tools import (
    create_nodes as create_nodes_impl,
    update_nodes as update_nodes_impl,
)
from knowledge_graph.maritime_kg_mcp.tools.port_tools import (
    get_port_context as fetch_port_context,
)
from knowledge_graph.maritime_kg_mcp.tools.schema_tool import get_graph_schema as fetch_schema
from knowledge_graph.maritime_kg_mcp.tools.vessel_tools import (
    get_vessel_context as fetch_vessel_context,
)
from knowledge_graph.maritime_kg_mcp.tools.voyage_tools import (
    get_voyage_context as fetch_voyage_context,
    scan_voyages as fetch_scan_voyages,
)

logger = get_logger(__name__)
config = get_config()

# Initialize FastMCP Server
mcp = FastMCP(
    name="Maritime Operations Knowledge Graph Server",
)


def _build_input(model_cls: type, flat_kwargs: dict, args_obj: Any) -> Any:
    """Helper to flexibly construct Pydantic inputs from flat kwargs or nested args dict."""
    data: dict[str, Any] = {}
    if args_obj is not None:
        if isinstance(args_obj, dict):
            data.update(args_obj)
        elif isinstance(args_obj, model_cls):
            return args_obj
    for k, v in flat_kwargs.items():
        if v is not None and k not in data:
            data[k] = v
    return model_cls(**data)


# =============================================================================
# 1. Cypher Execution: execute_read_query
# =============================================================================

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


# =============================================================================
# 2. Vessel Tools: get_vessel_context
# =============================================================================

@mcp.tool(description=(
    "Vessel profile with sister ships, recent voyage timeline, incidents, and class bulletins. "
    "Use for vessel-centric questions or to find the current active voyage."
))
def get_vessel_context(
    vessel: Optional[str] = None,
    voyages_limit: int = 8,
    incidents: Literal["all", "open"] = "all",
    include_sisters: bool = True,
    include_manager_fleet: bool = False,
    message_days_back: int = 30,
    args: Optional[Any] = None,
) -> str:
    inp = _build_input(GetVesselContextInput, {
        "vessel": vessel,
        "voyages_limit": voyages_limit,
        "incidents": incidents,
        "include_sisters": include_sisters,
        "include_manager_fleet": include_manager_fleet,
        "message_days_back": message_days_back,
    }, args)
    client = get_db_client()
    resp = fetch_vessel_context(client, inp)
    return resp.to_agent_text()


# =============================================================================
# 3. Voyage Tools: get_voyage_context & scan_voyages
# =============================================================================

@mcp.tool(description=(
    "Full context of one voyage as graph text: vessel (class, manager), origin/destination ports, port calls, "
    "destination congestion around the ETA, incidents with their message chains and evidence tier, bookings summary, "
    "berth-window verdict, delay reconciliation and GAPS to check next. Use first for 'why is X delayed / what happened on voyage Y'. "
    "Selectors: vessel + which, dest_port, window."
))
def get_voyage_context(
    voyage_id: Optional[str] = None,
    vessel: Optional[str] = None,
    which: Literal["current", "latest", "next", "in_window"] = "current",
    dest_port: Optional[str] = None,
    origin_port: Optional[str] = None,
    window: Optional[Dict[str, Any]] = None,
    max_voyages: int = 1,
    congestion_days_around_eta: int = 2,
    include_bookings_summary: bool = True,
    message_detail: Literal["counts_only", "snippet", "full"] = "snippet",
    args: Optional[Any] = None,
) -> str:
    inp = _build_input(GetVoyageContextInput, {
        "voyage_id": voyage_id,
        "vessel": vessel,
        "which": which,
        "dest_port": dest_port,
        "origin_port": origin_port,
        "window": window,
        "max_voyages": max_voyages,
        "congestion_days_around_eta": congestion_days_around_eta,
        "include_bookings_summary": include_bookings_summary,
        "message_detail": message_detail,
    }, args)
    client = get_db_client()
    resp = fetch_voyage_context(client, inp)
    return resp.to_agent_text()


@mcp.tool(description=(
    "Scan and rank voyages by berth-window risk, delay or ETA for a port and date window, with risk factors and evidence IDs. "
    "Use for fleet-wide or port-wide questions. Score weights are documented in the result."
))
def scan_voyages(
    window: Optional[Dict[str, Any]] = None,
    dest_port: Optional[str] = None,
    origin_port: Optional[str] = None,
    window_field: Literal["revised_eta", "original_eta", "berth_window", "departure"] = "revised_eta",
    vessel_class: Optional[str] = None,
    manager: Optional[str] = None,
    vessel_type: Optional[str] = None,
    statuses: Optional[List[str]] = None,
    only_risky: bool = False,
    min_risk: int = 0,
    rank_by: Literal["berth_risk", "delay", "eta"] = "berth_risk",
    limit: int = 15,
    args: Optional[Any] = None,
) -> str:
    flat = {
        "window": window,
        "dest_port": dest_port,
        "origin_port": origin_port,
        "window_field": window_field,
        "vessel_class": vessel_class,
        "manager": manager,
        "vessel_type": vessel_type,
        "only_risky": only_risky,
        "min_risk": min_risk,
        "rank_by": rank_by,
        "limit": limit,
    }
    if statuses is not None:
        flat["statuses"] = statuses
    inp = _build_input(ScanVoyagesInput, flat, args)
    client = get_db_client()
    resp = fetch_scan_voyages(client, inp)
    return resp.to_agent_text()


# =============================================================================
# 4. Port Tools: get_port_context
# =============================================================================

@mcp.tool(description=(
    "Port with congestion series, agents, port calls and inbound voyages for a date window. "
    "Use to judge whether congestion explains anchorage waits."
))
def get_port_context(
    port: Optional[str] = None,
    window: Optional[Dict[str, Any]] = None,
    include_port_calls: bool = True,
    include_inbound_voyages: bool = True,
    include_messages: bool = True,
    max_port_calls: int = 20,
    args: Optional[Any] = None,
) -> str:
    inp = _build_input(GetPortContextInput, {
        "port": port,
        "window": window,
        "include_port_calls": include_port_calls,
        "include_inbound_voyages": include_inbound_voyages,
        "include_messages": include_messages,
        "max_port_calls": max_port_calls,
    }, args)
    client = get_db_client()
    resp = fetch_port_context(client, inp)
    return resp.to_agent_text()


# =============================================================================
# 5. Incident Tools: search_incident_history
# =============================================================================

@mcp.tool(description=(
    "Recurrence of an incident type/component on the same vessel, sister vessels (class) and same technical manager, "
    "with corrections and bulletins. Use for 'has this happened before / on other ships'."
))
def search_incident_history(
    incident_id: Optional[str] = None,
    incident_type: Optional[str] = None,
    keyword: Optional[str] = None,
    anchor_vessel: Optional[str] = None,
    scopes: Optional[List[Literal["vessel", "class", "manager", "fleet"]]] = None,
    window: Optional[Dict[str, Any]] = None,
    statuses: Optional[List[str]] = None,
    limit_per_scope: int = 10,
    args: Optional[Any] = None,
) -> str:
    flat = {
        "incident_id": incident_id,
        "incident_type": incident_type,
        "keyword": keyword,
        "anchor_vessel": anchor_vessel,
        "window": window,
        "limit_per_scope": limit_per_scope,
    }
    if scopes is not None:
        flat["scopes"] = scopes
    if statuses is not None:
        flat["statuses"] = statuses
    inp = _build_input(SearchIncidentHistoryInput, flat, args)
    client = get_db_client()
    resp = fetch_incident_history(client, inp)
    return resp.to_agent_text()


# =============================================================================
# 6. Cargo / Booking Tools: track_booking & get_cargo_exposure
# =============================================================================

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


@mcp.tool(description=(
    "Customers and containers affected by a voyage, split into on board / rolled / cancelled, with promised-date risk. "
    "Rolled containers are NOT on board."
))
def get_cargo_exposure(
    voyage_id: Optional[str] = None,
    vessel: Optional[str] = None,
    which: Literal["current", "latest", "next"] = "current",
    customer: Optional[str] = None,
    include_statuses: Optional[List[str]] = None,
    args: Optional[Any] = None,
) -> str:
    flat = {
        "voyage_id": voyage_id,
        "vessel": vessel,
        "which": which,
        "customer": customer,
    }
    if include_statuses is not None:
        flat["include_statuses"] = include_statuses
    inp = _build_input(GetCargoExposureInput, flat, args)
    client = get_db_client()
    resp = fetch_cargo_exposure(client, inp)
    return resp.to_agent_text()


# =============================================================================
# 7. Write/Mutating Tools: create_nodes & update_nodes
# =============================================================================

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
    """
    client = get_db_client()
    return update_nodes_impl(client, label=label, key_value=key_value, key_field=key_field, properties=properties, edges=edges, nodes=nodes)


# =============================================================================
# 8. Schema Tools: get_knowledge_graph_schema
# =============================================================================

@mcp.tool()
def get_knowledge_graph_schema() -> Dict[str, Any]:
    """
    Returns the schema of the Maritime Knowledge Graph, including node labels,
    relationship types, property keys, and database constraints.
    """
    client = get_db_client()
    return fetch_schema(client)


# =============================================================================
# 9. Message Intelligence: search_messages
# =============================================================================

@mcp.tool(description=(
    "Search and inspect operational communications by keyword text query, exact filename, or message ID across trust tiers (T1-T4). "
    "Returns snippets or full message content and edge links. Flagged-malicious messages are withheld for security."
))
def search_messages(
    query: Optional[str] = None,
    message_id: Optional[str] = None,
    filename: Optional[str] = None,
    vessel: Optional[str] = None,
    voyage_id: Optional[str] = None,
    port: Optional[str] = None,
    incident_id: Optional[str] = None,
    kinds: Optional[List[str]] = None,
    trust_tiers: Optional[List[Literal["T1", "T2", "T3", "T4"]]] = None,
    window: Optional[Dict[str, Any]] = None,
    include_raw: bool = False,
    limit: int = 10,
    args: Optional[Any] = None,
) -> str:
    flat = {
        "query": query,
        "message_id": message_id,
        "filename": filename,
        "vessel": vessel,
        "voyage_id": voyage_id,
        "port": port,
        "incident_id": incident_id,
        "kinds": kinds,
        "trust_tiers": trust_tiers,
        "window": window,
        "include_raw": include_raw,
        "limit": limit,
    }
    inp = _build_input(SearchMessagesInput, flat, args)
    client = get_db_client()
    resp = fetch_messages(client, inp)
    return resp.to_agent_text()


# =============================================================================
# FastMCP Factory
# =============================================================================

def create_app() -> FastMCP:
    """Factory function returning the configured FastMCP server instance."""
    return mcp
