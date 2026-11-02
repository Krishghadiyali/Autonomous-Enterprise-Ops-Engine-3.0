import os
import sqlite3
from typing import Annotated, Literal, Optional
from typing_extensions import TypedDict
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import AnyMessage, ToolMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START
from langgraph.graph.message import add_messages
from langgraph.types import interrupt
from langgraph.checkpoint.sqlite import SqliteSaver
from pydantic import SecretStr, BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from app.tools import AGENT_TOOLS
from app.db.database import get_db_connection

load_dotenv()


# 1. Define the Agent's Memory State
class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    retrieved_documents: list[str]
    relevance_score: Literal["yes", "no", ""]
    rewrite_count: int
    customer_id: Optional[int]


# 2. Initialize the LLM
api_key_str = os.getenv("GROQ_API_KEY")
llm = ChatGroq(
    model="qwen/qwen3.8-27b",
    api_key=SecretStr(api_key_str) if api_key_str else None,
)
llm_with_tools = llm.bind_tools(AGENT_TOOLS)


def get_latest_user_question(messages: list[AnyMessage]) -> str:
    """Finds the most recent real user question (ignoring synthetic CRAG rewrite instructions)."""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            text = str(msg.content)
            if not text.startswith("The previous search failed."):
                return text
    return str(messages[0].content) if messages else ""


# --- CRAG GRADER SETUP ---
class GradeDocuments(BaseModel):
    """Binary score for relevance check on retrieved documents."""
    binary_score: Literal["yes", "no"] = Field(
        description="Documents are relevant to the question, 'yes' or 'no'"
    )


def build_crag_grader():
    structured_llm_grader = llm.with_structured_output(GradeDocuments)
    system_prompt = (
        "You are a grader assessing relevance of a retrieved document to a user question. "
        "If the document contains keyword(s) or semantic meaning related to the user question, grade it as relevant. "
        "It does not need to be a stringent test. The goal is to filter out erroneous retrievals. "
        "Give a binary score 'yes' or 'no' score to indicate whether the document is relevant to the question."
    )
    grade_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("human", "Retrieved document: \n\n {document} \n\n User question: {question}"),
        ]
    )
    return grade_prompt | structured_llm_grader


def crag_grader_node(state: AgentState):
    """Evaluates retrieved documents against the latest user question."""
    question = get_latest_user_question(state["messages"])
    documents = [str(state["messages"][-1].content)]

    retrieval_grader = build_crag_grader()
    filtered_docs = []

    for doc in documents:
        score = retrieval_grader.invoke({"question": question, "document": doc})
        if isinstance(score, dict):
            is_relevant = score.get("binary_score") == "yes"
        else:
            is_relevant = getattr(score, "binary_score", "no") == "yes"

        if is_relevant:
            filtered_docs.append(doc)

    relevance_score = "yes" if filtered_docs else "no"
    return {
        "retrieved_documents": filtered_docs,
        "relevance_score": relevance_score,
    }


def rewrite_query_node(state: AgentState):
    """Rewrites the latest user query if the CRAG grader found retrieved documents irrelevant."""
    original_question = get_latest_user_question(state["messages"])
    current_rewrites = state.get("rewrite_count", 0) + 1

    system_prompt = (
        "You are an expert at optimizing search queries for vector databases. "
        "The previous search yielded irrelevant results. "
        "Analyze the original question and write a better, more specific search query. "
        "Return ONLY the rewritten query text, with no additional commentary."
    )
    rewrite_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("human", "Original Question: {question}"),
        ]
    )

    chain = rewrite_prompt | llm
    response = chain.invoke({"question": original_question})

    return {
        "rewrite_count": current_rewrites,
        "messages": [
            HumanMessage(
                content=(
                    "The previous search failed. Please use the search_company_policies tool "
                    f"again with this refined query: {response.content}"
                )
            )
        ],
    }


def route_after_tools(state: AgentState) -> Literal["crag_grader_node", "assistant_node"]:
    last_message = state["messages"][-1]
    if getattr(last_message, "name", None) == "search_company_policies":
        return "crag_grader_node"
    return "assistant_node"


def route_after_grader(state: AgentState) -> Literal["rewrite_query_node", "assistant_node"]:
    # Cap CRAG self-correction at 2 rewrites to prevent infinite recursion
    if state.get("relevance_score") == "no" and state.get("rewrite_count", 0) < 2:
        return "rewrite_query_node"
    return "assistant_node"


def _resolve_refund_preview(tool_args: dict, customer_id: Optional[int]) -> dict:
    """Pre-populates missing order_id and amount from MySQL for the HITL approval preview."""
    resolved = dict(tool_args)
    if customer_id is not None:
        resolved["customer_id"] = customer_id

    if resolved.get("order_id") is not None and resolved.get("amount") is not None:
        return resolved

    try:
        conn = get_db_connection(read_only=True)
        cursor = conn.cursor(dictionary=True)
        if resolved.get("order_id") is not None:
            cursor.execute(
                "SELECT id, total_amount FROM orders WHERE id = %s",
                (resolved["order_id"],),
            )
        elif customer_id is not None:
            cursor.execute(
                "SELECT id, total_amount FROM orders WHERE customer_id = %s AND status = 'delivered' ORDER BY id DESC LIMIT 1",
                (customer_id,),
            )
        else:
            cursor.close()
            conn.close()
            return resolved

        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if row:
            if resolved.get("order_id") is None:
                resolved["order_id"] = int(row["id"])
            if resolved.get("amount") is None:
                resolved["amount"] = float(row["total_amount"])
    except Exception:
        pass
    return resolved


