"""
FastAPI Server Entry Point for Maritime Operations AI Agent.
Provides RESTful APIs for chat turns, human-in-the-loop clarifications,
operator authentication, and system health status.
"""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ai_agent.src.utilities.logger import setup_json_logging, get_logger
from ai_agent.src.api.routes import auth_router, chat_router, system_router

# Initialize structured JSON logging
setup_json_logging()
logger = get_logger("ai_agent.api")

tags_metadata = [
    {
        "name": "Authentication",
        "description": "Operator registration, PBKDF2 credential verification, and JWT bearer token issuance.",
    },
    {
        "name": "Chat",
        "description": (
            "Multi-turn conversational operations interface powered by a 5-layer LangGraph StateGraph: "
            "Input Guardrails -> Entity Resolution & Temporal Normalization -> Data Research Planner -> "
            "Researcher (FastMCP HTTP) -> Epistemic Grounding Reviewer & Deterministic Hydration."
        ),
    },
    {
        "name": "System",
        "description": "System health diagnostics, FastMCP bridge connectivity, and Knowledge Graph schema inspection.",
    },
]

app = FastAPI(
    title="Maritime Operations AI Agent API",
    version="2.0.0",
    description="""
# Commercial Maritime Operations AI Assistant API

A production-grade, 5-layer autonomous AI Agent built on **LangGraph**, **FastMCP**, and **Neo4j Knowledge Graph**.

### Core Capabilities:
- **Strict Epistemic Grounding**: Claims are strictly partitioned into `confirmed_facts`, `unverified_reports`, and `system_inferences`.
- **Zero Hallucination Policy**: Every single fact and inference is verified against complete database records by an LLM Judge before presentation.
- **Deterministic Hydration**: Entity citations (`{node, id}`) and backing messages (`message_id`, `filename`, `trust_tier`, `sent_at_utc`) are hydrated directly from Neo4j ground truth.
- **Evidence-Based Abstention**: Explicit `no_data_reason` escape hatches (`DATA_UNAVAILABLE`) prevent inventing facts when tools return no records.
- **Human-in-the-Loop Clarification**: Automatically prompts operators when queries contain ambiguous entity references or missing voyage parameters.
    """,
    openapi_tags=tags_metadata,
    swagger_ui_parameters={"persistAuthorization": True},
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

from pathlib import Path
from fastapi.staticfiles import StaticFiles

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(system_router)

# Mount built frontend UI if dist directory exists
FRONTEND_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"
if FRONTEND_DIST.exists() and (FRONTEND_DIST / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
else:
    @app.get("/")
    def root():
        return {
            "status": "online",
            "service": "Maritime Operations AI Agent API",
            "version": "2.0.0",
            "docs": "/docs",
            "frontend": "Run 'npm --prefix frontend run dev' for development UI"
        }


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("ai_agent.src.api.main:app", host="0.0.0.0", port=port, reload=True)

