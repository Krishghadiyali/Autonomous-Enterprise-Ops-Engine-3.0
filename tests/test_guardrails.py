from decimal import Decimal
from unittest.mock import MagicMock, patch
import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient
from langchain_core.messages import HumanMessage, AIMessage

from app.main import app
from app.routers.agent import _hash_password
from app.schemas.schemas import LoginRequest
from app.tools.sql_tools import (
    ListOrdersInput,
    ReadOrderInput,
    ExecuteRefundInput,
    list_customer_orders,
    read_order_status,
    execute_refund,
)
from app.agent.agent import get_latest_user_question, route_after_grader

client = TestClient(app)


# -----------------------------------------------------------------------------
# 1. Pydantic Input Schema Tests (v3.0 Schemas)
# -----------------------------------------------------------------------------
@pytest.mark.unit
def test_pydantic_rejects_invalid_inputs_and_allows_optional_auto_resolve():
    """Verifies negative IDs/amounts fail while optional order_id/amount in ExecuteRefundInput succeed."""
    with pytest.raises(ValidationError):
        ReadOrderInput(order_id=0)

    with pytest.raises(ValidationError):
        ListOrdersInput(customer_id=-1)

    with pytest.raises(ValidationError):
        ExecuteRefundInput(order_id=999, amount=-10.0, reason="Damaged item")

    with pytest.raises(ValidationError):
        ExecuteRefundInput(order_id=999, amount=25.0, reason="no")  # min_length=3

    # v3.0 Smart Auto-Resolution: order_id and amount can be omitted (None)
    valid_auto = ExecuteRefundInput(reason="Headphones arrived damaged", customer_id=1)
    assert valid_auto.order_id is None
    assert valid_auto.amount is None


# -----------------------------------------------------------------------------
# 2. v3.0 Authentication Endpoint Tests (/agent/login)
# -----------------------------------------------------------------------------
@pytest.mark.unit
@patch("app.routers.agent.get_db_connection")
def test_login_endpoint_succeeds_for_valid_credentials(mock_get_db):
    """Verifies /agent/login authenticates SHA-256 password hash and returns customer orders."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_get_db.return_value = mock_conn

    mock_cursor.fetchone.return_value = {
        "id": 1,
        "name": "Alice Smith",
        "email": "alice@example.com",
        "password_hash": _hash_password("alice123"),
        "role": "customer",
    }
    mock_cursor.fetchall.return_value = [
        {
            "id": 999,
            "item_name": "Wireless Noise-Cancelling Headphones",
            "total_amount": Decimal("50.00"),
            "status": "delivered",
        }
    ]

    response = client.post(
        "/agent/login",
        json={"email": "alice@example.com", "password": "alice123"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["customer_id"] == 1
    assert payload["name"] == "Alice Smith"
    assert payload["role"] == "customer"
    assert len(payload["orders"]) == 1
    assert payload["orders"][0]["id"] == 999


@pytest.mark.unit
@patch("app.routers.agent.get_db_connection")
def test_login_endpoint_rejects_wrong_password_with_401(mock_get_db):
    """Verifies /agent/login returns HTTP 401 when password hash does not match."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_get_db.return_value = mock_conn

    mock_cursor.fetchone.return_value = {
        "id": 1,
        "name": "Alice Smith",
        "email": "alice@example.com",
        "password_hash": _hash_password("alice123"),
        "role": "customer",
    }

    response = client.post(
        "/agent/login",
        json={"email": "alice@example.com", "password": "wrongpassword"},
    )
    assert response.status_code == 401


# -----------------------------------------------------------------------------
# 3. v3.0 Multi-Tenant Security & SQL Tool Tests
# -----------------------------------------------------------------------------
@pytest.mark.unit
@patch("app.tools.sql_tools.get_db_connection")
def test_list_customer_orders_returns_authenticated_user_orders(mock_get_db):
    """Verifies list_customer_orders queries read-only connection and formats item_name."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_get_db.return_value = mock_conn

    mock_cursor.fetchall.return_value = [
        {
            "id": 999,
            "item_name": "Wireless Noise-Cancelling Headphones",
            "total_amount": Decimal("50.00"),
            "status": "delivered",
        }
    ]

    result = list_customer_orders.invoke({"customer_id": 1})
    mock_get_db.assert_called_once_with(read_only=True)
    assert "Order #999" in result
    assert "Wireless Noise-Cancelling Headphones" in result


@pytest.mark.unit
@patch("app.tools.sql_tools.get_db_connection")
def test_read_order_status_blocks_cross_customer_access(mock_get_db):
    """Security Guardrail (IDOR): Customer #1 must be blocked from viewing Customer #2's Order #555."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_get_db.return_value = mock_conn

    mock_cursor.fetchone.return_value = {
        "id": 555,
        "customer_id": 2,  # Belongs to Bob Jones (Customer #2)
        "total_amount": Decimal("150.00"),
        "status": "delivered",
    }

    result = read_order_status.invoke({"order_id": 555, "customer_id": 1})
    assert "Access Denied (Security Guardrail)" in result


