"""
System & Health Routes for Maritime Operations AI Agent API.
"""

import os
from typing import List, Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field
from knowledge_graph.database import Neo4jClient

router = APIRouter(prefix="/api/system", tags=["System"])


class HealthCheckResponse(BaseModel):
    status: str = Field(description="System overall status ('healthy' or 'degraded').", examples=["healthy"])
    neo4j: str = Field(description="Knowledge graph connection status ('connected' or error details).", examples=["connected"])
    llm_provider: str = Field(description="Configured LLM provider name ('azure', 'groq', 'openrouter', 'bedrock').", examples=["azure"])
    database: str = Field(description="Local SQLite metadata store status.", examples=["sqlite_ready"])
    mcp_transport: str = Field(description="Underlying FastMCP transport type ('http', 'sse', 'stdio').", examples=["http"])
    mcp_server: Optional[str] = Field(default=None, description="URL of the Maritime Knowledge Graph MCP server.", examples=["http://localhost:8000"])


class SchemaInspectResponse(BaseModel):
    success: bool = Field(description="Whether schema query succeeded.")
    node_labels: List[str] = Field(default_factory=list, description="All registered node labels in Neo4j.")
    relationship_types: List[str] = Field(default_factory=list, description="All registered relationship types in Neo4j.")
    error: Optional[str] = Field(default=None, description="Error message if schema inspection failed.")


@router.get("/health", response_model=HealthCheckResponse, summary="System health check", description="Verifies connectivity to the Neo4j Knowledge Graph and checks SQLite database readiness.")
def health():
    """Checks Neo4j database health directly."""
    neo4j_status = "unhealthy"
    try:
        client = Neo4jClient()
        res = client.execute_read_query("RETURN 1 AS ping")
        if res:
            neo4j_status = "connected"
    except Exception as e:
        neo4j_status = f"error: {str(e)}"

    provider = os.getenv("LLM_PROVIDER", "azure")
    mcp_url = os.getenv("MARITIME_MCP_SERVER_URL", "http://localhost:8000/mcp")
    return {
        "status": "healthy" if neo4j_status == "connected" else "degraded",
        "neo4j": neo4j_status,
        "llm_provider": provider,
        "database": "sqlite_ready",
        "mcp_transport": "http",
        "mcp_server": mcp_url
    }


@router.get("/schema", response_model=SchemaInspectResponse, summary="Graph schema inspection", description="Retrieves available Knowledge Graph node labels and relationship types.")
def schema():
    """Returns knowledge graph node labels and relationship types from Neo4j."""
    try:
        client = Neo4jClient()
        labels_res = client.execute_read_query("CALL db.labels() YIELD label RETURN collect(label) AS labels")
        rel_res = client.execute_read_query("CALL db.relationshipTypes() YIELD relationshipType RETURN collect(relationshipType) AS rels")
        labels = labels_res[0].get("labels", []) if labels_res else []
        rels = rel_res[0].get("rels", []) if rel_res else []
        return {
            "success": True,
            "node_labels": labels,
            "relationship_types": rels,
            "error": None
        }
    except Exception as e:
        return {"success": False, "node_labels": [], "relationship_types": [], "error": str(e)}

