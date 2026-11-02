import json
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
    page_title="Enterprise Ops Engine | Secure Console & Live Animator",
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

if "animation_steps" not in st.session_state:
    st.session_state.animation_steps = []

if "animation_title" not in st.session_state:
    st.session_state.animation_title = "Idle — Submit a Prompt or Select a Major Scenario Below"


# -----------------------------------------------------------------------------
# Pre-Built Major Interview Scenarios for 1-Click Animated Video Playback
# -----------------------------------------------------------------------------
MAJOR_SCENARIO_ANIMATIONS = {
    "rag_crag": {
        "title": "Scenario 1: Self-Healing Corrective RAG (Policy Lookup & Query Rewrite)",
        "steps": [
            {
                "from": "ui",
                "to": "api",
                "active": "api",
                "badge": "HTTP POST (SSE)",
                "detail": "User asks: 'What is the restocking fee if I refuse delivery?' -> Dispatched to /agent/query/stream",
                "code": "POST /agent/query/stream { 'customer_id': 1, 'query': 'What is the restocking fee...' }",
            },
            {
                "from": "api",
                "to": "assistant",
                "active": "assistant",
                "badge": "LangGraph START",
                "detail": "assistant_node (Groq Qwen-3.8-27B) analyzes intent and binds tool: search_company_policies",
                "code": "AIMessage(tool_calls=[{'name': 'search_company_policies', 'args': {'query': 'refused delivery fee'}}])",
            },
            {
                "from": "assistant",
                "to": "tools",
                "active": "tools",
                "badge": "Tool Dispatch",
                "detail": "execute_tools_node invokes ChromaDB vector similarity search (all-MiniLM-L6-v2)",
                "code": "vectorstore.as_retriever(search_kwargs={'k': 3}).invoke('refused delivery fee')",
            },
            {
                "from": "tools",
                "to": "chroma",
                "active": "chroma",
                "badge": "Vector Search",
                "detail": "ChromaDB retrieves top-3 chunks from Company_policy.pdf (Section 1: Order Cancellations)",
                "code": "Document 1: 'Refused Deliveries: refund will be subject to a 15% restocking fee...'",
            },
            {
                "from": "chroma",
                "to": "grader",
                "active": "grader",
                "badge": "CRAG Grader",
                "detail": "crag_grader_node evaluates retrieved chunks with structured Pydantic model GradeDocuments",
                "code": "GradeDocuments(binary_score='yes') -> Relevance verified! Skipping query rewrite.",
            },
            {
                "from": "grader",
                "to": "assistant",
                "active": "assistant",
                "badge": "Grounded Synthesis",
                "detail": "assistant_node synthesizes final grounded answer citing the 15% restocking fee",
                "code": "Final Response: 'According to Section 1 of company policy, refused deliveries incur a 15% restocking fee.'",
            },
        ],
    },
    "refund_hitl": {
        "title": "Scenario 2: Auto-Resolved Refund + HITL Governance Gate + ACID MySQL Transaction",
        "steps": [
            {
                "from": "ui",
                "to": "api",
                "active": "api",
                "badge": "Authenticated Request",
                "detail": "Alice (customer_id=1) asks: 'Refund my delivered order because it arrived damaged' (No Order ID/Amount given)",
                "code": "POST /agent/query/stream { 'customer_id': 1, 'query': 'Refund my delivered order...' }",
            },
            {
                "from": "api",
                "to": "assistant",
                "active": "assistant",
                "badge": "Reasoning Node",
                "detail": "assistant_node triggers execute_refund(order_id=None, amount=None, reason='Arrived damaged')",
                "code": "AIMessage(tool_calls=[{'name': 'execute_refund', 'args': {'reason': 'Item arrived damaged'}}])",
            },
            {
                "from": "assistant",
                "to": "tools",
                "active": "tools",
                "badge": "Auto-Resolution",
                "detail": "execute_tools_node binds customer_id=1 and resolves Alice's delivered Order #999 ($50.00) from MySQL",
                "code": "SELECT id, total_amount FROM orders WHERE customer_id = 1 AND status = 'delivered' LIMIT 1 -> Order #999 ($50.00)",
            },
            {
                "from": "tools",
                "to": "hitl",
                "active": "hitl",
                "badge": "⏸️ HITL INTERRUPT",
                "detail": "Execution deterministically freezes at interrupt()! Checkpoint saved to SqliteSaver awaiting Admin decision.",
                "code": "interrupt({'action': 'require_approval', 'tool': 'execute_refund', 'order_id': 999, 'amount': 50.00})",
            },
            {
                "from": "hitl",
                "to": "mysql",
                "active": "mysql",
                "badge": "✅ Admin Approved -> ACID Write",
                "detail": "Admin clicks Approve! MySQL locks row (FOR UPDATE), checks idempotency & bounds, and commits refund.",
                "code": "SELECT * FROM orders WHERE id=999 FOR UPDATE;\nINSERT INTO refunds (order_id, refund_amount, reason) VALUES (999, 50.00, 'Item arrived damaged');\nUPDATE orders SET status='refunded' WHERE id=999;\nCOMMIT;",
            },
            {
                "from": "mysql",
                "to": "assistant",
                "active": "assistant",
                "badge": "Transaction Complete",
                "detail": "MySQL confirms ACID commit -> assistant_node streams final confirmation back to Streamlit UI",
                "code": "ToolMessage: 'Successfully processed a $50.00 refund for Order #999 and updated status to refunded.'",
            },
        ],
    },
    "sql_guardrail": {
        "title": "Scenario 3: Critical Guardrail — $5,000 Excessive Refund Demand Blocked by MySQL",
        "steps": [
            {
                "from": "ui",
                "to": "api",
                "active": "api",
                "badge": "High-Risk Prompt",
                "detail": "User demands: 'My order 999 arrived broken, give me a $5,000 refund immediately!'",
                "code": "POST /agent/query/stream { 'customer_id': 1, 'query': 'Give me a $5,000 refund for order 999!' }",
            },
            {
                "from": "api",
                "to": "assistant",
                "active": "assistant",
                "badge": "Tool Binding",
                "detail": "assistant_node prepares execute_refund(order_id=999, amount=5000.0, reason='Broken item')",
                "code": "execute_refund(order_id=999, amount=5000.00, customer_id=1)",
            },
            {
                "from": "assistant",
                "to": "hitl",
                "active": "hitl",
                "badge": "⏸️ HITL Gate",
                "detail": "Graph pauses at interrupt() for human inspection. Even if Admin approves to test DB safety...",
                "code": "Command(resume='approve') -> Proceeding to MySQL transactional guardrail check",
            },
            {
                "from": "hitl",
                "to": "mysql",
                "active": "mysql",
                "badge": "🛑 BOUNDS GUARDRAIL",
                "detail": "MySQL locks Order #999 (total_amount=$50.00). Detects $5,000 > $50.00 -> ROLLBACK executed!",
                "code": "SELECT id, total_amount, status FROM orders WHERE id = 999 FOR UPDATE;\n-- Guardrail: requested ($5000.00) > max_refundable ($50.00)\nROLLBACK;",
            },
            {
                "from": "mysql",
                "to": "assistant",
                "active": "assistant",
                "badge": "Safe Rejection",
                "detail": "assistant_node reports the exact validation error without mutating any database records",
                "code": "Validation Error: Requested refund ($5000.00) exceeds original total amount ($50.00) for Order #999.",
            },
        ],
    },
}


