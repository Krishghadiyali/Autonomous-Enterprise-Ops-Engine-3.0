import json
import uuid
import os
import requests
import streamlit as st

# -----------------------------------------------------------------------------
# Configuration (Matches app/routers/agent.py routes)
# -----------------------------------------------------------------------------
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
LOGIN_ENDPOINT = f"{API_BASE_URL}/agent/login"
QUERY_STREAM_ENDPOINT = f"{API_BASE_URL}/agent/query/stream"
APPROVE_STREAM_ENDPOINT = f"{API_BASE_URL}/agent/approve/stream"
HEALTH_ENDPOINT = f"{API_BASE_URL}/health"

st.set_page_config(
    page_title="Enterprise Ops Engine | Secure Console",
    page_icon="🔐",
    layout="wide",
)

# -----------------------------------------------------------------------------
# Session State Initialization
# -----------------------------------------------------------------------------
if "authenticated_user" not in st.session_state:
    st.session_state.authenticated_user = None

if "thread_id" not in st.session_state:
    st.session_state.thread_id = f"ops-{uuid.uuid4().hex[:8]}"

if "messages" not in st.session_state:
    st.session_state.messages = []

if "interrupted_state" not in st.session_state:
    st.session_state.interrupted_state = None


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------
def check_backend_health() -> bool:
    try:
        res = requests.get(HEALTH_ENDPOINT, timeout=3)
        return res.status_code == 200
    except requests.RequestException:
        return False


def refresh_user_orders():
    """Re-fetches the logged-in user's orders after a refund execution."""
    user = st.session_state.authenticated_user
    if not user or "_password" not in user:
        return
    try:
        res = requests.post(
            LOGIN_ENDPOINT,
            json={"email": user["email"], "password": user["_password"]},
            timeout=5,
        )
        if res.status_code == 200:
            updated = res.json()
            updated["_password"] = user["_password"]
            st.session_state.authenticated_user = updated
    except requests.RequestException:
        pass


def consume_sse_stream(url: str, payload: dict, status_box) -> dict:
    """Streams Server-Sent Events from FastAPI and renders live node transitions."""
    trace_steps = []
    final_payload = {}

    with requests.post(url, json=payload, stream=True, timeout=120) as response:
        response.raise_for_status()
        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line or not raw_line.startswith("data: "):
                continue
            event_data = json.loads(raw_line[6:])
            event_type = event_data.get("event")

            if event_type == "node_update":
                node_name = event_data.get("node", "node")
                detail = event_data.get("detail", "")
                status_box.write(f"🔹 **`{node_name}`**: {detail}")
                trace_steps.append(event_data)

            elif event_type == "error":
                raise RuntimeError(event_data.get("detail", "Unknown streaming error"))

            elif event_type == "final":
                final_payload = event_data
                final_payload["trace_steps"] = trace_steps

    return final_payload


# -----------------------------------------------------------------------------
# GATE 1: Security Login Screen (Shown when user is not logged in)
# -----------------------------------------------------------------------------
if st.session_state.authenticated_user is None:
    _, center_col, _ = st.columns([1, 1.4, 1])
    with center_col:
        st.markdown("## 🔐 Enterprise Ops Security Gate")
        st.caption(
            "Sign in with your customer account. Once authenticated, your orders and refund amounts "
            "are automatically resolved from MySQL—no need to enter Prompt IDs, Order IDs, or Refund Amounts."
        )

        if check_backend_health():
            st.success("FastAPI Backend: Online")
        else:
            st.error("FastAPI Backend: Offline (Start Uvicorn on :8000)")

        with st.form("login_form", clear_on_submit=False):
            email_input = st.text_input(
                "Email Address", value="alice@example.com", placeholder="alice@example.com"
            )
            password_input = st.text_input(
                "Password", value="alice123", type="password"
            )
            submit_login = st.form_submit_button(
                "🔓 Sign In to Operations Console", type="primary", use_container_width=True
            )

            if submit_login:
                try:
                    resp = requests.post(
                        LOGIN_ENDPOINT,
                        json={"email": email_input, "password": password_input},
                        timeout=10,
                    )
                    if resp.status_code == 200:
                        user_data = resp.json()
                        user_data["_password"] = password_input
                        st.session_state.authenticated_user = user_data
                        st.session_state.thread_id = (
                            f"cust-{user_data['customer_id']}-{uuid.uuid4().hex[:6]}"
                        )
                        st.session_state.messages = []
                        st.session_state.interrupted_state = None
                        st.rerun()
                    else:
                        err_detail = resp.json().get("detail", "Authentication failed.")
                        st.error(f"Access Denied: {err_detail}")
                except requests.RequestException as exc:
                    st.error(f"Could not connect to FastAPI backend: {exc}")

        with st.expander("📋 Demo Credentials (Seeded in MySQL)", expanded=True):
            st.markdown(
                "- **Alice Smith (Customer #1):** `alice@example.com` / `alice123` *(Orders #999 [$50 Delivered], #404 [$1200 Processing])*\n"
                "- **Bob Jones (Customer #2):** `bob@example.com` / `bob123` *(Order #555 [$150 Delivered])*\n"
                "- **Enterprise Admin:** `admin@example.com` / `admin123`"
            )
    st.stop()


