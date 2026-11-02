from .sql_tools import list_customer_orders, read_order_status, execute_refund
from .rag_tools import search_company_policies

# This is the exact list of tools the AI Agent will have access to
AGENT_TOOLS = [
    list_customer_orders,
    read_order_status,
    execute_refund,
    search_company_policies,
]