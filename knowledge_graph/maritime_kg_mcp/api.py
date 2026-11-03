"""FastAPI Application & Swagger UI for Maritime Knowledge Graph MCP Server.

Provides:
1. Interactive Swagger UI (/docs) and ReDoc (/redoc) for all Maritime Knowledge Graph domain tools.
2. Direct REST execution endpoints for tools (get_voyage_context, get_vessel_context, scan_voyages, etc.).
3. Tool catalog (/tools) and system health diagnostics (/health).
4. FastMCP Streamable HTTP ASGI bridge mounted on /mcp for LLM agent integration.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
import uvicorn
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

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
    ToolResponse,
)
from knowledge_graph.maritime_kg_mcp.server import (
    execute_read_query as run_execute_read_query,
    fetch_booking,
    fetch_cargo_exposure,
    fetch_incident_history,
    fetch_messages,
    fetch_port_context,
    fetch_scan_voyages,
    fetch_schema,
    fetch_vessel_context,
    fetch_voyage_context,
    mcp,
)

logger = get_logger(__name__)

mcp_tags_metadata = [
    {
        "name": "Maritime Context Tools",
        "description": (
            "Specialized operational domain tools reconstructing vessel profiles, voyage schedules, "
            "berth-window compliance, and port turnaround telemetry."
        ),
    },
    {
        "name": "Incidents & Maintenance",
        "description": (
            "Mechanical defect analysis, recurring defect clustering across sister vessels, "
            "and technical manager bulletin verification."
        ),
    },
    {
        "name": "Cargo & Commercial",
        "description": (
            "Customer-by-customer container exposure analysis, rolled cargo tracking, "
            "and promised delivery date risks."
        ),
    },
    {
        "name": "Operational Communications",
        "description": (
            "Unstructured communication intelligence (Master noon reports, port agent notices, "
            "crew WhatsApp messages) with strict 4-tier epistemic trust classification."
        ),
    },
    {
        "name": "Knowledge Graph & Schema",
        "description": (
            "Direct Knowledge Graph inspection, schema constraints, and validated read-only Cypher queries."
        ),
    },
    {
        "name": "System & Diagnostics",
        "description": (
            "Server health status, Neo4j connectivity diagnostics, tool registration catalog, "
            "and MCP protocol bridge."
        ),
    },
]

mcp_app = FastAPI(
    title="Maritime Operations Knowledge Graph MCP Server & Tools API",
    version="1.0.0",
    description="""
# Maritime Operations Knowledge Graph MCP & REST API

Production-grade FastMCP and REST server exposing specialized domain tools, message intelligence, 
and knowledge graph analytics for commercial maritime operations.

### Key Capabilities:
- **Model Context Protocol (MCP)**: Native `/mcp` Streamable HTTP endpoint for AI agents (LangChain, Claude Desktop, Antigravity).
- **Interactive Swagger UI**: Test and explore all maritime domain tools with live parameters directly at `/docs`.
- **Strict Epistemic Trust Tiers**: Communications and incidents are categorized into **T1** (Master Noon Reports), **T2** (Technical Bulletins & Agent Notices), **T3** (Crew Relays), and **T4** (Customer Forwards).
- **Temporal Anchor**: Grounded to operational snapshot `2026-10-26 12:00 UTC`.
- **Anti-Hallucination Evidence**: All tools return graph-text dossiers containing explicit `CITABLE` tags (`[Voyage:VG-1042]`, `[Incident:INC-084]`, `[File:noon_report.txt]`).