# -----------------------------------------------------------------------------
# GATE 2: Authenticated Console
# -----------------------------------------------------------------------------
current_user = st.session_state.authenticated_user

with st.sidebar:
    st.title("⚙️ Ops Engine Control")
    st.markdown(
        f"**👤 Logged in as:** `{current_user['name']}`\n\n"
        f"**📧 Email:** `{current_user['email']}`\n\n"
        f"**🛡️ Customer ID:** `#{current_user['customer_id']}`"
    )

    if st.button("🔒 Sign Out", use_container_width=True):
        st.session_state.authenticated_user = None
        st.session_state.messages = []
        st.session_state.interrupted_state = None
        st.rerun()

    st.divider()
    st.subheader("📦 My Linked Orders")
    user_orders = current_user.get("orders", [])
    if user_orders:
        for order in user_orders:
            st.markdown(
                f"**Order #{order['id']}** — `{order['status'].upper()}`\n"
                f"*{order.get('item_name', 'Order')}* • **${order['total_amount']:.2f}**"
            )
    else:
        st.caption("No orders linked to this account.")

    st.divider()
    if st.button("➕ Reset Conversation", use_container_width=True):
        st.session_state.thread_id = (
            f"cust-{current_user['customer_id']}-{uuid.uuid4().hex[:6]}"
        )
        st.session_state.messages = []
        st.session_state.interrupted_state = None
        st.rerun()

    st.caption(f"Session Thread: `{st.session_state.thread_id}`")

# -----------------------------------------------------------------------------
# Main Layout: Two Columns (Conversation Feed vs. HITL & Telemetry Inspector)
# -----------------------------------------------------------------------------
st.subheader(f"Autonomous Enterprise Operations Console — Welcome, {current_user['name']}")
chat_col, inspector_col = st.columns([1.6, 1], gap="large")

with chat_col:
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("metadata"):
                with st.expander("View Execution Trace & State Payload"):
                    st.json(msg["metadata"])

    input_disabled = st.session_state.interrupted_state is not None
    user_prompt = st.chat_input(
        "Try: 'Refund my delivered order because it arrived damaged' (No Order ID or Amount needed!)",
        disabled=input_disabled,
    )

    if user_prompt:
        st.session_state.messages.append({"role": "user", "content": user_prompt})
        with st.chat_message("user"):
            st.markdown(user_prompt)

        with st.chat_message("assistant"):
            with st.status("Streaming LangGraph execution...", expanded=True) as status_box:
                try:
                    data = consume_sse_stream(
                        QUERY_STREAM_ENDPOINT,
                        {
                            "query": user_prompt,
                            "thread_id": st.session_state.thread_id,
                            "customer_id": current_user["customer_id"],
                        },
                        status_box,
                    )
                    agent_status = data.get("status", "completed").lower()
                    answer = (
                        data.get("response")
                        or data.get("result")
                        or data.get("message")
                        or str(data)
                    )

                    if agent_status in [
                        "waiting_for_approval",
                        "interrupted",
                        "pending_approval",
                        "requires_approval",
                    ]:
                        status_box.update(
                            label="⏸️ Graph Paused: Human-in-the-Loop Approval Required",
                            state="error",
                            expanded=True,
                        )
                        st.warning(answer)
                        st.session_state.interrupted_state = data
                        st.session_state.messages.append(
                            {
                                "role": "assistant",
                                "content": f"⏸️ **HITL Gate Triggered:** {answer}",
                                "metadata": data,
                            }
                        )
                        st.rerun()
                    else:
                        status_box.update(
                            label="✅ Workflow Completed", state="complete", expanded=False
                        )
                        st.markdown(answer)
                        st.session_state.messages.append(
                            {"role": "assistant", "content": answer, "metadata": data}
                        )

                except Exception as exc:
                    status_box.update(label="❌ Execution Failed", state="error")
                    st.error(f"FastAPI Stream Error: {exc}")