def build_animation_steps_from_sse(user_prompt: str, trace_steps: list, final_payload: dict) -> list:
    """Converts real-time FastAPI SSE node updates into animated graph transitions."""
    steps = [
        {
            "from": "ui",
            "to": "api",
            "active": "api",
            "badge": "SSE Request",
            "detail": f"Streamlit dispatched user prompt to FastAPI SSE stream: '{user_prompt[:80]}'",
            "code": f"POST /agent/query/stream -> thread_id='{st.session_state.thread_id}'",
        }
    ]
    prev_node = "api"

    for ev in trace_steps:
        raw_node = ev.get("node", "")
        detail = ev.get("detail", "")
        meta = ev.get("metadata", {})

        if raw_node == "assistant_node":
            steps.append(
                {
                    "from": prev_node,
                    "to": "assistant",
                    "active": "assistant",
                    "badge": "assistant_node",
                    "detail": detail,
                    "code": json.dumps(meta.get("tool_calls", "Synthesizing response"), indent=2),
                }
            )
            prev_node = "assistant"

        elif raw_node == "execute_tools_node":
            tool_out = meta.get("tool_output", "")
            steps.append(
                {
                    "from": prev_node,
                    "to": "tools",
                    "active": "tools",
                    "badge": "execute_tools_node",
                    "detail": detail,
                    "code": tool_out or "Executing bound tool...",
                }
            )
            if "policy" in detail.lower() or "document" in tool_out.lower():
                steps.append(
                    {
                        "from": "tools",
                        "to": "chroma",
                        "active": "chroma",
                        "badge": "ChromaDB RAG",
                        "detail": "Fetched top-k policy chunks from ChromaDB (all-MiniLM-L6-v2)",
                        "code": tool_out[:260],
                    }
                )
                prev_node = "chroma"
            else:
                steps.append(
                    {
                        "from": "tools",
                        "to": "mysql",
                        "active": "mysql",
                        "badge": "MySQL 8.0",
                        "detail": "Executed transactional SQL query against MySQL 8.0 connection pool",
                        "code": tool_out[:260],
                    }
                )
                prev_node = "mysql"

        elif raw_node == "crag_grader_node":
            score = meta.get("relevance_score", "yes")
            steps.append(
                {
                    "from": prev_node,
                    "to": "grader",
                    "active": "grader",
                    "badge": f"CRAG Grader ({score.upper()})",
                    "detail": detail,
                    "code": f"GradeDocuments(binary_score='{score}')",
                }
            )
            prev_node = "grader"

        elif raw_node == "rewrite_query_node":
            steps.append(
                {
                    "from": prev_node,
                    "to": "rewriter",
                    "active": "rewriter",
                    "badge": "Query Rewriter",
                    "detail": detail,
                    "code": "Rewriting query for secondary ChromaDB retrieval...",
                }
            )
            prev_node = "rewriter"

    if final_payload.get("status") == "waiting_for_approval":
        sql_prev = final_payload.get("pending_sql") or "INSERT INTO refunds ...; UPDATE orders ...;"
        steps.append(
            {
                "from": prev_node,
                "to": "hitl",
                "active": "hitl",
                "badge": "⏸️ HITL Interrupt",
                "detail": "Execution frozen at interrupt() prior to MySQL write. Waiting for Admin approval.",
                "code": sql_prev,
            }
        )

    return steps


