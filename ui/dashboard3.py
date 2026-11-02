import json
import time
import uuid
import os
import requests
import streamlit as st
import streamlit.components.v1 as components

# -----------------------------------------------------------------------------
# Configuration (Matches app/routers/agent.py routes)
# -----------------------------------------------------------------------------
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
LOGIN_ENDPOINT = f"{API_BASE_URL}/agent/login"
QUERY_STREAM_ENDPOINT = f"{API_BASE_URL}/agent/query/stream"
APPROVE_STREAM_ENDPOINT = f"{API_BASE_URL}/agent/approve/stream"
HEALTH_ENDPOINT = f"{API_BASE_URL}/health"

st.set_page_config(
    page_title="Enterprise Ops Engine | Live SSE Graph Console",
    page_icon="⚙️",
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

if "graph_visual_state" not in st.session_state:
    st.session_state.graph_visual_state = {
        "active_node": None,
        "from_node": None,
        "to_node": None,
        "visited_nodes": [],
        "status_mode": "idle",  # 'idle' | 'running' | 'hitl' | 'completed' | 'error'
        "badge": "IDLE",
        "detail": "Waiting for user prompt... Live SSE node transitions will animate here.",
        "code": "-- No active SSE stream --",
    }


# -----------------------------------------------------------------------------
# Live Right-Column SVG Graph Renderer (Driven by Real-Time SSE Events)
# -----------------------------------------------------------------------------
def render_live_sse_graph(placeholder, state: dict):
    """Renders the current LangGraph node & edge state inside the right-hand column."""
    active_node = state.get("active_node") or ""
    from_node = state.get("from_node") or ""
    to_node = state.get("to_node") or ""
    visited_json = json.dumps(state.get("visited_nodes", []))
    status_mode = state.get("status_mode", "idle")
    badge = state.get("badge", "SSE")
    detail = state.get("detail", "")
    code = state.get("code", "")

    badge_colors = {
        "idle": "#475569",
        "running": "#0284c7",
        "hitl": "#dc2626",
        "completed": "#059669",
        "error": "#b91c1c",
    }
    badge_bg = badge_colors.get(status_mode, "#0284c7")

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        body {{
            margin: 0;
            padding: 0;
            background: transparent;
            color: #e2e8f0;
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
        }}
        .graph-card {{
            background: linear-gradient(145deg, #0f172a, #090d16);
            border: 1px solid #1e293b;
            border-radius: 12px;
            padding: 12px 14px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.45);
        }}
        .graph-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
            padding-bottom: 6px;
            border-bottom: 1px solid #1e293b;
        }}
        .header-title {{
            font-size: 13px;
            font-weight: 700;
            color: #38bdf8;
            letter-spacing: 0.4px;
            text-transform: uppercase;
        }}
        .live-indicator {{
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 11px;
            color: #94a3b8;
            font-family: monospace;
        }}
        .pulse-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: {badge_bg};
            box-shadow: 0 0 8px {badge_bg};
            animation: pulseDot 1.2s infinite ease-in-out;
        }}
        @keyframes pulseDot {{
            0%, 100% {{ transform: scale(1); opacity: 1; }}
            50% {{ transform: scale(1.4); opacity: 0.5; }}
        }}
        svg {{
            width: 100%;
            height: 310px;
            background: radial-gradient(circle at center, #111827 0%, #090d16 100%);
            border-radius: 8px;
            border: 1px solid #1e293b;
        }}
        .edge {{
            stroke: #334155;
            stroke-width: 2.2;
            fill: none;
            stroke-dasharray: 5 5;
            transition: stroke 0.25s ease;
        }}
        .edge.visited-edge {{
            stroke: #059669;
            stroke-width: 2.5;
            stroke-dasharray: none;
            opacity: 0.75;
        }}
        .edge.active-edge {{
            stroke: #38bdf8;
            stroke-width: 3.5;
            stroke-dasharray: 8 4;
            animation: dashFlow 0.55s linear infinite;
            filter: drop-shadow(0 0 6px #38bdf8);
        }}
        @keyframes dashFlow {{
            to {{ stroke-dashoffset: -24; }}
        }}
        .node-box {{
            fill: #1e293b;
            stroke: #475569;
            stroke-width: 2;
            rx: 8;
            ry: 8;
            transition: all 0.25s ease;
        }}
        .node-box.visited-node {{
            fill: #064e3b;
            stroke: #10b981;
            stroke-width: 2.2;
        }}
        .node-box.active-node {{
            fill: #0c4a6e;
            stroke: #38bdf8;
            stroke-width: 3;
            filter: drop-shadow(0 0 14px #0ea5e9);
            animation: nodePulse 1.1s infinite alternate;
        }}
        .node-box.hitl-node {{
            fill: #7f1d1d !important;
            stroke: #f87171 !important;
            stroke-width: 3 !important;
            filter: drop-shadow(0 0 16px #ef4444) !important;
            animation: nodePulse 0.8s infinite alternate;
        }}
        @keyframes nodePulse {{
            from {{ filter: drop-shadow(0 0 6px #38bdf8); }}
            to {{ filter: drop-shadow(0 0 16px #38bdf8); }}
        }}
        .node-title {{
            fill: #f8fafc;
            font-size: 11px;
            font-weight: 700;
            text-anchor: middle;
            pointer-events: none;
        }}
        .node-sub {{
            fill: #cbd5e1;
            font-size: 9px;
            text-anchor: middle;
            pointer-events: none;
        }}
        .telemetry-box {{
            margin-top: 10px;
            background: #060911;
            border: 1px solid #1e293b;
            border-left: 4px solid {badge_bg};
            border-radius: 6px;
            padding: 9px 12px;
        }}
        .telemetry-top {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 5px;
        }}
        .sse-badge {{
            background: {badge_bg};
            color: #ffffff;
            font-size: 10.5px;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 4px;
            letter-spacing: 0.3px;
        }}
        .sse-detail {{
            font-size: 12.5px;
            color: #f1f5f9;
            font-weight: 600;
        }}
        .sse-code {{
            background: #020617;
            color: #34d399;
            font-family: 'Consolas', monospace;
            font-size: 11px;
            padding: 7px 9px;
            border-radius: 4px;
            border: 1px solid #1e293b;
            white-space: pre-wrap;
            max-height: 78px;
            overflow-y: auto;
        }}
    </style>
    </head>
    <body>
    <div class="graph-card">
        <div class="graph-header">
            <span class="header-title">⚡ Live LangGraph SSE State Machine</span>
            <div class="live-indicator">
                <span class="pulse-dot"></span>
                <span>{status_mode.upper()}</span>
            </div>
        </div>

        <svg viewBox="0 0 580 300">
            <!-- Edges -->
            <path id="edge-ui-api" class="edge" d="M 110 50 L 185 50" />
            <path id="edge-api-assistant" class="edge" d="M 305 50 L 375 50" />
            <path id="edge-assistant-tools" class="edge" d="M 445 78 L 445 128" />
            <path id="edge-tools-chroma" class="edge" d="M 380 155 L 295 155" />
            <path id="edge-chroma-grader" class="edge" d="M 230 182 L 230 225" />
            <path id="edge-grader-rewriter" class="edge" d="M 165 252 L 125 252" />
            <path id="edge-rewriter-assistant" class="edge" d="M 65 225 L 65 95 L 375 65" />
            <path id="edge-grader-assistant" class="edge" d="M 295 252 L 345 252 L 410 78" />
            <path id="edge-tools-mysql" class="edge" d="M 445 182 L 445 225" />
            <path id="edge-tools-hitl" class="edge" d="M 510 155 L 525 155 L 525 225" />
            <path id="edge-hitl-mysql" class="edge" d="M 465 252 L 435 252" />
            <path id="edge-mysql-assistant" class="edge" d="M 375 225 L 375 78" />

            <!-- Moving SSE Data Packet -->
            <circle id="packetDot" r="6" fill="#38bdf8" visibility="hidden" filter="drop-shadow(0 0 8px #38bdf8)" />

            <!-- Row 1: Entry & Reasoning -->
            <g transform="translate(15, 24)">
                <rect id="node-ui" class="node-box" width="95" height="52" />
                <text x="47" y="22" class="node-title">🖥️ Streamlit</text>
                <text x="47" y="38" class="node-sub">Client UI</text>
            </g>

            <g transform="translate(185, 24)">
                <rect id="node-api" class="node-box" width="120" height="52" />
                <text x="60" y="22" class="node-title">⚡ FastAPI SSE</text>
                <text x="60" y="38" class="node-sub">/query/stream</text>
            </g>

            <g transform="translate(375, 24)">
                <rect id="node-assistant" class="node-box" width="140" height="52" />
                <text x="70" y="22" class="node-title">🧠 assistant_node</text>
                <text x="70" y="38" class="node-sub">Groq Qwen-3.8-27B</text>
            </g>

            <!-- Row 2: Tool Execution & ChromaDB -->
            <g transform="translate(165, 128)">
                <rect id="node-chroma" class="node-box" width="130" height="52" />
                <text x="65" y="22" class="node-title">📚 ChromaDB</text>
                <text x="65" y="38" class="node-sub">Policy Vectors</text>
            </g>

            <g transform="translate(380, 128)">
                <rect id="node-tools" class="node-box" width="130" height="52" />
                <text x="65" y="22" class="node-title">🛠️ execute_tools</text>
                <text x="65" y="38" class="node-sub">IDOR & Tool Router</text>
            </g>

            <!-- Row 3: CRAG Loop, MySQL & HITL Gate -->
            <g transform="translate(15, 225)">
                <rect id="node-rewriter" class="node-box" width="110" height="52" />
                <text x="55" y="22" class="node-title">✏️ rewrite_query</text>
                <text x="55" y="38" class="node-sub">Query Optimizer</text>
            </g>

            <g transform="translate(165, 225)">
                <rect id="node-grader" class="node-box" width="130" height="52" />
                <text x="65" y="22" class="node-title">🔍 crag_grader</text>
                <text x="65" y="38" class="node-sub">Pydantic Grader</text>
            </g>

            <g transform="translate(325, 225)">
                <rect id="node-mysql" class="node-box" width="115" height="52" />
                <text x="57" y="22" class="node-title">🗄️ MySQL 8.0</text>
                <text x="57" y="38" class="node-sub">ACID + Row Lock</text>
            </g>

            <g transform="translate(460, 225)">
                <rect id="node-hitl" class="node-box" width="105" height="52" />
                <text x="52" y="22" class="node-title">⏸️ HITL Gate</text>
                <text x="52" y="38" class="node-sub">interrupt()</text>
            </g>
        </svg>

        <div class="telemetry-box">
            <div class="telemetry-top">
                <span class="sse-badge">{badge}</span>
                <span class="sse-detail">{detail}</span>
            </div>
            <div class="sse-code">{code}</div>
        </div>
    </div>

    <script>
        const visited = {visited_json};
        const activeNode = "{active_node}";
        const fromNode = "{from_node}";
        const toNode = "{to_node}";
        const statusMode = "{status_mode}";

        const coords = {{
            ui: [62, 50],
            api: [245, 50],
            assistant: [445, 50],
            chroma: [230, 154],
            tools: [445, 154],
            rewriter: [70, 251],
            grader: [230, 251],
            mysql: [382, 251],
            hitl: [512, 251]
        }};

        visited.forEach(n => {{
            const el = document.getElementById('node-' + n);
            if (el) el.classList.add('visited-node');
        }});

        if (activeNode) {{
            const actEl = document.getElementById('node-' + activeNode);
            if (actEl) {{
                actEl.classList.remove('visited-node');
                if (statusMode === 'hitl' || activeNode === 'hitl') {{
                    actEl.classList.add('hitl-node');
                }} else {{
                    actEl.classList.add('active-node');
                }}
            }}
        }}

        if (fromNode && toNode) {{
            const edgeEl = document.getElementById('edge-' + fromNode + '-' + toNode);
            if (edgeEl) edgeEl.classList.add('active-edge');

            const dot = document.getElementById('packetDot');
            const s = coords[fromNode];
            const e = coords[toNode];
            if (s && e) {{
                dot.setAttribute('visibility', 'visible');
                const start = performance.now();
                const duration = 450;
                function step(now) {{
                    const p = Math.min((now - start) / duration, 1);
                    dot.setAttribute('cx', s[0] + (e[0] - s[0]) * p);
                    dot.setAttribute('cy', s[1] + (e[1] - s[1]) * p);
                    if (p < 1) requestAnimationFrame(step);
                }}
                requestAnimationFrame(step);
            }}
        }}
    </script>
    </body>
    </html>
    """
    with placeholder.container():
        components.html(html_code, height=465, scrolling=False)


# -----------------------------------------------------------------------------
# Backend Health & Live SSE Stream Consumer (Animates Graph on Every Event)
# -----------------------------------------------------------------------------
def check_backend_health() -> bool:
    try:
        res = requests.get(HEALTH_ENDPOINT, timeout=3)
        return res.status_code == 200
    except requests.RequestException:
        return False


def refresh_user_orders():
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


def consume_sse_stream_with_live_graph(
    url: str,
    payload: dict,
    graph_placeholder,
    is_approval_resume: bool = False,
    anim_delay: float = 0.55,
) -> dict:
    """
    Consumes Server-Sent Events from FastAPI and animates each LangGraph node transition
    live inside the right-hand column (`graph_placeholder`) instead of printing plain text.
    """
    trace_steps = []
    final_payload = {}
    visited = list(st.session_state.graph_visual_state.get("visited_nodes", []))

    if not is_approval_resume:
        visited = ["ui"]
        st.session_state.graph_visual_state = {
            "active_node": "api",
            "from_node": "ui",
            "to_node": "api",
            "visited_nodes": visited,
            "status_mode": "running",
            "badge": "SSE DISPATCH",
            "detail": "Streaming prompt from Streamlit UI to FastAPI SSE endpoint...",
            "code": f"POST /agent/query/stream | customer_id={payload.get('customer_id')}",
        }
        render_live_sse_graph(graph_placeholder, st.session_state.graph_visual_state)
        time.sleep(anim_delay)
        prev_node = "api"
    else:
        decision = payload.get("decision", "approve")
        st.session_state.graph_visual_state = {
            "active_node": "mysql" if decision == "approve" else "assistant",
            "from_node": "hitl",
            "to_node": "mysql" if decision == "approve" else "assistant",
            "visited_nodes": visited + ["hitl"],
            "status_mode": "running",
            "badge": f"HITL RESUME ({decision.upper()})",
            "detail": f"Administrator dispatched Command(resume='{decision}')...",
            "code": f"POST /agent/approve/stream | thread_id='{payload.get('thread_id')}'",
        }
        render_live_sse_graph(graph_placeholder, st.session_state.graph_visual_state)
        time.sleep(anim_delay)
        prev_node = "mysql" if decision == "approve" else "hitl"

    with requests.post(url, json=payload, stream=True, timeout=120) as response:
        response.raise_for_status()
        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line or not raw_line.startswith("data: "):
                continue
            event_data = json.loads(raw_line[6:])
            event_type = event_data.get("event")

            if event_type == "node_update":
                trace_steps.append(event_data)
                raw_node = event_data.get("node", "")
                detail = event_data.get("detail", "")
                meta = event_data.get("metadata", {})

                if prev_node not in visited:
                    visited.append(prev_node)

                if raw_node == "assistant_node":
                    tool_calls = meta.get("tool_calls")
                    code_str = (
                        json.dumps(tool_calls, indent=2)
                        if tool_calls
                        else "Synthesizing grounded response from context..."
                    )
                    st.session_state.graph_visual_state = {
                        "active_node": "assistant",
                        "from_node": prev_node,
                        "to_node": "assistant",
                        "visited_nodes": list(visited),
                        "status_mode": "running",
                        "badge": "assistant_node",
                        "detail": detail,
                        "code": code_str,
                    }
                    render_live_sse_graph(graph_placeholder, st.session_state.graph_visual_state)
                    time.sleep(anim_delay)
                    prev_node = "assistant"

                elif raw_node == "execute_tools_node":
                    tool_out = meta.get("tool_output", "")
                    # Step A: Highlight execute_tools_node
                    st.session_state.graph_visual_state = {
                        "active_node": "tools",
                        "from_node": prev_node,
                        "to_node": "tools",
                        "visited_nodes": list(visited),
                        "status_mode": "running",
                        "badge": "execute_tools_node",
                        "detail": detail,
                        "code": tool_out or "Executing bound tool...",
                    }
                    render_live_sse_graph(graph_placeholder, st.session_state.graph_visual_state)
                    time.sleep(anim_delay)
                    visited.append("tools")

                    # Step B: Animate hop to ChromaDB or MySQL 8.0 based on executed tool
                    is_rag = "search_company_policies" in detail or "policy" in tool_out.lower()
                    target_db = "chroma" if is_rag else "mysql"
                    db_badge = "ChromaDB Vector Search" if is_rag else "MySQL 8.0 Pool"
                    db_detail = (
                        "Retrieved top-3 policy chunks from Company_policy.pdf"
                        if is_rag
                        else "Executed SQL query with customer_id isolation"
                    )
                    st.session_state.graph_visual_state = {
                        "active_node": target_db,
                        "from_node": "tools",
                        "to_node": target_db,
                        "visited_nodes": list(visited),
                        "status_mode": "running",
                        "badge": db_badge,
                        "detail": db_detail,
                        "code": tool_out,
                    }
                    render_live_sse_graph(graph_placeholder, st.session_state.graph_visual_state)
                    time.sleep(anim_delay)
                    prev_node = target_db

                elif raw_node == "crag_grader_node":
                    score = str(meta.get("relevance_score", "yes")).upper()
                    st.session_state.graph_visual_state = {
                        "active_node": "grader",
                        "from_node": prev_node,
                        "to_node": "grader",
                        "visited_nodes": list(visited),
                        "status_mode": "running",
                        "badge": f"crag_grader_node ({score})",
                        "detail": detail,
                        "code": f"Pydantic GradeDocuments(binary_score='{score.lower()}')",
                    }
                    render_live_sse_graph(graph_placeholder, st.session_state.graph_visual_state)
                    time.sleep(anim_delay)
                    prev_node = "grader"

                elif raw_node == "rewrite_query_node":
                    st.session_state.graph_visual_state = {
                        "active_node": "rewriter",
                        "from_node": prev_node,
                        "to_node": "rewriter",
                        "visited_nodes": list(visited),
                        "status_mode": "running",
                        "badge": "rewrite_query_node",
                        "detail": detail,
                        "code": "Optimizing search query for retry against ChromaDB...",
                    }
                    render_live_sse_graph(graph_placeholder, st.session_state.graph_visual_state)
                    time.sleep(anim_delay)
                    prev_node = "rewriter"

            elif event_type == "error":
                st.session_state.graph_visual_state["status_mode"] = "error"
                st.session_state.graph_visual_state["badge"] = "STREAM ERROR"
                st.session_state.graph_visual_state["detail"] = event_data.get("detail", "Error")
                render_live_sse_graph(graph_placeholder, st.session_state.graph_visual_state)
                raise RuntimeError(event_data.get("detail", "Unknown streaming error"))

            elif event_type == "final":
                final_payload = event_data
                final_payload["trace_steps"] = trace_steps
                status = str(event_data.get("status", "completed")).lower()

                if prev_node not in visited:
                    visited.append(prev_node)

                if status in ["waiting_for_approval", "interrupted", "pending_approval"]:
                    # Animate transition from assistant/tools into HITL Interrupt Gate
                    if "tools" not in visited:
                        visited.append("tools")
                    sql_prev = event_data.get("pending_sql") or json.dumps(
                        event_data.get("pending_action", {}), indent=2
                    )
                    st.session_state.graph_visual_state = {
                        "active_node": "hitl",
                        "from_node": "tools",
                        "to_node": "hitl",
                        "visited_nodes": list(visited),
                        "status_mode": "hitl",
                        "badge": "⏸️ HITL INTERRUPT",
                        "detail": "Execution frozen at interrupt() prior to MySQL write! Waiting for Admin decision.",
                        "code": str(sql_prev),
                    }
                else:
                    if "assistant" not in visited:
                        visited.append("assistant")
                    st.session_state.graph_visual_state = {
                        "active_node": "assistant",
                        "from_node": prev_node,
                        "to_node": "assistant",
                        "visited_nodes": list(visited),
                        "status_mode": "completed",
                        "badge": "✅ WORKFLOW COMPLETED",
                        "detail": "LangGraph execution finished and streamed final response to UI.",
                        "code": str(event_data.get("response", ""))[:260],
                    }
                render_live_sse_graph(graph_placeholder, st.session_state.graph_visual_state)

    return final_payload


# -----------------------------------------------------------------------------
# GATE 1: Security Login Screen
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
            email_input = st.text_input("Email Address", value="alice@example.com")
            password_input = st.text_input("Password", value="alice123", type="password")
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
# GATE 2: Authenticated Console (Left: Chat | Right: Live Animated SSE Graph)
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
    for order in current_user.get("orders", []):
        st.markdown(
            f"**Order #{order['id']}** — `{order['status'].upper()}`\n"
            f"*{order.get('item_name', 'Order')}* • **${order['total_amount']:.2f}**"
        )

    st.divider()
    anim_speed = st.slider(
        "SSE Node Animation Delay (sec)",
        min_value=0.2,
        max_value=1.5,
        value=0.55,
        step=0.05,
        help="Controls how long each node transition stays highlighted as SSE events stream in.",
    )

    if st.button("➕ Reset Conversation", use_container_width=True):
        st.session_state.thread_id = (
            f"cust-{current_user['customer_id']}-{uuid.uuid4().hex[:6]}"
        )
        st.session_state.messages = []
        st.session_state.interrupted_state = None
        st.session_state.graph_visual_state = {
            "active_node": None,
            "from_node": None,
            "to_node": None,
            "visited_nodes": [],
            "status_mode": "idle",
            "badge": "IDLE",
            "detail": "Waiting for user prompt... Live SSE node transitions will animate here.",
            "code": "-- No active SSE stream --",
        }
        st.rerun()

st.subheader(f"Autonomous Enterprise Operations Console — Welcome, {current_user['name']}")
chat_col, inspector_col = st.columns([1.25, 1.15], gap="large")

# -----------------------------------------------------------------------------
# Right Column: Live Animated SSE Graph & HITL Governance Gate
# -----------------------------------------------------------------------------
with inspector_col:
    graph_placeholder = st.empty()
    render_live_sse_graph(graph_placeholder, st.session_state.graph_visual_state)

    if st.session_state.interrupted_state:
        pending_data = st.session_state.interrupted_state
        pending_action = pending_data.get("pending_action", {})
        pending_sql = pending_data.get("pending_sql") or json.dumps(
            pending_action, indent=2
        )

        st.error("⚠️ **HITL Gate Active: Administrator Decision Required**")
        if isinstance(pending_action, dict) and pending_action.get("args"):
            with st.expander("Inspect Auto-Resolved Tool Arguments & SQL Preview", expanded=True):
                st.json(pending_action["args"])
                st.code(str(pending_sql), language="sql")

        btn_col1, btn_col2 = st.columns(2)

        with btn_col1:
            if st.button("✅ Approve & Execute", type="primary", use_container_width=True):
                try:
                    res = consume_sse_stream_with_live_graph(
                        APPROVE_STREAM_ENDPOINT,
                        {"thread_id": st.session_state.thread_id, "decision": "approve"},
                        graph_placeholder,
                        is_approval_resume=True,
                        anim_delay=anim_speed,
                    )
                    final_msg = (
                        res.get("response")
                        or res.get("result")
                        or "Operation approved and executed."
                    )
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
                try:
                    res = consume_sse_stream_with_live_graph(
                        APPROVE_STREAM_ENDPOINT,
                        {"thread_id": st.session_state.thread_id, "decision": "reject"},
                        graph_placeholder,
                        is_approval_resume=True,
                        anim_delay=anim_speed,
                    )
                    final_msg = (
                        res.get("response")
                        or res.get("result")
                        or "Operation rejected by administrator."
                    )
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

# -----------------------------------------------------------------------------
# Left Column: Clean Chat Feed (No Cluttered Text Logs)
# -----------------------------------------------------------------------------
with chat_col:
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("metadata"):
                with st.expander("View Raw SSE Telemetry JSON"):
                    st.json(msg["metadata"])

    input_disabled = st.session_state.interrupted_state is not None
    user_prompt = st.chat_input(
        "Ask a policy question, check your orders, or request a refund...",
        disabled=input_disabled,
    )

    if user_prompt:
        st.session_state.messages.append({"role": "user", "content": user_prompt})
        with st.chat_message("user"):
            st.markdown(user_prompt)

        with st.chat_message("assistant"):
            with st.spinner("Executing LangGraph workflow (watch live graph on the right →)..."):
                try:
                    data = consume_sse_stream_with_live_graph(
                        QUERY_STREAM_ENDPOINT,
                        {
                            "query": user_prompt,
                            "thread_id": st.session_state.thread_id,
                            "customer_id": current_user["customer_id"],
                        },
                        graph_placeholder,
                        is_approval_resume=False,
                        anim_delay=anim_speed,
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
                        st.markdown(answer)
                        st.session_state.messages.append(
                            {"role": "assistant", "content": answer, "metadata": data}
                        )
                        st.rerun()

                except Exception as exc:
                    st.error(f"FastAPI Stream Error: {exc}")