---
### Operational Tools Included:
1. `get_voyage_context`: Comprehensive voyage timeline, ETA drift, berth-window assessment, and delay reconciliation.
2. `get_vessel_context`: Vessel identity, class specifications, sister ships, technical manager, and recent incident history.
3. `scan_voyages`: Corridor and port-wide fleet discovery with automated berth-window risk classification.
4. `get_port_context`: Port operations, daily congestion metrics, anchorage wait times, and inbound traffic.
5. `search_incident_history`: Class-wide recurring defect analysis, attributed delay hours, and repair directives.
6. `get_cargo_exposure`: Customer container impacts, rollover status, and promised delivery deadline risks.
7. `track_booking`: Direct booking lookup by booking ID, customer name, or voyage.
8. `search_messages`: Full-text communication search with trust tiers and prompt-injection suppression.
9. `get_knowledge_graph_schema`: Complete Neo4j schema (13 node types, relationships, constraints).
10. `execute_read_query`: Read-only Cypher query execution (capped at 500 rows).
    """,
    openapi_tags=mcp_tags_metadata,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    swagger_ui_parameters={"persistAuthorization": True, "displayRequestDuration": True},
)

mcp_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Helper Request Models
# =============================================================================

class TrackBookingRequest(BaseModel):
    booking_id: Optional[str] = Field(
        default=None,
        description="Specific booking identifier, e.g. 'BK-0912'",
        examples=["BK-0912"]
    )
    customer_name: Optional[str] = Field(
        default=None,
        description="Customer or shipper name substring, e.g. 'Kaimon Electronics'",
        examples=["Kaimon Electronics"]
    )
    voyage_id: Optional[str] = Field(
        default=None,
        description="Assigned voyage ID, e.g. 'VG-1042'",
        examples=["VG-1042"]
    )
    limit: int = Field(default=50, ge=1, le=200, description="Maximum number of booking records to return.")


class CypherQueryRequest(BaseModel):
    query: str = Field(
        description="Read-only Cypher query to execute. Mutating statements (CREATE, MERGE, SET, DELETE) are forbidden.",
        examples=["MATCH (v:Vessel)-[:OF_CLASS]->(c:VesselClass) RETURN v.name, c.name LIMIT 10"]
    )
    parameters: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional parameter mapping for parameterized Cypher queries."
    )
    limit: int = Field(default=100, ge=1, le=500, description="Maximum number of records to return.")


class HealthResponse(BaseModel):
    status: str = Field(description="'healthy' or 'degraded'")
    service: str = Field(description="Name of the MCP service")
    neo4j: str = Field(description="Neo4j connection status")
    database: str = Field(description="Active Neo4j database name")
    tools_count: int = Field(description="Number of operational tools available")
    mcp_endpoint: str = Field(description="Path to the MCP Streamable HTTP endpoint")


class ToolInfo(BaseModel):
    name: str = Field(description="Tool identifier used by MCP clients")
    description: str = Field(description="Detailed tool purpose and usage instructions")
    parameters_schema: Dict[str, Any] = Field(description="JSON Schema describing valid tool input arguments")


class ToolCatalogResponse(BaseModel):
    service: str
    tools: List[ToolInfo]


# =============================================================================
# System & Diagnostic Endpoints
# =============================================================================

@mcp_app.get(
    "/",
    summary="Service Index",
    tags=["System & Diagnostics"],
    description="Returns service metadata, health status, and direct links to documentation."
)
def root():
    return {
        "service": "Maritime Operations Knowledge Graph FastMCP Server",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc",
        "openapi_spec": "/openapi.json",
        "mcp_streamable_http": "/mcp",
        "tools_catalog": "/tools",
        "health": "/health",
    }


@mcp_app.get(
    "/health",
    response_model=HealthResponse,
    summary="Server & Knowledge Graph Health Check",
    tags=["System & Diagnostics"],
    description="Tests live connectivity to the Neo4j Knowledge Graph and reports driver health."
)
def health_check():
    client = get_db_client()
    neo4j_status = "connected"
    try:
        res = client.execute_read_query("RETURN 1 AS ping")
        if not res:
            neo4j_status = "error: no response"
    except Exception as exc:
        neo4j_status = f"error: {str(exc)}"

    return {
        "status": "healthy" if neo4j_status == "connected" else "degraded",
        "service": "maritime-kg-mcp",
        "neo4j": neo4j_status,
        "database": getattr(client, "_database", "maritime-kg") or "maritime-kg",
        "tools_count": 10,
        "mcp_endpoint": "/mcp"
    }


@mcp_app.get(
    "/tools",
    response_model=ToolCatalogResponse,
    summary="List Registered MCP Tools",
    tags=["System & Diagnostics"],
    description="Returns the complete catalog of MCP tools registered on this server, including full parameter schemas."
)
def list_tools():
    tools_catalog: List[ToolInfo] = [
        ToolInfo(
            name="get_voyage_context",
            description="Fetches full operational dossier for one or more voyages: schedule, ETA drift, berth windows, delay reconciliation, incidents, bookings, and operational gaps.",
            parameters_schema=GetVoyageContextInput.model_json_schema()
        ),
        ToolInfo(
            name="get_vessel_context",
            description="Returns comprehensive profile for a vessel: class specifications, sister ships, active manager fleet, active voyage, and historical incidents.",
            parameters_schema=GetVesselContextInput.model_json_schema()
        ),
        ToolInfo(
            name="scan_voyages",
            description="Scans and ranks fleet voyages arriving/departing in a time window with automated berth-window adherence and risk scoring.",
            parameters_schema=ScanVoyagesInput.model_json_schema()
        ),
        ToolInfo(
            name="get_port_context",
            description="Retrieves port operations, local timezone, port agents, daily congestion series, average anchorage wait, and inbound vessels.",
            parameters_schema=GetPortContextInput.model_json_schema()
        ),
        ToolInfo(
            name="search_incident_history",
            description="Analyzes recurring defects across vessel, class, technical manager, or fleet scopes, with linked technical bulletins and repair directives.",
            parameters_schema=SearchIncidentHistoryInput.model_json_schema()
        ),
        ToolInfo(
            name="get_cargo_exposure",
            description="Evaluates customer container volumes, rolled bookings, and promised delivery date risks for a voyage.",
            parameters_schema=GetCargoExposureInput.model_json_schema()
        ),
        ToolInfo(
            name="track_booking",
            description="Tracks commercial cargo bookings by booking ID, customer name, or assigned voyage.",
            parameters_schema=TrackBookingRequest.model_json_schema()
        ),
        ToolInfo(
            name="search_messages",
            description="Searches operational communications (noon reports, agent notices, crew relays) with trust tier classification and prompt-injection filtering.",
            parameters_schema=SearchMessagesInput.model_json_schema()
        ),
        ToolInfo(
            name="get_knowledge_graph_schema",
            description="Returns node labels, relationship types, property keys, and database constraints of the Maritime Knowledge Graph.",
            parameters_schema={"type": "object", "properties": {}}
        ),
        ToolInfo(
            name="execute_read_query",
            description="Executes a read-only Cypher query against the Maritime Knowledge Graph (capped at 500 rows). Mutating queries are forbidden.",
            parameters_schema=CypherQueryRequest.model_json_schema()
        ),
    ]
    return {
        "service": "maritime-kg-mcp",
        "tools": tools_catalog
    }


# =============================================================================
# Domain Tools REST Endpoints
# =============================================================================

@mcp_app.post(
    "/api/v1/tools/get_voyage_context",
    response_model=ToolResponse,
    summary="Get Voyage Context",
    tags=["Maritime Context Tools"],
    description="""
