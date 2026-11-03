"""
FastAPI Server Entry Point for Maritime Operations AI Agent.
Provides RESTful APIs for chat turns, human-in-the-loop clarifications,
operator authentication, and system health status.
"""

from __future__ import annotations

import os
from pathlib import Path
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ai_agent.src.utilities.logger import setup_json_logging, get_logger
from ai_agent.src.api.routes import auth_router, chat_router, system_router

# Initialize structured JSON logging
setup_json_logging()
logger = get_logger("ai_agent.api")

tags_metadata = [
    {
        "name": "Chat",
        "description": (
            "Multi-turn operational maritime intelligence interface powered by an autonomous 5-layer LangGraph pipeline. "
            "Enforces strict 3-way epistemic segregation (Confirmed Facts, Unverified Reports, System Inferences), "
            "deterministic citation hydration from Neo4j, and zero-hallucination abstention."
        ),
    },
    {
        "name": "Authentication",
        "description": (
            "Operator identity management: registration, PBKDF2-SHA256 credential hashing, "
            "and signed JWT bearer token issuance for fleet dispatchers, port captains, and superintendents."
        ),
    },
    {
        "name": "System",
        "description": (
            "System health diagnostics, Neo4j Knowledge Graph connectivity verification, "
            "LLM provider runtime inspection, and graph schema discovery."
        ),
    },
]

app = FastAPI(
    title="Commercial Maritime Operations AI Assistant API",
    version="2.0.0",
    description="""
# Commercial Maritime Operations AI Assistant API

A production-grade, autonomous maritime intelligence system built on **LangGraph**, **FastMCP**, and **Neo4j Knowledge Graph**.
Provides real-time decision support for fleet superintendents, operations directors, and logistics dispatchers.

---

### Core Pipeline Architecture (5-Layer StateGraph):

```
User Query
   │
   ▼
[1. Input Guardrail] ─────────► (Blocks prompt injection, SQL/Cypher jailbreaks & out-of-scope requests)
   │
   ▼
[2. Entity Resolution] ──────► (Resolves vessels, IMO, UN/LOCODE ports; anchors dates to 2026-10-26 12:00 UTC)
   │
   ▼
[3. Research Planner] ───────► (Generates sequenced tool plan across specialized maritime MCP domain tools)
   │
   ▼
[4. ReAct Researcher] ───────► (Calls FastMCP HTTP server with exponential backoff & full jitter retry)
   │
   ▼
[5. Grounding Reviewer] ─────► (Strict epistemic segregation & deterministic hydration of backing messages)
   │
   ▼
Final Structured Response
```

---

### Strict Epistemic Grounding Contract:
Every assistant response separates findings into three non-overlapping certainty tiers:
1. **Confirmed Facts**: Grounded solely in verified database records (Vessel, Voyage, PortCall, Congestion, Booking) or authoritative T1 (Master Noon Reports) / T2 (Technical Bulletins) communications.
2. **Unverified Reports**: Sourced from pending/reported incidents, dismissed incidents, or informal T3 (Crew WhatsApp) / T4 (Customer Forwards) communications that lack corroboration.
3. **System Inferences**: Reconciled delay hours, berth-window risk margins, and operational projections, each accompanied by an explicit deduction rationale.

---

### Response Status Lifecycle:
- `SUCCESS`: Complete, verified synthesis backed by Knowledge Graph citations.
- `DATA_UNAVAILABLE`: Honest evidence-based abstention with `no_data_reason` when records do not exist.
- `CLARIFICATION_NEEDED`: Multi-choice prompt when query references ambiguous vessels or missing parameters.
- `FALSE_PREMISE`: Explicit reality check when a query rests on an incorrect assumption.
- `OUT_OF_SCOPE_REFUSAL`: Safe refusal when input violates maritime operational domain boundaries.
    """,
    openapi_tags=tags_metadata,
    contact={
        "name": "Nautilus AI Maritime Intelligence Team (Gokul Panneer Selvam)",
        "url": "https://github.com/gokulpannerselvam02",
        "email": "operations@nautilus-maritime.ai",
    },
    license_info={
        "name": "Commercial Maritime Ops License",
    },
    swagger_ui_parameters={
        "persistAuthorization": True,
        "displayRequestDuration": True,
        "docExpansion": "list",
        "defaultModelsExpandDepth": 3,
    },
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(system_router)

# Mount built frontend UI if dist directory exists
FRONTEND_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"
if FRONTEND_DIST.exists() and (FRONTEND_DIST / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
else:
    @app.get(
        "/",
        summary="Service Index",
        tags=["System"],
        description="Root entrypoint returning API metadata, documentation links, and frontend availability."
    )
    def root():
        return {
            "status": "online",
            "service": "Commercial Maritime Operations AI Assistant API",
            "version": "2.0.0",
            "docs": "/docs",
            "redoc": "/redoc",
            "openapi": "/openapi.json",
            "mcp_server": "http://localhost:8000/docs",
            "frontend": "Run 'npm --prefix frontend run dev' for development UI"
        }


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("ai_agent.src.api.main:app", host="0.0.0.0", port=port, reload=True)
