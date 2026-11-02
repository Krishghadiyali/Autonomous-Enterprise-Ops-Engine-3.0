from decimal import Decimal
from typing import Optional
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from app.db.database import get_db_connection


class ListOrdersInput(BaseModel):
    customer_id: int = Field(
        default=1,
        gt=0,
        description="The authenticated customer ID (injected automatically by runtime).",
    )


class ReadOrderInput(BaseModel):
    order_id: int = Field(
        ...,
        gt=0,
        description="The unique positive integer ID of the customer order to inspect.",
    )
    customer_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Authenticated customer ID for ownership verification.",
    )


class ExecuteRefundInput(BaseModel):
    order_id: Optional[int] = Field(
        default=None,
        gt=0,
        description=(
            "Optional positive integer ID of the order being refunded. "
            "If omitted by the user, the system automatically resolves their eligible delivered order."
        ),
    )
    amount: Optional[float] = Field(
        default=None,
        gt=0,
        description=(
            "Optional dollar amount to refund. "
            "If omitted by the user, the system automatically refunds the full order total_amount from MySQL."
        ),
    )
    reason: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Clear audit reason explaining why the refund is being issued.",
    )
    customer_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Authenticated customer ID (injected automatically by runtime).",
    )


@tool("list_customer_orders", args_schema=ListOrdersInput)
def list_customer_orders(customer_id: int = 1) -> str:
    """
    Use this read-only tool to list all orders belonging to the currently logged-in customer.
    Call this tool when the user asks about 'my orders' or requests a refund without giving an order_id.
    """
    conn = get_db_connection(read_only=True)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT id, item_name, total_amount, status FROM orders WHERE customer_id = %s ORDER BY id DESC",
            (customer_id,),
        )
        rows = cursor.fetchall()
        if not rows:
            return f"No orders found for customer #{customer_id}."

        lines = [
            f"- Order #{r['id']} ({r.get('item_name', 'Order')}): Status='{r['status']}', Total=${r['total_amount']}"
            for r in rows
        ]
        return "Authenticated Customer Orders:\n" + "\n".join(lines)
    except Exception as exc:
        return f"Database read error: {str(exc)}"
    finally:
        cursor.close()
        conn.close()


@tool("read_order_status", args_schema=ReadOrderInput)
def read_order_status(order_id: int, customer_id: Optional[int] = None) -> str:
    """
    Use this read-only tool to check the current status and total_amount of a specific customer order.
    """
    conn = get_db_connection(read_only=True)
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute(
            "SELECT id, customer_id, total_amount, status FROM orders WHERE id = %s",
            (order_id,),
        )
        result = cursor.fetchone()

        if not result:
            return f"Order #{order_id} was not found in the database."

        if customer_id is not None and result.get("customer_id") is not None:
            if int(result["customer_id"]) != int(customer_id):
                return (
                    f"Access Denied (Security Guardrail): Order #{order_id} does not belong "
                    "to your authenticated account."
                )

        return (
            f"Order #{result['id']} is currently '{result['status']}' "
            f"with a total amount of ${result['total_amount']}."
        )
    except Exception as exc:
        return f"Database read error: {str(exc)}"
    finally:
        cursor.close()
        conn.close()


@tool("execute_refund", args_schema=ExecuteRefundInput)
def execute_refund(
    reason: str,
    order_id: Optional[int] = None,
    amount: Optional[float] = None,
    customer_id: Optional[int] = None,
) -> str:
    """
    Use this tool to execute a database write to log a refund for a customer order.
    CRITICAL INSTRUCTION: Trigger this tool IMMEDIATELY when a user requests a refund.
    The user does NOT need to provide order_id or amount; if omitted, leave them null/None
    and this tool will automatically resolve the order and full refund amount from the database.
    """
    conn = get_db_connection(read_only=False)
    cursor = conn.cursor(dictionary=True)

    try:
        # 1. Auto-resolve order_id for the logged-in customer if not explicitly provided
        if order_id is None:
            if customer_id is None:
                conn.rollback()
                return "Refund aborted: Neither order_id nor authenticated customer_id was provided."

            cursor.execute(
                """
                SELECT id, customer_id, total_amount, status
                FROM orders
                WHERE customer_id = %s AND status = 'delivered'
                ORDER BY id DESC
                FOR UPDATE
                """,
                (customer_id,),
            )
            order = cursor.fetchone()
            if not order:
                conn.rollback()
                return (
                    "Refund aborted: No eligible 'delivered' order was found under your "
                    "authenticated account."
                )
            order_id = int(order["id"])
        else:
            # Lock the specific target order row for atomic validation
            cursor.execute(
                "SELECT id, customer_id, total_amount, status FROM orders WHERE id = %s FOR UPDATE",
                (order_id,),
            )
            order = cursor.fetchone()

        if not order:
            conn.rollback()
            return f"Refund aborted: Order #{order_id} does not exist."

        # 2. Ownership Security Check (IDOR Prevention)
        if customer_id is not None and order.get("customer_id") is not None:
            if int(order["customer_id"]) != int(customer_id):
                conn.rollback()
                return (
                    f"Access Denied (Security Guardrail): Order #{order_id} does not belong "
                    "to your authenticated account."
                )

        # 3. Idempotency Check #1: Order status is already 'refunded'
        current_status = str(order["status"]).lower()
        if current_status == "refunded":
            conn.rollback()
            return (
                f"Idempotency Guard Triggered: Order #{order_id} has already been refunded. "
                "No duplicate refund was created."
            )

        # 4. Idempotency Check #2: Verify no existing record in `refunds` table
        cursor.execute(
            "SELECT refund_id, refund_amount FROM refunds WHERE order_id = %s",
            (order_id,),
        )
        existing_refund = cursor.fetchone()
        if existing_refund:
            conn.rollback()
            return (
                f"Idempotency Guard Triggered: Refund #{existing_refund['refund_id']} "
                f"(${existing_refund['refund_amount']}) already exists for Order #{order_id}."
            )

        # 5. Auto-resolve refund amount from database if user did not specify an amount
        max_refundable = Decimal(str(order["total_amount"]))
        if amount is None:
            requested_amount = max_refundable
        else:
            requested_amount = Decimal(str(round(amount, 2)))

        # 6. Business Guardrail: Requested refund cannot exceed the order's total_amount
        if requested_amount > max_refundable:
            conn.rollback()
            return (
                f"Validation Error: Requested refund (${requested_amount}) exceeds the "
                f"original total amount (${max_refundable}) for Order #{order_id}."
            )

        # 7. Execute atomic write transaction
        cursor.execute(
            "INSERT INTO refunds (order_id, refund_amount, reason) VALUES (%s, %s, %s)",
            (order_id, float(requested_amount), reason.strip()),
        )
        cursor.execute(
            "UPDATE orders SET status = 'refunded' WHERE id = %s",
            (order_id,),
        )
        conn.commit()
        return (
            f"Successfully processed a ${requested_amount:.2f} refund for Order #{order_id} "
            f"and updated order status to 'refunded'."
        )
    except Exception as exc:
        conn.rollback()
        return f"Failed to execute refund transaction: {str(exc)}"
    finally:
        cursor.close()
        conn.close()