Reconstructs the complete operational lifecycle of a voyage.
- Reconciles cumulative recorded delay against ETA drift and confirmed incidents.
- Evaluates berth-window adherence (`INSIDE_WINDOW`, `EARLY`, `LATE`).
- Retrieves linked incidents, port calls, bookings summary, and backing messages.
- Returns an operational graph-text body along with a list of verified `CITABLE` tags.
"""
)
def api_get_voyage_context(req: GetVoyageContextInput):
    client = get_db_client()
    return fetch_voyage_context(client, req)


@mcp_app.post(
    "/api/v1/tools/get_vessel_context",
    response_model=ToolResponse,
    summary="Get Vessel Context",
    tags=["Maritime Context Tools"],
    description="""
Retrieves complete vessel identity and operational context:
- Identifies vessel design class (`Meridian 8500`, `Atlas 6000`, etc.) and technical manager.
- Discovers sister vessels belonging to the same design class.
- Reconstructs active/recent operational voyages and incident history.
"""
)
def api_get_vessel_context(req: GetVesselContextInput):
    client = get_db_client()
    return fetch_vessel_context(client, req)


@mcp_app.post(
    "/api/v1/tools/scan_voyages",
    response_model=ToolResponse,
    summary="Scan Fleet Voyages",
    tags=["Maritime Context Tools"],
    description="""
Discovers and ranks fleet voyages arriving or departing across corridors or ports within a time window.
- Computes berth-window risk scores and flags vessels likely to miss their scheduled windows.
- Injects destination port congestion metrics around expected arrival dates.
"""
)
def api_scan_voyages(req: ScanVoyagesInput):
    client = get_db_client()
    return fetch_scan_voyages(client, req)


@mcp_app.post(
    "/api/v1/tools/get_port_context",
    response_model=ToolResponse,
    summary="Get Port Operations & Congestion",
    tags=["Maritime Context Tools"],
    description="""
