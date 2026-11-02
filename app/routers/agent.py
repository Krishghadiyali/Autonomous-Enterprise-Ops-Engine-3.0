import json
import hashlib
from typing import Any
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langgraph.types import Command
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from app.schemas.schemas import (
    QueryRequest,
    ApprovalRequest,
    LoginRequest,
    LoginResponse,
)
from app.agent.agent import ops_agent_graph
from app.db.database import get_db_connection

router = APIRouter(prefix="/agent", tags=["AI Agent"])


def _hash_password(plain_password: str) -> str:
    return hashlib.sha256(plain_password.encode("utf-8")).hexdigest()


@router.post("/login", response_model=LoginResponse)
def login_user(req: LoginRequest):
    """Authenticates a customer or administrator against MySQL and fetches their orders."""
    conn = get_db_connection(read_only=True)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT id, name, email, password_hash, role FROM customers WHERE email = %s",
            (req.email.strip().lower(),),
        )
        user = cursor.fetchone()
        if not user or user.get("password_hash") != _hash_password(req.password):
            raise HTTPException(status_code=401, detail="Invalid email or password.")

        cursor.execute(
            "SELECT id, item_name, total_amount, status FROM orders WHERE customer_id = %s ORDER BY id DESC",
            (user["id"],),
        )
        orders = cursor.fetchall() or []
        for o in orders:
            o["total_amount"] = float(o["total_amount"])

        return LoginResponse(
            customer_id=int(user["id"]),
            name=user["name"],
            email=user["email"],
            role=user.get("role") or "customer",
            orders=orders,
        )
    finally:
        cursor.close()
        conn.close()


def _extract_interrupt_payload(state: Any) -> dict:
    """Extracts the payload passed to interrupt() inside execute_tools_node."""
    try:
        for task in getattr(state, "tasks", []):
            for intr in getattr(task, "interrupts", []):
                val = getattr(intr, "value", None)
                if isinstance(val, dict):
                    return val
    except Exception:
        pass
    return {"action": "require_approval", "tool": "execute_refund"}


def _format_sse(payload: dict) -> str:
    """Formats a dict as a Server-Sent Event line."""
    return f"data: {json.dumps(payload)}\n\n"


def _summarize_node_update(node_name: str, node_output: Any) -> dict:
    """Creates a clean telemetry event for each LangGraph node transition."""
    detail = f"Executed {node_name}"
    extra = {}

    if isinstance(node_output, dict):
        if node_name == "assistant_node" and node_output.get("messages"):
            last_msg = node_output["messages"][-1]
            tool_calls = getattr(last_msg, "tool_calls", None)
            if tool_calls:
                called = ", ".join(
                    f"{tc['name']}({tc.get('args', {})})" for tc in tool_calls
                )
                detail = f"LLM decided to invoke tool: {called}"
                extra["tool_calls"] = tool_calls
            else:
                detail = "LLM synthesized final response."

        elif node_name == "execute_tools_node" and node_output.get("messages"):
            tool_msg = node_output["messages"][-1]
            t_name = getattr(tool_msg, "name", "tool")
            detail = f"Tool '{t_name}' completed."
            extra["tool_output"] = str(getattr(tool_msg, "content", ""))[:300]

        elif node_name == "crag_grader_node":
            score = node_output.get("relevance_score", "")
            detail = f"CRAG Relevance Grader scored retrieved docs: '{score.upper()}'"
            extra["relevance_score"] = score

        elif node_name == "rewrite_query_node":
            count = node_output.get("rewrite_count", 1)
            detail = f"CRAG Query Rewriter optimized search query (Attempt #{count})."
            extra["rewrite_count"] = count

    return {
        "event": "node_update",
        "node": node_name,
        "detail": detail,
        "metadata": extra,
    }


