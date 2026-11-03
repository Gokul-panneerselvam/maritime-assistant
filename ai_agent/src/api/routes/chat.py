"""
Chat & Thread Routes for Maritime Operations AI Agent API.
Handles multi-turn conversational operations, LangGraph invocation, and audit logging.
"""

import time
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage

from ai_agent.src.utilities.logger import get_logger
from ai_agent.src.schemas.epistemic import MaritimeAgentResponse, ClarificationPrompt
from ai_agent.src.repo.database import (
    create_or_get_thread,
    list_user_threads,
    get_thread_history,
    save_message,
    log_audit_trail,
    update_thread_title,
    get_db_connection
)
from ai_agent.src.api.dependencies import get_current_user
from ai_agent.src.agent.graph import get_graph

logger = get_logger(__name__)
router = APIRouter(prefix="/api/chat", tags=["Chat"])


class ChatRequest(BaseModel):
    thread_id: Optional[str] = Field(
        default=None,
        description="Optional existing session/thread ID. If omitted, a new thread is created automatically."
    )
    message: str = Field(
        description="Operational maritime query or instruction from the operator."
    )


class ChatTurnResponse(BaseModel):
    thread_id: str = Field(description="Unique conversation session/thread identifier.")
    response: Optional[MaritimeAgentResponse] = Field(
        default=None,
        description="Epistemically grounded maritime assistant response with facts, inferences, and citations."
    )
    is_interrupted: bool = Field(
        default=False,
        description="Whether execution was interrupted for external review."
    )
    needs_clarification: bool = Field(
        default=False,
        description="True if query entities were ambiguous and require user clarification."
    )


class ThreadSummary(BaseModel):
    thread_id: str = Field(description="Thread session identifier.")
    title: Optional[str] = Field(default=None, description="Thread subject summary.")
    created_at: Optional[str] = Field(default=None, description="Session creation timestamp.")
    updated_at: Optional[str] = Field(default=None, description="Last activity timestamp.")


class ThreadListResponse(BaseModel):
    threads: List[ThreadSummary] = Field(
        default_factory=list,
        description="List of active conversation threads belonging to the operator."
    )


class ThreadHistoryResponse(BaseModel):
    thread_id: str = Field(description="Thread session identifier.")
    messages: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Chronological message history including roles, text, and structured payloads."
    )


class DeleteThreadResponse(BaseModel):
    deleted: bool = Field(description="Whether the thread was successfully removed.")
    thread_id: str = Field(description="ID of the deleted thread.")


@router.post("", response_model=ChatTurnResponse, summary="Send chat message", description="Submits a natural-language query to the 5-layer maritime operations agent pipeline.")
async def chat(req: ChatRequest, current_user: dict = Depends(get_current_user)):
    """Processes a user prompt through the LangGraph pipeline."""
    start_time = time.time()
    user_id = current_user["user_id"]
    
    # 1. Thread management
    thread_id = create_or_get_thread(
        req.thread_id,
        user_id=user_id,
        title=req.message[:40] + ("..." if len(req.message) > 40 else "")
    )
    save_message(thread_id, role="user", content=req.message)

    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    try:
        result_state = await graph.ainvoke(
            {
                "user_query": req.message,
                "messages": [HumanMessage(content=req.message)],
                "validation_retries": 0
            },
            config=config
        )
        final_response: Optional[MaritimeAgentResponse] = result_state.get("final_response")
        latency_ms = (time.time() - start_time) * 1000

        # When entity resolution requires clarification, return a structured CLARIFICATION_NEEDED response
        if not final_response and result_state.get("needs_clarification"):
            clarification_text = result_state.get(
                "clarification_response",
                "Could you please provide more details to clarify your request?"
            )
            final_response = MaritimeAgentResponse(
                status="CLARIFICATION_NEEDED",
                executive_summary=clarification_text,
                confirmed_facts=[],
                unverified_reports=[],
                system_inferences=[],
                false_premises_detected=[],
                clarification=ClarificationPrompt(
                    question=clarification_text,
                    reason="Ambiguous entity reference requires clarification.",
                    options=[]
                ),
                citations=[],
                cypher_queries_executed=[]
            )

        # Save assistant structured turn
        if final_response:
            save_message(
                thread_id,
                role="assistant",
                content=final_response.executive_summary,
                structured_payload=final_response.model_dump()
            )
            log_audit_trail(
                user_id=user_id,
                thread_id=thread_id,
                user_query=req.message,
                cypher_queries=final_response.cypher_queries_executed,
                validation_status=final_response.status,
                latency_ms=latency_ms
            )

        return {
            "thread_id": thread_id,
            "response": final_response,
            "is_interrupted": False,
            "needs_clarification": bool(result_state.get("needs_clarification", False))
        }

    except Exception as e:
        logger.error("Chat invocation failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent workflow error: {str(e)}"
        )


@router.get("/threads", response_model=ThreadListResponse, summary="List conversation threads", description="Retrieves active threads and sessions for the authenticated operator.")
def get_threads(current_user: dict = Depends(get_current_user)):
    """Lists all conversation sessions for the authenticated operator."""
    threads = list_user_threads(current_user["user_id"])
    return {"threads": threads}


@router.get("/threads/{thread_id}/history", response_model=ThreadHistoryResponse, summary="Get thread history", description="Fetches all previous turns, text, and structured epistemic payloads for a specific thread.")
def get_history(thread_id: str, current_user: dict = Depends(get_current_user)):
    """Fetches full historical turns with structured payloads for a thread."""
    messages = get_thread_history(thread_id)
    return {"thread_id": thread_id, "messages": messages}


@router.delete("/threads/{thread_id}", response_model=DeleteThreadResponse, summary="Delete conversation thread", description="Deletes an entire thread session and all associated turn messages.")
def delete_thread(thread_id: str, current_user: dict = Depends(get_current_user)):
    """Deletes a thread and its messages."""
    conn = get_db_connection()
    conn.execute("DELETE FROM threads WHERE thread_id = ? AND user_id = ?;", (thread_id, current_user["user_id"]))
    conn.commit()
    conn.close()
    return {"deleted": True, "thread_id": thread_id}