@pytest.mark.unit
@patch("app.tools.sql_tools.get_db_connection")
def test_execute_refund_auto_resolves_delivered_order_and_full_amount(mock_get_db):
    """v3.0 Smart Refund: Omitting order_id and amount auto-resolves latest delivered order and full price."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_get_db.return_value = mock_conn

    # 1st fetchone(): resolves delivered Order #999 ($50.00) for customer_id=1
    # 2nd fetchone(): checks refunds table (None -> no prior refund)
    mock_cursor.fetchone.side_effect = [
        {
            "id": 999,
            "customer_id": 1,
            "item_name": "Wireless Noise-Cancelling Headphones",
            "total_amount": Decimal("50.00"),
            "status": "delivered",
        },
        None,
    ]

    result = execute_refund.invoke(
        {"reason": "Arrived defective", "order_id": None, "amount": None, "customer_id": 1}
    )

    assert "999" in result
    assert "50.00" in result
    mock_conn.commit.assert_called_once()


@pytest.mark.unit
@patch("app.tools.sql_tools.get_db_connection")
def test_execute_refund_blocks_duplicate_refund_on_refunded_order(mock_get_db):
    """Idempotency Check: Must block refund if order status is already 'refunded'."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_get_db.return_value = mock_conn

    mock_cursor.fetchone.return_value = {
        "id": 999,
        "customer_id": 1,
        "total_amount": Decimal("50.00"),
        "status": "refunded",
    }

    result = execute_refund.invoke(
        {"order_id": 999, "amount": 50.0, "reason": "Duplicate refund attempt", "customer_id": 1}
    )

    assert "already been refunded" in result or "Idempotency" in result
    mock_conn.rollback.assert_called_once()
    mock_conn.commit.assert_not_called()


@pytest.mark.unit
@patch("app.tools.sql_tools.get_db_connection")
def test_execute_refund_blocks_amount_exceeding_order_total(mock_get_db):
    """Business Guardrail: Must reject any refund amount greater than the order's total_amount."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_get_db.return_value = mock_conn

    mock_cursor.fetchone.side_effect = [
        {"id": 999, "customer_id": 1, "total_amount": Decimal("50.00"), "status": "delivered"},
        None,
    ]

    result = execute_refund.invoke(
        {"order_id": 999, "amount": 500.00, "reason": "Hallucinated 10x amount", "customer_id": 1}
    )

    assert "exceeds" in result.lower()
    mock_conn.rollback.assert_called_once()
    mock_conn.commit.assert_not_called()


# -----------------------------------------------------------------------------
# 4. CRAG State Helpers & FastAPI Contract Tests
# -----------------------------------------------------------------------------
@pytest.mark.unit
def test_get_latest_user_question_ignores_synthetic_rewrites():
    messages = [
        HumanMessage(content="Check status of order 999"),
        AIMessage(content="Order #999 is delivered."),
        HumanMessage(content="What is the restocking fee on refused deliveries?"),
        HumanMessage(
            content="The previous search failed. Please use the search_company_policies tool again with this refined query: restocking fee"
        ),
    ]
    assert (
        get_latest_user_question(messages)
        == "What is the restocking fee on refused deliveries?"
    )


@pytest.mark.unit
def test_crag_route_after_grader_caps_rewrites_at_two():
    assert route_after_grader({"relevance_score": "no", "rewrite_count": 1}) == "rewrite_query_node"
    assert route_after_grader({"relevance_score": "no", "rewrite_count": 2}) == "assistant_node"


@pytest.mark.unit
def test_health_and_unpaused_approve_endpoints():
    health_res = client.get("/health")
    assert health_res.status_code == 200

    approve_res = client.post(
        "/agent/approve",
        json={"thread_id": "non-existent-thread-v3", "decision": "approve"},
    )
    assert approve_res.status_code == 400