def render_animated_architecture_player(steps: list, title: str):
    """Renders an interactive HTML5/SVG animated node-by-node video player inside Streamlit."""
    steps_json = json.dumps(steps)
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        body {{
            margin: 0;
            padding: 0;
            background: #0b0f19;
            color: #e2e8f0;
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
        }}
        .player-card {{
            background: linear-gradient(145deg, #0f172a, #0b0f19);
            border: 1px solid #1e293b;
            border-radius: 12px;
            padding: 14px 18px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.5);
        }}
        .header-bar {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
            border-bottom: 1px solid #1e293b;
            padding-bottom: 8px;
        }}
        .title-text {{
            font-size: 14px;
            font-weight: 700;
            color: #38bdf8;
            letter-spacing: 0.3px;
        }}
        .controls {{
            display: flex;
            gap: 8px;
            align-items: center;
        }}
        .btn {{
            background: #1e293b;
            color: #f8fafc;
            border: 1px solid #334155;
            border-radius: 6px;
            padding: 5px 11px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .btn:hover {{
            background: #334155;
            border-color: #38bdf8;
        }}
        .btn-primary {{
            background: #0284c7;
            border-color: #38bdf8;
        }}
        .step-counter {{
            font-size: 12px;
            color: #94a3b8;
            font-family: monospace;
            margin-left: 6px;
        }}
        svg {{
            width: 100%;
            height: 290px;
            background: radial-gradient(circle at center, #111827 0%, #0b0f19 100%);
            border-radius: 8px;
            border: 1px solid #1e293b;
        }}
        .edge {{
            stroke: #334155;
            stroke-width: 2.2;
            fill: none;
            stroke-dasharray: 5 5;
        }}
        .edge.active-edge {{
            stroke: #38bdf8;
            stroke-width: 3.5;
            stroke-dasharray: 8 4;
            animation: dashFlow 0.6s linear infinite;
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
            transition: all 0.3s ease;
        }}
        .node-box.active-node {{
            fill: #0c4a6e;
            stroke: #38bdf8;
            stroke-width: 3;
            filter: drop-shadow(0 0 12px #0ea5e9);
        }}
        .node-box.visited-node {{
            stroke: #10b981;
            stroke-width: 2.2;
        }}
        .node-box.hitl-active {{
            fill: #7f1d1d !important;
            stroke: #f87171 !important;
            filter: drop-shadow(0 0 14px #ef4444) !important;
        }}
        .node-title {{
            fill: #f8fafc;
            font-size: 11px;
            font-weight: 700;
            text-anchor: middle;
            pointer-events: none;
        }}
        .node-sub {{
            fill: #94a3b8;
            font-size: 9.5px;
            text-anchor: middle;
            pointer-events: none;
        }}
        .telemetry-panel {{
            margin-top: 10px;
            background: #090d16;
            border: 1px solid #1e293b;
            border-left: 4px solid #38bdf8;
            border-radius: 6px;
            padding: 10px 14px;
        }}
        .telemetry-header {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 4px;
        }}
        .badge {{
            background: #0284c7;
            color: #fff;
            font-size: 11px;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 4px;
        }}
        .telemetry-detail {{
            font-size: 13px;
            color: #e2e8f0;
            font-weight: 500;
        }}
        .telemetry-code {{
            margin-top: 6px;
            background: #020617;
            color: #34d399;
            font-family: 'Consolas', monospace;
            font-size: 11.5px;
            padding: 8px 10px;
            border-radius: 4px;
            border: 1px solid #1e293b;
            white-space: pre-wrap;
            max-height: 75px;
            overflow-y: auto;
        }}
    </style>
    </head>
    <body>
    <div class="player-card">
        <div class="header-bar">
            <div class="title-text">🎬 {title}</div>
            <div class="controls">
                <button class="btn btn-primary" onclick="restartAnim()">▶️ Replay Animation</button>
                <button class="btn" onclick="prevStep()">⏮️ Prev</button>
                <button class="btn" onclick="togglePause()" id="pauseBtn">⏸️ Pause</button>
                <button class="btn" onclick="nextStep()">⏭️ Next</button>
                <span class="step-counter" id="stepCounter">Step 0 / 0</span>
            </div>
        </div>

        <svg viewBox="0 0 920 285">
            <!-- Directed Edges -->
            <path id="edge-ui-api" class="edge" d="M 125 140 L 210 140" />
            <path id="edge-api-assistant" class="edge" d="M 340 140 L 420 140" />
            <path id="edge-assistant-tools" class="edge" d="M 555 140 L 635 140" />
            <path id="edge-tools-chroma" class="edge" d="M 700 112 L 700 52 L 765 52" />
            <path id="edge-chroma-grader" class="edge" d="M 835 80 L 835 115" />
            <path id="edge-grader-rewriter" class="edge" d="M 835 168 L 835 205" />
            <path id="edge-rewriter-assistant" class="edge" d="M 765 232 L 485 232 L 485 168" />
            <path id="edge-grader-assistant" class="edge" d="M 765 140 L 485 80 L 485 112" />
            <path id="edge-tools-hitl" class="edge" d="M 700 168 L 700 232 L 605 232" />
            <path id="edge-assistant-hitl" class="edge" d="M 485 168 L 540 205" />
            <path id="edge-hitl-mysql" class="edge" d="M 475 232 L 365 232" />
            <path id="edge-tools-mysql" class="edge" d="M 635 155 L 365 215" />
            <path id="edge-mysql-assistant" class="edge" d="M 300 205 L 440 168" />

            <!-- Moving Data Packet Dot -->
            <circle id="packetDot" r="6" fill="#38bdf8" visibility="hidden" filter="drop-shadow(0 0 8px #38bdf8)" />

            <!-- 1. Streamlit UI -->
            <g transform="translate(15, 112)">
                <rect id="node-ui" class="node-box" width="110" height="56" />
                <text x="55" y="24" class="node-title">🖥️ Streamlit UI</text>
                <text x="55" y="41" class="node-sub">Auth Session</text>
            </g>

            <!-- 2. FastAPI SSE -->
            <g transform="translate(210, 112)">
                <rect id="node-api" class="node-box" width="130" height="56" />
                <text x="65" y="24" class="node-title">⚡ FastAPI Router</text>
                <text x="65" y="41" class="node-sub">SSE Event Stream</text>
            </g>

            <!-- 3. assistant_node -->
            <g transform="translate(420, 112)">
                <rect id="node-assistant" class="node-box" width="135" height="56" />
                <text x="67" y="24" class="node-title">🧠 assistant_node</text>
                <text x="67" y="41" class="node-sub">Groq Qwen-3.8-27B</text>
            </g>

            <!-- 4. execute_tools_node -->
            <g transform="translate(635, 112)">
                <rect id="node-tools" class="node-box" width="115" height="56" />
                <text x="57" y="24" class="node-title">🛠️ execute_tools</text>
                <text x="57" y="41" class="node-sub">IDOR & Tool Guard</text>
            </g>

            <!-- 5. ChromaDB Vector Store -->
            <g transform="translate(765, 22)">
                <rect id="node-chroma" class="node-box" width="140" height="56" />
                <text x="70" y="24" class="node-title">📚 ChromaDB RAG</text>
                <text x="70" y="41" class="node-sub">Company_policy.pdf</text>
            </g>

            <!-- 6. crag_grader_node -->
            <g transform="translate(765, 112)">
                <rect id="node-grader" class="node-box" width="140" height="56" />
                <text x="70" y="24" class="node-title">🔍 crag_grader</text>
                <text x="70" y="41" class="node-sub">Pydantic Grader</text>
            </g>

            <!-- 7. rewrite_query_node -->
            <g transform="translate(765, 204)">
                <rect id="node-rewriter" class="node-box" width="140" height="56" />
                <text x="70" y="24" class="node-title">✏️ rewrite_query</text>
                <text x="70" y="41" class="node-sub">Max 2 Retries</text>
            </g>

            <!-- 8. HITL Gate -->
            <g transform="translate(475, 204)">
                <rect id="node-hitl" class="node-box" width="130" height="56" />
                <text x="65" y="24" class="node-title">⏸️ HITL Gate</text>
                <text x="65" y="41" class="node-sub">interrupt() Freeze</text>
            </g>

            <!-- 9. MySQL 8.0 Database -->
            <g transform="translate(225, 204)">
                <rect id="node-mysql" class="node-box" width="140" height="56" />
                <text x="70" y="24" class="node-title">🗄️ MySQL 8.0 DB</text>
                <text x="70" y="41" class="node-sub">FOR UPDATE + ACID</text>
            </g>
        </svg>

        <div class="telemetry-panel">
            <div class="telemetry-header">
                <span class="badge" id="stepBadge">READY</span>
                <span class="telemetry-detail" id="stepDetail">Click a scenario button or send a chat message to watch the live backend execution graph.</span>
            </div>
            <div class="telemetry-code" id="stepCode">-- SQL & LangGraph state telemetry will stream here step-by-step --</div>
        </div>
    </div>

    <script>
        const steps = {steps_json};
        let currentIdx = 0;
        let isPaused = false;
        let timer = null;

        const nodeCoords = {{
            ui: [70, 140],
            api: [275, 140],
            assistant: [487, 140],
            tools: [692, 140],
            chroma: [835, 50],
            grader: [835, 140],
            rewriter: [835, 232],
            hitl: [540, 232],
            mysql: [295, 232]
        }};

        function clearHighlights() {{
            document.querySelectorAll('.node-box').forEach(el => {{
                el.classList.remove('active-node', 'hitl-active');
            }});
            document.querySelectorAll('.edge').forEach(el => {{
                el.classList.remove('active-edge');
            }});
        }}

        function animatePacket(fromNode, toNode) {{
            const dot = document.getElementById('packetDot');
            const start = nodeCoords[fromNode];
            const end = nodeCoords[toNode];
            if (!start || !end) {{
                dot.setAttribute('visibility', 'hidden');
                return;
            }}
            dot.setAttribute('visibility', 'visible');
            let progress = 0;
            const duration = 550;
            const startTime = performance.now();

            function frame(now) {{
                progress = Math.min((now - startTime) / duration, 1);
                const cx = start[0] + (end[0] - start[0]) * progress;
                const cy = start[1] + (end[1] - start[1]) * progress;
                dot.setAttribute('cx', cx);
                dot.setAttribute('cy', cy);
                if (progress < 1) requestAnimationFrame(frame);
            }}
            requestAnimationFrame(frame);
        }}

        function renderStep(idx) {{
            if (!steps || steps.length === 0) return;
            clearHighlights();

            for (let i = 0; i < idx; i++) {{
                const prevEl = document.getElementById('node-' + steps[i].active);
                if (prevEl) prevEl.classList.add('visited-node');
            }}

            const step = steps[idx];
            const activeEl = document.getElementById('node-' + step.active);
            if (activeEl) {{
                activeEl.classList.add('active-node');
                if (step.active === 'hitl') activeEl.classList.add('hitl-active');
            }}

            const edgeId = 'edge-' + step.from + '-' + step.to;
            const edgeEl = document.getElementById(edgeId);
            if (edgeEl) edgeEl.classList.add('active-edge');

            animatePacket(step.from, step.to);

            document.getElementById('stepBadge').textContent = step.badge || 'STEP ' + (idx + 1);
            document.getElementById('stepDetail').textContent = step.detail || '';
            document.getElementById('stepCode').textContent = step.code || '';
            document.getElementById('stepCounter').textContent = 'Step ' + (idx + 1) + ' / ' + steps.length;
        }}

        function scheduleNext() {{
            clearTimeout(timer);
            if (isPaused || !steps || steps.length === 0) return;
            timer = setTimeout(() => {{
                if (currentIdx < steps.length - 1) {{
                    currentIdx++;
                    renderStep(currentIdx);
                    scheduleNext();
                }}
            }}, 2200);
        }}

        function restartAnim() {{
            if (!steps || steps.length === 0) return;
            document.querySelectorAll('.node-box').forEach(el => el.classList.remove('visited-node'));
            currentIdx = 0;
            isPaused = false;
            document.getElementById('pauseBtn').textContent = '⏸️ Pause';
            renderStep(0);
            scheduleNext();
        }}

        function togglePause() {{
            isPaused = !isPaused;
            document.getElementById('pauseBtn').textContent = isPaused ? '▶️ Resume' : '⏸️ Pause';
            if (!isPaused) scheduleNext();
            else clearTimeout(timer);
        }}

        function nextStep() {{
            if (!steps || steps.length === 0) return;
            isPaused = true;
            document.getElementById('pauseBtn').textContent = '▶️ Resume';
            clearTimeout(timer);
            if (currentIdx < steps.length - 1) currentIdx++;
            renderStep(currentIdx);
        }}

        function prevStep() {{
            if (!steps || steps.length === 0) return;
            isPaused = true;
            document.getElementById('pauseBtn').textContent = '▶️ Resume';
            clearTimeout(timer);
            if (currentIdx > 0) currentIdx--;
            renderStep(currentIdx);
        }}

        if (steps && steps.length > 0) {{
            restartAnim();
        }}
    </script>
    </body>
    </html>
    """
    components.html(html_code, height=455, scrolling=False)


# -----------------------------------------------------------------------------
# Helper Functions for Backend & SSE Streaming
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


def consume_sse_stream(url: str, payload: dict, status_box) -> dict:
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
                        st.session_state.animation_steps = MAJOR_SCENARIO_ANIMATIONS["rag_crag"]["steps"]
                        st.session_state.animation_title = MAJOR_SCENARIO_ANIMATIONS["rag_crag"]["title"]
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
# GATE 2: Authenticated Operations Console + Animated Graph Studio
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
    if st.button("➕ Reset Conversation", use_container_width=True):
        st.session_state.thread_id = (
            f"cust-{current_user['customer_id']}-{uuid.uuid4().hex[:6]}"
        )
        st.session_state.messages = []
        st.session_state.interrupted_state = None
        st.rerun()

# -----------------------------------------------------------------------------
# TOP PANEL: Interactive Animated Graph Tree & Scenario Video Player
# -----------------------------------------------------------------------------
st.subheader("🎬 Live LangGraph Node-by-Node Execution Animator")
sc_col1, sc_col2, sc_col3 = st.columns(3)

with sc_col1:
    if st.button("▶️ Play Scenario 1: CRAG Policy Retrieval", use_container_width=True):
        st.session_state.animation_steps = MAJOR_SCENARIO_ANIMATIONS["rag_crag"]["steps"]
        st.session_state.animation_title = MAJOR_SCENARIO_ANIMATIONS["rag_crag"]["title"]

with sc_col2:
    if st.button("▶️ Play Scenario 2: Auto-Refund + HITL + SQL", use_container_width=True):
        st.session_state.animation_steps = MAJOR_SCENARIO_ANIMATIONS["refund_hitl"]["steps"]
        st.session_state.animation_title = MAJOR_SCENARIO_ANIMATIONS["refund_hitl"]["title"]

with sc_col3:
    if st.button("▶️ Play Scenario 3: $5,000 Refund Guardrail Block", use_container_width=True):
        st.session_state.animation_steps = MAJOR_SCENARIO_ANIMATIONS["sql_guardrail"]["steps"]
        st.session_state.animation_title = MAJOR_SCENARIO_ANIMATIONS["sql_guardrail"]["title"]

render_animated_architecture_player(
    st.session_state.animation_steps,
    st.session_state.animation_title,
)

st.divider()

# -----------------------------------------------------------------------------
# BOTTOM PANEL: Live Chat Feed & HITL Governance Inspector
# -----------------------------------------------------------------------------
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
        "Ask a policy question or request a refund (the graph above will animate your exact path!)...",
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
                    # Build live animation from actual SSE trace steps!
                    st.session_state.animation_steps = build_animation_steps_from_sse(
                        user_prompt, data.get("trace_steps", []), data
                    )
                    st.session_state.animation_title = f"Live Execution Trace: '{user_prompt[:55]}'"

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
                        st.rerun()

                except Exception as exc:
                    status_box.update(label="❌ Execution Failed", state="error")
                    st.error(f"FastAPI Stream Error: {exc}")

with inspector_col:
    st.markdown("### 🛡️ Governance & HITL Gate")

    if st.session_state.interrupted_state:
        pending_data = st.session_state.interrupted_state
        pending_action = pending_data.get("pending_action", {})
        pending_sql = pending_data.get("pending_sql") or json.dumps(
            pending_action, indent=2
        )

        st.error("⚠️ **High-Stakes Database Mutation Intercepted**")
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
                        st.session_state.animation_steps.append(
                            {
                                "from": "hitl",
                                "to": "mysql",
                                "active": "mysql",
                                "badge": "✅ Approved -> MySQL Commit",
                                "detail": "Admin approved! Executed FOR UPDATE lock and committed refund in MySQL 8.0.",
                                "code": str(pending_sql),
                            }
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