Retrieves port operations, local timezone, official port agents, and congestion telemetry:
- Daily congestion time-series, peak/average wait times, and vessels at anchor.
- Turnaround telemetry for recent port calls (anchorage wait vs. berth stay hours).
- Inbound traffic schedule with berth-window adherence estimates.
"""
)
def api_get_port_context(req: GetPortContextInput):
    client = get_db_client()
    return fetch_port_context(client, req)


@mcp_app.post(
    "/api/v1/tools/search_incident_history",
    response_model=ToolResponse,
    summary="Search Incident History & Sister Ship Recurrence",
    tags=["Incidents & Maintenance"],
    description="""
Analyzes equipment failures and delays across multiple operational scopes:
- Scope hierarchy: `vessel` -> `class` (sister ships) -> `manager` (fleet-wide) -> `fleet`.
- Groups recurring defects, calculates total attributed delay hours, and checks for superseding technical bulletins.
"""
)
def api_search_incident_history(req: SearchIncidentHistoryInput):
    client = get_db_client()
    return fetch_incident_history(client, req)


@mcp_app.post(
    "/api/v1/tools/get_cargo_exposure",
    response_model=ToolResponse,
    summary="Get Cargo Exposure & Rolled Bookings",
    tags=["Cargo & Commercial"],
    description="""
Calculates customer container volumes and delivery deadline risks for a voyage:
- Categorizes cargo into **Confirmed (On Board)**, **Rolled (Transferred to target voyage)**, and **Cancelled**.
- Calculates delivery margin (days between revised ETA and promised delivery date).
- Flags critical delivery risks when ETA drifts past customer promised dates.
"""
)
def api_get_cargo_exposure(req: GetCargoExposureInput):
    client = get_db_client()
    return fetch_cargo_exposure(client, req)


@mcp_app.post(
    "/api/v1/tools/track_booking",
    summary="Track Cargo Booking",
    tags=["Cargo & Commercial"],
    description="Direct commercial booking verification by booking ID, customer name, or assigned voyage."
)
def api_track_booking(req: TrackBookingRequest):
    client = get_db_client()
    return fetch_booking(client, req.booking_id, req.customer_name, req.voyage_id, limit=req.limit)


@mcp_app.post(
    "/api/v1/tools/search_messages",
    response_model=ToolResponse,
    summary="Search Operational Communications",
    tags=["Operational Communications"],
    description="""
Searches primary operational messages (noon reports, agent emails, technical bulletins, crew relays):
- Enforces 4-tier epistemic hierarchy: **T1** (Master Noon Report), **T2** (Technical Bulletin / Port Agent Notice), **T3** (Crew Message), **T4** (Customer Forward).
- Automatically suppresses messages flagged with `is_malicious = true` from prompt context.
"""
)
def api_search_messages(req: SearchMessagesInput):
    client = get_db_client()
    return fetch_messages(client, req)


@mcp_app.get(
    "/api/v1/tools/get_knowledge_graph_schema",
    summary="Get Knowledge Graph Schema",
    tags=["Knowledge Graph & Cypher"],
    description="Returns node labels, relationship types, property keys, and database constraints in the Maritime Knowledge Graph."
)
def api_get_knowledge_graph_schema():
    client = get_db_client()
    return fetch_schema(client)


@mcp_app.post(
    "/api/v1/tools/execute_read_query",
    summary="Execute Read-Only Cypher Query",
    tags=["Knowledge Graph & Cypher"],
    description="""
Executes an arbitrary read-only Cypher query against Neo4j.
- Validates that no mutating operations (CREATE, MERGE, SET, DELETE, DROP) are present.
- Results are capped at 500 records.
"""
)
def api_execute_read_query(req: CypherQueryRequest):
    client = get_db_client()
    return run_execute_read_query(req.query, parameters=req.parameters, limit=req.limit)


# =============================================================================
# Mount FastMCP Streamable HTTP ASGI App on /mcp
# =============================================================================

# Mount FastMCP streamable-http app on /mcp so AI Agent and MCP clients connect seamlessly
mcp_sub_asgi = mcp.http_app(path="/")
mcp_app.mount("/mcp", mcp_sub_asgi)