@router.post("/query/stream")
def stream_query_agent(req: QueryRequest):
    """Streams real-time LangGraph node transitions and HITL interrupts via SSE."""
    config: RunnableConfig = {
        "configurable": {"thread_id": req.thread_id},
        "tags": ["enterprise-ops-engine", "fastapi-sse"],
        "metadata": {
            "thread_id": req.thread_id,
            "customer_id": req.customer_id,
            "environment": "development",
        },
    }

    def event_generator():
        try:
            initial_input = {
                "messages": [HumanMessage(content=req.query)],
                "rewrite_count": 0,
                "customer_id": req.customer_id,
            }
            for chunk in ops_agent_graph.stream(
                initial_input, config=config, stream_mode="updates"
            ):
                for node_name, node_output in chunk.items():
                    if node_name == "__interrupt__":
                        continue
                    yield _format_sse(_summarize_node_update(node_name, node_output))

            state = ops_agent_graph.get_state(config)
            if state.next:
                interrupt_data = _extract_interrupt_payload(state)
                yield _format_sse(
                    {
                        "event": "final",
                        "status": "waiting_for_approval",
                        "thread_id": req.thread_id,
                        "response": "The agent paused to request human approval for a high-stakes database write.",
                        "pending_action": interrupt_data,
                        "pending_sql": interrupt_data.get("sql_preview"),
                    }
                )
            else:
                final_message = state.values["messages"][-1].content
                yield _format_sse(
                    {
                        "event": "final",
                        "status": "completed",
                        "thread_id": req.thread_id,
                        "response": final_message,
                        "result": final_message,
                    }
                )
        except Exception as exc:
            yield _format_sse({"event": "error", "detail": str(exc)})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/approve/stream")
def stream_approve_action(req: ApprovalRequest):
    """Resumes a paused HITL thread and streams the post-decision execution via SSE."""
    config: RunnableConfig = {
        "configurable": {"thread_id": req.thread_id},
        "tags": ["enterprise-ops-engine", "fastapi-sse"],
        "metadata": {"thread_id": req.thread_id, "environment": "development"},
    }
    state = ops_agent_graph.get_state(config)
    if not state.next:
        raise HTTPException(
            status_code=400,
            detail="No pending actions awaiting approval for this thread.",
        )

    def event_generator():
        try:
            for chunk in ops_agent_graph.stream(
                Command(resume=req.decision), config=config, stream_mode="updates"
            ):
                for node_name, node_output in chunk.items():
                    if node_name == "__interrupt__":
                        continue
                    yield _format_sse(_summarize_node_update(node_name, node_output))

            new_state = ops_agent_graph.get_state(config)
            final_message = new_state.values["messages"][-1].content
            yield _format_sse(
                {
                    "event": "final",
                    "status": "completed",
                    "thread_id": req.thread_id,
                    "response": final_message,
                    "result": final_message,
                }
            )
        except Exception as exc:
            yield _format_sse({"event": "error", "detail": str(exc)})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# --- Standard Non-Streaming Endpoints (Kept for Postman & Pytest Compatibility) ---
@router.post("/query")
def query_agent(req: QueryRequest):
    config: RunnableConfig = {
        "configurable": {"thread_id": req.thread_id},
        "tags": ["enterprise-ops-engine", "fastapi-sse"],
        "metadata": {
            "thread_id": req.thread_id,
            "customer_id": req.customer_id,
            "environment": "development",
        },
    }
    ops_agent_graph.invoke(
        {
            "messages": [HumanMessage(content=req.query)],
            "rewrite_count": 0,
            "customer_id": req.customer_id,
        },
        config=config,
    )
    state = ops_agent_graph.get_state(config)
    if state.next:
        interrupt_data = _extract_interrupt_payload(state)
        return {
            "status": "waiting_for_approval",
            "thread_id": req.thread_id,
            "message": "The agent paused to request human approval for a high-stakes action.",
            "response": "The agent paused to request human approval for a high-stakes action.",
            "pending_action": interrupt_data,
            "pending_sql": interrupt_data.get("sql_preview"),
        }
    final_message = state.values["messages"][-1].content
    return {
        "status": "completed",
        "result": final_message,
        "response": final_message,
    }


@router.post("/approve")
def approve_action(req: ApprovalRequest):
    config: RunnableConfig = {
        "configurable": {"thread_id": req.thread_id},
        "tags": ["enterprise-ops-engine", "fastapi-sse"],
        "metadata": {"thread_id": req.thread_id, "environment": "development"},
    }
    state = ops_agent_graph.get_state(config)
    if not state.next:
        raise HTTPException(
            status_code=400,
            detail="No pending actions awaiting approval for this thread.",
        )
    ops_agent_graph.invoke(Command(resume=req.decision), config=config)
    new_state = ops_agent_graph.get_state(config)
    final_message = new_state.values["messages"][-1].content
    return {
        "status": "completed",
        "result": final_message,
        "response": final_message,
    }