# -----------------------------------------------------------------------------
# Right Column: Human-in-the-Loop (HITL) Approval Gate & State Inspector
# -----------------------------------------------------------------------------
with inspector_col:
    st.markdown("### 🛡️ Governance & HITL Gate")

    if st.session_state.interrupted_state:
        pending_data = st.session_state.interrupted_state
        pending_action = pending_data.get("pending_action", {})
        pending_sql = pending_data.get("pending_sql") or json.dumps(
            pending_action, indent=2
        )

        st.error("⚠️ **High-Stakes Database Mutation Intercepted**")
        st.markdown(
            "The agent invoked `execute_refund` with auto-resolved order and amount details. "
            "Execution is frozen at `interrupt()` until an administrator decides:"
        )

        if isinstance(pending_action, dict) and pending_action.get("args"):
            st.markdown("**Intercepted & Auto-Resolved Tool Arguments:**")
            st.json(pending_action["args"])

        st.markdown("**Pending SQL Transaction Preview:**")
        st.code(str(pending_sql), language="sql")

        btn_col1, btn_col2 = st.columns(2)

        with btn_col1:
            if st.button("✅ Approve & Execute", type="primary", use_container_width=True):
                with st.status("Resuming LangGraph thread (decision='approve')...", expanded=True) as resume_box:
                    try:
                        res = consume_sse_stream(
                            APPROVE_STREAM_ENDPOINT,
                            {"thread_id": st.session_state.thread_id, "decision": "approve"},
                            resume_box,
                        )
                        final_msg = (
                            res.get("response")
                            or res.get("result")
                            or "Operation approved and executed."
                        )
                        resume_box.update(label="✅ Refund Executed", state="complete")
                        st.session_state.messages.append(
                            {
                                "role": "assistant",
                                "content": f"✅ **Approved & Executed:**\n\n{final_msg}",
                                "metadata": res,
                            }
                        )
                        st.session_state.interrupted_state = None
                        refresh_user_orders()
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Approval failed: {exc}")

        with btn_col2:
            if st.button("🛑 Reject Operation", use_container_width=True):
                with st.status("Resuming LangGraph thread (decision='reject')...", expanded=True) as reject_box:
                    try:
                        res = consume_sse_stream(
                            APPROVE_STREAM_ENDPOINT,
                            {"thread_id": st.session_state.thread_id, "decision": "reject"},
                            reject_box,
                        )
                        final_msg = (
                            res.get("response")
                            or res.get("result")
                            or "Operation rejected by administrator."
                        )
                        reject_box.update(label="🛑 Operation Cancelled", state="complete")
                        st.session_state.messages.append(
                            {
                                "role": "assistant",
                                "content": f"🛑 **Operation Rejected:**\n\n{final_msg}",
                                "metadata": res,
                            }
                        )
                        st.session_state.interrupted_state = None
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Rejection failed: {exc}")
    else:
        st.info("No pending approvals. Read-only SQL lookups and policy RAG queries execute autonomously.")
        if st.session_state.messages:
            last_meta = st.session_state.messages[-1].get("metadata")
            if last_meta:
                st.markdown("#### Latest Graph Trace & Telemetry")
                st.json(last_meta)