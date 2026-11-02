import json
import os
import time
import uuid
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

DEFAULT_ANIM_DELAY = 0.55

st.set_page_config(
    page_title="Enterprise Ops Engine | Live SSE Graph Console",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------------------------------------------------------
# Modern SaaS Theme & Sticky Layout CSS
# -----------------------------------------------------------------------------
st.markdown(
    """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

        html, body, [class*="css"] {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
        }
        code, pre {
            font-family: 'JetBrains Mono', monospace !important;
        }

        /* Compact viewport padding for 1080p screens */
        .block-container {
            padding-top: 1.5rem !important;
            padding-bottom: 1rem !important;
            max-width: 96% !important;
        }

        /* Sticky Right Column for Live Graph + HITL Gate */
        div[data-testid="stHorizontalBlock"] {
            align-items: flex-start !important;
        }
        div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:nth-of-type(2),
        div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:nth-of-type(2) {
            position: sticky !important;
            top: 2.5rem !important;
            z-index: 10 !important;
            align-self: flex-start !important;
        }

        /* Sidebar Styling */
        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #0b0f19 0%, #060911 100%) !important;
            border-right: 1px solid rgba(148, 163, 184, 0.12) !important;
        }

        /* Custom Scrollable Chat Container Border & Glass Effect */
        div[data-testid="stVerticalBlockBorderWrapper"] {
            background: rgba(15, 23, 42, 0.45) !important;
            border: 1px solid rgba(148, 163, 184, 0.14) !important;
            border-radius: 14px !important;
            backdrop-filter: blur(12px);
            box-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.5);
        }

        /* Chat Message Bubbles */
        div[data-testid="stChatMessage"] {
            background: rgba(30, 41, 59, 0.35) !important;
            border: 1px solid rgba(148, 163, 184, 0.1) !important;
            border-radius: 12px !important;
            padding: 0.85rem 1rem !important;
            margin-bottom: 0.65rem !important;
        }

        /* Buttons */
        .stButton > button {
            border-radius: 9px !important;
            font-weight: 600 !important;
            letter-spacing: 0.2px !important;
            transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
            border: 1px solid rgba(148, 163, 184, 0.2) !important;
        }
        .stButton > button:hover {
            transform: translateY(-1px);
            border-color: #38bdf8 !important;
            box-shadow: 0 4px 14px rgba(56, 189, 248, 0.2) !important;
        }
        .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #0284c7 0%, #2563eb 100%) !important;
            border: 1px solid rgba(56, 189, 248, 0.4) !important;
            color: #ffffff !important;
        }

        /* Top Console Telemetry Banner */
        .console-banner {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: linear-gradient(90deg, rgba(15, 23, 42, 0.85) 0%, rgba(15, 23, 42, 0.4) 100%);
            border: 1px solid rgba(148, 163, 184, 0.15);
            border-radius: 12px;
            padding: 12px 18px;
            margin-bottom: 14px;
            backdrop-filter: blur(10px);
        }
        .banner-left {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .banner-icon {
            width: 36px;
            height: 36px;
            border-radius: 9px;
            background: linear-gradient(135deg, #0ea5e9, #6366f1);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 18px;
            box-shadow: 0 0 15px rgba(14, 165, 233, 0.35);
        }
        .banner-title {
            font-size: 16px;
            font-weight: 700;
            color: #f8fafc;
            margin: 0;
            line-height: 1.2;
        }
        .banner-sub {
            font-size: 12px;
            color: #94a3b8;
            margin: 0;
        }
        .banner-pills {
            display: flex;
            gap: 8px;
            align-items: center;
        }
        .meta-pill {
            background: rgba(30, 41, 59, 0.75);
            border: 1px solid rgba(148, 163, 184, 0.2);
            color: #cbd5e1;
            font-family: 'JetBrains Mono', monospace;
            font-size: 11px;
            padding: 4px 10px;
            border-radius: 999px;
        }
        .meta-pill.online {
            background: rgba(16, 185, 129, 0.12);
            border-color: rgba(16, 185, 129, 0.35);
            color: #34d399;
        }

        /* Sidebar Profile, Thread ID & Order Cards */
        .profile-card {
            background: rgba(30, 41, 59, 0.45);
            border: 1px solid rgba(148, 163, 184, 0.15);
            border-radius: 10px;
            padding: 12px;
            margin-bottom: 10px;
        }
        .profile-name {
            font-size: 14px;
            font-weight: 700;
            color: #f8fafc;
            margin-bottom: 2px;
        }
        .profile-email {
            font-size: 12px;
            color: #94a3b8;
            font-family: 'JetBrains Mono', monospace;
            margin-bottom: 8px;
        }
        .profile-badge {
            display: inline-block;
            background: rgba(56, 189, 248, 0.12);
            border: 1px solid rgba(56, 189, 248, 0.3);
            color: #38bdf8;
            font-size: 11px;
            font-weight: 600;
            padding: 2px 8px;
            border-radius: 6px;
        }
        .thread-card {
            background: rgba(15, 23, 42, 0.75);
            border: 1px solid rgba(56, 189, 248, 0.25);
            border-radius: 10px;
            padding: 10px 12px;
            margin-bottom: 10px;
        }
        .thread-label {
            font-size: 10.5px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: #94a3b8;
            margin-bottom: 4px;
        }
        .thread-value {
            font-family: 'JetBrains Mono', monospace;
            font-size: 12.5px;
            font-weight: 700;
            color: #38bdf8;
            word-break: break-all;
        }
        .order-card {
            background: rgba(15, 23, 42, 0.65);
            border: 1px solid rgba(148, 163, 184, 0.14);
            border-radius: 9px;
            padding: 10px 12px;
            margin-bottom: 8px;
            transition: border-color 0.2s ease;
        }
        .order-card:hover {
            border-color: rgba(56, 189, 248, 0.4);
        }
        .order-top {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 4px;
        }
        .order-id {
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
            font-weight: 700;
            color: #e2e8f0;
        }
        .order-status {
            font-size: 10px;
            font-weight: 700;
            padding: 2px 7px;
            border-radius: 99px;
            text-transform: uppercase;
            letter-spacing: 0.4px;
        }
        .status-delivered {
            background: rgba(16, 185, 129, 0.15);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }
        .status-processing {
            background: rgba(245, 158, 11, 0.15);
            color: #fbbf24;
            border: 1px solid rgba(245, 158, 11, 0.3);
        }
        .status-other {
            background: rgba(148, 163, 184, 0.15);
            color: #cbd5e1;
            border: 1px solid rgba(148, 163, 184, 0.3);
        }
        .order-bottom {
            display: flex;
            justify-content: space-between;
            font-size: 12px;
            color: #94a3b8;
        }
        .order-amount {
            color: #f8fafc;
            font-weight: 600;
            font-family: 'JetBrains Mono', monospace;
        }

        /* HITL Alert Card */
        .hitl-banner {
            background: linear-gradient(135deg, rgba(127, 29, 29, 0.45), rgba(69, 10, 10, 0.65));
            border: 1px solid rgba(248, 113, 113, 0.45);
            border-left: 4px solid #ef4444;
            border-radius: 10px;
            padding: 12px 14px;
            margin-top: 8px;
            margin-bottom: 10px;
        }
        .hitl-title {
            color: #fca5a5;
            font-size: 13px;
            font-weight: 700;
            margin-bottom: 4px;
        }
        .hitl-desc {
            color: #fecaca;
            font-size: 12px;
            margin: 0;
        }
    </style>
    """,
    unsafe_allow_html=True,
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

if "queued_prompt" not in st.session_state:
    st.session_state.queued_prompt = None

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


def reset_thread_session(customer_id: int):
    """Generates a new Thread ID and resets the conversation and live graph state."""
    st.session_state.thread_id = f"cust-{customer_id}-{uuid.uuid4().hex[:6]}"
    st.session_state.messages = []
    st.session_state.interrupted_state = None
    st.session_state.graph_visual_state = {
        "active_node": None,
        "from_node": None,
        "to_node": None,
        "visited_nodes": [],
        "status_mode": "idle",
        "badge": "IDLE",
        "detail": f"New thread ({st.session_state.thread_id}) initialized. Waiting for user prompt...",
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
        "idle": "#64748b",
        "running": "#0ea5e9",
        "hitl": "#ef4444",
        "completed": "#10b981",
        "error": "#f43f5e",
    }
    badge_bg = badge_colors.get(status_mode, "#0ea5e9")

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
    <style>
        * {{
            box-sizing: border-box;
        }}
        body {{
            margin: 0;
            padding: 0;
            background: transparent;
            color: #e2e8f0;
            font-family: 'Inter', system-ui, -apple-system, sans-serif;
        }}
        .graph-card {{
            background: linear-gradient(160deg, #0f172a 0%, #070b14 100%);
            border: 1px solid rgba(148, 163, 184, 0.16);
            border-radius: 14px;
            padding: 14px;
            box-shadow: 0 12px 32px rgba(0, 0, 0, 0.55);
        }}
        .graph-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
            padding-bottom: 8px;
            border-bottom: 1px solid rgba(148, 163, 184, 0.12);
        }}
        .header-left {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .header-title {{
            font-size: 12.5px;
            font-weight: 700;
            color: #f8fafc;
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }}
        .legend-bar {{
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 10px;
            color: #94a3b8;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 4px;
        }}
        .legend-dot {{
            width: 7px;
            height: 7px;
            border-radius: 50%;
        }}
        .live-indicator {{
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 10.5px;
            font-weight: 600;
            color: #e2e8f0;
            background: rgba(30, 41, 59, 0.7);
            border: 1px solid rgba(148, 163, 184, 0.2);
            padding: 3px 9px;
            border-radius: 999px;
            font-family: 'JetBrains Mono', monospace;
        }}
        .pulse-dot {{
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: {badge_bg};
            box-shadow: 0 0 8px {badge_bg};
            animation: pulseDot 1.4s infinite ease-in-out;
        }}
        @keyframes pulseDot {{
            0%, 100% {{ transform: scale(1); opacity: 1; }}
            50% {{ transform: scale(1.45); opacity: 0.55; }}
        }}
        svg {{
            width: 100%;
            height: 295px;
            background: #060913;
            border-radius: 10px;
            border: 1px solid rgba(148, 163, 184, 0.14);
            box-shadow: inset 0 0 24px rgba(0, 0, 0, 0.65);
        }}
        .edge {{
            stroke: #334155;
            stroke-width: 2;
            fill: none;
            stroke-dasharray: 5 5;
            transition: stroke 0.3s ease;
        }}
        .edge.active-edge {{
            stroke: #38bdf8;
            stroke-width: 3;
            stroke-dasharray: 8 4;
            animation: dashFlow 0.5s linear infinite;
            filter: drop-shadow(0 0 6px #38bdf8);
        }}
        @keyframes dashFlow {{
            to {{ stroke-dashoffset: -24; }}
        }}
        .node-box {{
            fill: url(#idleGrad);
            stroke: #334155;
            stroke-width: 1.8;
            rx: 10;
            ry: 10;
            transition: all 0.25s ease;
        }}
        .node-box.visited-node {{
            fill: url(#visitedGrad);
            stroke: #10b981;
            stroke-width: 2;
        }}
        .node-box.active-node {{
            fill: url(#activeGrad);
            stroke: #38bdf8;
            stroke-width: 2.8;
            filter: drop-shadow(0 0 12px rgba(56, 189, 248, 0.65));
            animation: nodePulse 1.1s infinite alternate;
        }}
        .node-box.hitl-node {{
            fill: url(#hitlGrad) !important;
            stroke: #f87171 !important;
            stroke-width: 2.8 !important;
            filter: drop-shadow(0 0 14px rgba(239, 68, 68, 0.75)) !important;
            animation: nodePulse 0.8s infinite alternate;
        }}
        @keyframes nodePulse {{
            from {{ transform: scale(1); }}
            to {{ transform: scale(1.015); }}
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
            font-size: 9px;
            font-family: 'JetBrains Mono', monospace;
            text-anchor: middle;
            pointer-events: none;
        }}
        .telemetry-box {{
            margin-top: 10px;
            background: #04070e;
            border: 1px solid rgba(148, 163, 184, 0.16);
            border-left: 3.5px solid {badge_bg};
            border-radius: 8px;
            padding: 9px 12px;
        }}
        .telemetry-top {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 6px;
        }}
        .telemetry-status {{
            display: flex;
            align-items: center;
            gap: 8px;
            overflow: hidden;
        }}
        .sse-badge {{
            background: {badge_bg};
            color: #ffffff;
            font-family: 'JetBrains Mono', monospace;
            font-size: 10px;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 4px;
            letter-spacing: 0.3px;
            white-space: nowrap;
        }}
        .sse-detail {{
            font-size: 11.5px;
            color: #e2e8f0;
            font-weight: 500;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .mac-dots {{
            display: flex;
            gap: 4px;
        }}
        .mac-dot {{
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: #334155;
        }}
        .sse-code {{
            background: rgba(15, 23, 42, 0.55);
            color: #34d399;
            font-family: 'JetBrains Mono', monospace;
            font-size: 10.5px;
            padding: 7px 9px;
            border-radius: 6px;
            border: 1px solid rgba(148, 163, 184, 0.1);
            white-space: pre-wrap;
            max-height: 68px;
            overflow-y: auto;
            line-height: 1.4;
        }}
    </style>
    </head>
    <body>
    <div class="graph-card">
        <div class="graph-header">
            <div class="header-left">
                <span class="header-title">⚡ LangGraph SSE State Machine</span>
            </div>
            <div class="legend-bar">
                <div class="legend-item"><span class="legend-dot" style="background:#38bdf8;"></span>Active</div>
                <div class="legend-item"><span class="legend-dot" style="background:#10b981;"></span>Visited</div>
                <div class="legend-item"><span class="legend-dot" style="background:#ef4444;"></span>HITL</div>
            </div>
            <div class="live-indicator">
                <span class="pulse-dot"></span>
                <span>{status_mode.upper()}</span>
            </div>
        </div>

        <svg viewBox="0 0 580 300">
            <defs>
                <!-- Subtle Dot Matrix Grid -->
                <pattern id="dotGrid" width="18" height="18" patternUnits="userSpaceOnUse">
                    <circle cx="2" cy="2" r="1" fill="#1e293b" />
                </pattern>
                <!-- Node Gradients -->
                <linearGradient id="idleGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#1e293b" />
                    <stop offset="100%" stop-color="#0f172a" />
                </linearGradient>
                <linearGradient id="visitedGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#065f46" />
                    <stop offset="100%" stop-color="#064e3b" />
                </linearGradient>
                <linearGradient id="activeGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#0284c7" />
                    <stop offset="100%" stop-color="#0c4a6e" />
                </linearGradient>
                <linearGradient id="hitlGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#991b1b" />
                    <stop offset="100%" stop-color="#450a0a" />
                </linearGradient>
            </defs>

            <rect width="580" height="300" fill="url(#dotGrid)" />

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
            <circle id="packetDot" r="5.5" fill="#38bdf8" visibility="hidden" filter="drop-shadow(0 0 8px #38bdf8)" />

            <!-- Row 1: Entry & Reasoning -->
            <g transform="translate(15, 24)">
                <rect id="node-ui" class="node-box" width="95" height="52" />
                <text x="47" y="23" class="node-title">🖥️ Streamlit</text>
                <text x="47" y="39" class="node-sub">Client UI</text>
            </g>

            <g transform="translate(185, 24)">
                <rect id="node-api" class="node-box" width="120" height="52" />
                <text x="60" y="23" class="node-title">⚡ FastAPI SSE</text>
                <text x="60" y="39" class="node-sub">/query/stream</text>
            </g>

            <g transform="translate(375, 24)">
                <rect id="node-assistant" class="node-box" width="140" height="52" />
                <text x="70" y="23" class="node-title">🧠 assistant_node</text>
                <text x="70" y="39" class="node-sub">Groq Qwen-3.8-27B</text>
            </g>

            <!-- Row 2: Tool Execution & ChromaDB -->
            <g transform="translate(165, 128)">
                <rect id="node-chroma" class="node-box" width="130" height="52" />
                <text x="65" y="23" class="node-title">📚 ChromaDB</text>
                <text x="65" y="39" class="node-sub">Policy Vectors</text>
            </g>

            <g transform="translate(380, 128)">
                <rect id="node-tools" class="node-box" width="130" height="52" />
                <text x="65" y="23" class="node-title">🛠️ execute_tools</text>
                <text x="65" y="39" class="node-sub">IDOR &amp; Tool Router</text>
            </g>

            <!-- Row 3: CRAG Loop, MySQL & HITL Gate -->
            <g transform="translate(15, 225)">
                <rect id="node-rewriter" class="node-box" width="110" height="52" />
                <text x="55" y="23" class="node-title">✏️ rewrite_query</text>
                <text x="55" y="39" class="node-sub">Query Optimizer</text>
            </g>

            <g transform="translate(165, 225)">
                <rect id="node-grader" class="node-box" width="130" height="52" />
                <text x="65" y="23" class="node-title">🔍 crag_grader</text>
                <text x="65" y="39" class="node-sub">Pydantic Grader</text>
            </g>

            <g transform="translate(325, 225)">
                <rect id="node-mysql" class="node-box" width="115" height="52" />
                <text x="57" y="23" class="node-title">🗄️ MySQL 8.0</text>
                <text x="57" y="39" class="node-sub">ACID + Row Lock</text>
            </g>

            <g transform="translate(460, 225)">
                <rect id="node-hitl" class="node-box" width="105" height="52" />
                <text x="52" y="23" class="node-title">⏸️ HITL Gate</text>
                <text x="52" y="39" class="node-sub">interrupt()</text>
            </g>
        </svg>

        <div class="telemetry-box">
            <div class="telemetry-top">
                <div class="telemetry-status">
                    <span class="sse-badge">{badge}</span>
                    <span class="sse-detail">{detail}</span>
                </div>
                <div class="mac-dots">
                    <span class="mac-dot"></span>
                    <span class="mac-dot"></span>
                    <span class="mac-dot"></span>
                </div>
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
        components.html(html_code, height=455, scrolling=False)


# -----------------------------------------------------------------------------
# Backend Health & Live SSE Stream Consumer
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
    anim_delay: float = DEFAULT_ANIM_DELAY,
) -> dict:
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
# GATE 1: Modernized Security Login Screen
# -----------------------------------------------------------------------------
if st.session_state.authenticated_user is None:
    _, center_col, _ = st.columns([1, 1.35, 1])
    with center_col:
        is_online = check_backend_health()
        status_pill = (
            '<span class="meta-pill online">● FastAPI Backend Online</span>'
            if is_online
            else '<span class="meta-pill" style="color:#f87171;border-color:rgba(248,113,113,0.4);">● FastAPI Offline (:8000)</span>'
        )

        st.markdown(
            f"""
            <div class="console-banner" style="margin-top: 2rem;">
                <div class="banner-left">
                    <div class="banner-icon">🔐</div>
                    <div>
                        <p class="banner-title">Enterprise Ops Security Gate</p>
                        <p class="banner-sub">Zero-Trust Customer Context &amp; Live LangGraph Telemetry</p>
                    </div>
                </div>
                <div class="banner-pills">{status_pill}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.container(border=True):
            st.caption(
                "Sign in with your customer credentials. Your linked orders, customer ID isolation, "
                "and refund eligibility are resolved automatically from MySQL 8.0."
            )
            with st.form("login_form", clear_on_submit=False):
                email_input = st.text_input("Work Email Address", value="alice@example.com")
                password_input = st.text_input("Password", value="alice123", type="password")
                submit_login = st.form_submit_button(
                    "🔓 Authenticate & Launch Console", type="primary", use_container_width=True
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
                            reset_thread_session(user_data["customer_id"])
                            st.rerun()
                        else:
                            err_detail = resp.json().get("detail", "Authentication failed.")
                            st.error(f"Access Denied: {err_detail}")
                    except requests.RequestException as exc:
                        st.error(f"Could not connect to FastAPI backend: {exc}")

        with st.expander("📋 Seeded Demo Accounts (MySQL 8.0)", expanded=True):
            st.markdown(
                """
                | Persona | Credentials | Seeded Orders |
                | :--- | :--- | :--- |
                | **Alice Smith** *(Customer #1)* | `alice@example.com` / `alice123` | `#999` ($50 Delivered), `#404` ($1200 Processing) |
                | **Bob Jones** *(Customer #2)* | `bob@example.com` / `bob123` | `#555` ($150 Delivered) |
                | **Enterprise Admin** | `admin@example.com` / `admin123` | Full governance oversight |
                """
            )
    st.stop()


# -----------------------------------------------------------------------------
# GATE 2: Authenticated Console (Sidebar + Header + Split Workspace)
# -----------------------------------------------------------------------------
current_user = st.session_state.authenticated_user

with st.sidebar:
    st.markdown("### ⚡ Ops Engine Control")
    st.markdown(
        f"""
        <div class="profile-card">
            <div class="profile-name">👤 {current_user['name']}</div>
            <div class="profile-email">{current_user['email']}</div>
            <span class="profile-badge">🛡️ Customer ID #{current_user['customer_id']}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button("🔒 Sign Out", use_container_width=True):
        st.session_state.authenticated_user = None
        st.session_state.messages = []
        st.session_state.interrupted_state = None
        st.rerun()

    st.divider()
    st.markdown("##### 🧵 Session Thread ID")
    st.markdown(
        f"""
        <div class="thread-card">
            <div class="thread-label">Active LangGraph Thread</div>
            <div class="thread-value">{st.session_state.thread_id}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("🔄 Generate New Thread ID", type="primary", use_container_width=True):
        reset_thread_session(current_user["customer_id"])
        st.rerun()

    st.divider()
    st.markdown("##### 📦 Linked MySQL Orders")
    orders_list = current_user.get("orders", [])
    if not orders_list:
        st.caption("No orders linked to this account.")
    for order in orders_list:
        status_raw = str(order.get("status", "UNKNOWN")).upper()
        if "DELIVER" in status_raw:
            status_cls = "status-delivered"
        elif "PROCESS" in status_raw or "PEND" in status_raw:
            status_cls = "status-processing"
        else:
            status_cls = "status-other"

        item_label = order.get("item_name", "Enterprise Order")
        amount_val = float(order.get("total_amount", 0.0))

        st.markdown(
            f"""
            <div class="order-card">
                <div class="order-top">
                    <span class="order-id">Order #{order['id']}</span>
                    <span class="order-status {status_cls}">{status_raw}</span>
                </div>
                <div class="order-bottom">
                    <span>{item_label}</span>
                    <span class="order-amount">${amount_val:,.2f}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# Top Console Header Banner
st.markdown(
    f"""
    <div class="console-banner">
        <div class="banner-left">
            <div class="banner-icon">⚙️</div>
            <div>
                <p class="banner-title">Autonomous Enterprise Operations Console</p>
                <p class="banner-sub">Authenticated Session for <strong>{current_user['name']}</strong> • CRAG Policy Grounding + HITL SQL Governance</p>
            </div>
        </div>
        <div class="banner-pills">
            <span class="meta-pill">THREAD: {st.session_state.thread_id}</span>
            <span class="meta-pill online">● SSE STREAM READY</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

chat_col, inspector_col = st.columns([1.22, 1.18], gap="large")

# -----------------------------------------------------------------------------
# Right Column: Sticky Live Animated SSE Graph & HITL Governance Gate
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

        st.markdown(
            """
            <div class="hitl-banner">
                <div class="hitl-title">⚠️ HITL Governance Gate Active — Administrator Decision Required</div>
                <p class="hitl-desc">LangGraph execution is paused at <code>interrupt()</code> prior to executing a state-changing MySQL write.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if isinstance(pending_action, dict) and pending_action.get("args"):
            with st.expander("🔍 Inspect Auto-Resolved Tool Arguments & SQL Preview", expanded=False):
                st.json(pending_action["args"])
                st.code(str(pending_sql), language="sql")

        btn_col1, btn_col2 = st.columns(2)

        with btn_col1:
            if st.button("✅ Approve & Execute SQL", type="primary", use_container_width=True):
                try:
                    res = consume_sse_stream_with_live_graph(
                        APPROVE_STREAM_ENDPOINT,
                        {"thread_id": st.session_state.thread_id, "decision": "approve"},
                        graph_placeholder,
                        is_approval_resume=True,
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
# Left Column: Fixed-Height Scrollable Chat History Container
# -----------------------------------------------------------------------------
with chat_col:
    chat_scroll_box = st.container(height=510, border=True)

    with chat_scroll_box:
        if not st.session_state.messages:
            st.markdown(
                """
                <div style="text-align:center; padding: 36px 20px 18px 20px;">
                    <div style="font-size: 28px; margin-bottom: 8px;">✨</div>
                    <div style="font-size: 15px; font-weight: 600; color: #f8fafc; margin-bottom: 6px;">
                        Ready to Execute Operations Workflow
                    </div>
                    <div style="font-size: 12.5px; color: #94a3b8; max-width: 420px; margin: 0 auto 18px auto;">
                        Ask a policy question, inspect your live MySQL orders, or initiate an automated refund to watch the SSE state machine animate in real time.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            q_col1, q_col2, q_col3 = st.columns(3)
            with q_col1:
                if st.button("📦 Check my orders", use_container_width=True):
                    st.session_state.queued_prompt = "What is the status of my current orders?"
                    st.rerun()
            with q_col2:
                if st.button("📜 Refund policy", use_container_width=True):
                    st.session_state.queued_prompt = "What is the company refund and return policy?"
                    st.rerun()
            with q_col3:
                if st.button("💸 Request a refund", use_container_width=True):
                    st.session_state.queued_prompt = "I would like to request a refund for my delivered order."
                    st.rerun()

        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg.get("metadata"):
                    with st.expander("📡 View Raw SSE Telemetry JSON"):
                        st.json(msg["metadata"])

# -----------------------------------------------------------------------------
# Pinned Bottom Input Bar (Supports both direct typing and quick-action buttons)
# -----------------------------------------------------------------------------
input_disabled = st.session_state.interrupted_state is not None
typed_prompt = st.chat_input(
    "Ask a policy question, check your orders, or request a refund...",
    disabled=input_disabled,
)

user_prompt = typed_prompt or st.session_state.queued_prompt
if st.session_state.queued_prompt:
    st.session_state.queued_prompt = None

if user_prompt:
    st.session_state.messages.append({"role": "user", "content": user_prompt})
    with chat_scroll_box:
        with st.chat_message("user"):
            st.markdown(user_prompt)

        with st.chat_message("assistant"):
            with st.spinner("Streaming LangGraph SSE events (watch live node graph on the right →)..."):
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