# 3. Define the Core Nodes
def assistant_node(state: AgentState):
    """The reasoning engine that evaluates the prompt and decides on tools."""
    cid = state.get("customer_id") or 1
    sys_msg = SystemMessage(
        content=(
            f"You are the Autonomous Enterprise Operations Assistant. "
            f"The user is already authenticated with customer_id={cid}. "
            "IMPORTANT RULES:\n"
            "1. The user does NOT need to provide their order_id or refund amount in the prompt.\n"
            "2. If a user asks about their orders without giving an order_id, call `list_customer_orders`.\n"
            "3. If a user requests a refund, call `execute_refund` IMMEDIATELY. If they did not specify "
            "an `order_id` or `amount`, leave `order_id` and `amount` omitted/null — the backend will "
            "automatically resolve their delivered order and full refund amount from the database. "
            "Never ask the user to type their order ID or refund amount before calling `execute_refund`."
        )
    )
    response = llm_with_tools.invoke([sys_msg] + list(state["messages"]))
    return {"messages": [response]}


def execute_tools_node(state: AgentState):
    """Executes the chosen tools, enforcing customer_id isolation and a mandatory pause for refunds."""
    last_message = state["messages"][-1]
    tool_calls = getattr(last_message, "tool_calls", [])

    if not tool_calls:
        return {"messages": []}

    authenticated_cid = state.get("customer_id")
    results = []

    for tool_call in tool_calls:
        tool_name = tool_call["name"]
        tool_args = dict(tool_call["args"])

        # Deterministically bind authenticated customer_id so LLM cannot spoof another user
        if tool_name in ("list_customer_orders", "read_order_status", "execute_refund"):
            if authenticated_cid is not None:
                tool_args["customer_id"] = authenticated_cid

        # --- HUMAN-IN-THE-LOOP GUARDRAIL ---
        if tool_name == "execute_refund":
            tool_args = _resolve_refund_preview(tool_args, authenticated_cid)
            human_decision = interrupt(
                {
                    "action": "require_approval",
                    "tool": tool_name,
                    "args": tool_args,
                    "sql_preview": (
                        f"INSERT INTO refunds (order_id, refund_amount, reason) "
                        f"VALUES ({tool_args.get('order_id')}, {tool_args.get('amount')}, '{tool_args.get('reason')}');\n"
                        f"UPDATE orders SET status = 'refunded' WHERE id = {tool_args.get('order_id')};"
                    ),
                }
            )

            if str(human_decision).lower() != "approve":
                results.append(
                    ToolMessage(
                        tool_call_id=tool_call["id"],
                        name=tool_name,
                        content="Action was rejected by human administrator.",
                    )
                )
                continue

        tool_fn = next(t for t in AGENT_TOOLS if t.name == tool_name)
        try:
            tool_result = tool_fn.invoke(tool_args)
            results.append(
                ToolMessage(
                    tool_call_id=tool_call["id"],
                    name=tool_name,
                    content=str(tool_result),
                )
            )
        except Exception as e:
            results.append(
                ToolMessage(
                    tool_call_id=tool_call["id"],
                    name=tool_name,
                    content=f"Error executing tool: {str(e)}",
                )
            )

    return {"messages": results}


def router(state: AgentState) -> Literal["execute_tools_node", "__end__"]:
    last_message = state["messages"][-1]
    if getattr(last_message, "tool_calls", None):
        return "execute_tools_node"
    return "__end__"


# 5. Compile the Graph
builder = StateGraph(AgentState)
builder.add_node("assistant_node", assistant_node)
builder.add_node("execute_tools_node", execute_tools_node)
builder.add_node("crag_grader_node", crag_grader_node)
builder.add_node("rewrite_query_node", rewrite_query_node)

builder.add_edge(START, "assistant_node")
builder.add_conditional_edges("assistant_node", router)
builder.add_conditional_edges("execute_tools_node", route_after_tools)
builder.add_conditional_edges("crag_grader_node", route_after_grader)
builder.add_edge("rewrite_query_node", "assistant_node")

CHECKPOINT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "chroma_db"
)
os.makedirs(CHECKPOINT_DIR, exist_ok=True)
CHECKPOINT_DB_PATH = os.path.join(CHECKPOINT_DIR, "langgraph_checkpoints.sqlite")

sqlite_conn = sqlite3.connect(CHECKPOINT_DB_PATH, check_same_thread=False)
checkpointer = SqliteSaver(sqlite_conn)

ops_agent_graph = builder.compile(checkpointer=checkpointer)