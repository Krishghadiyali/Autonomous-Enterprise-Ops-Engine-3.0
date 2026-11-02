from typing import Literal, Optional
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str = Field(..., description="Registered customer or admin email address.")
    password: str = Field(..., min_length=3, description="Account password.")


class LoginResponse(BaseModel):
    customer_id: int
    name: str
    email: str
    role: str
    orders: list[dict] = []


class QueryRequest(BaseModel):
    thread_id: str = Field(..., min_length=1, description="Unique conversation thread ID.")
    query: str = Field(..., min_length=1, description="Natural language user prompt.")
    customer_id: int = Field(
        default=1,
        gt=0,
        description="Authenticated customer ID injected from the login session.",
    )


class ApprovalRequest(BaseModel):
    thread_id: str = Field(..., min_length=1, description="Paused thread ID awaiting approval.")
    decision: Literal["approve", "reject"] = Field(
        ..., description="Administrator decision ('approve' or 'reject')."
    )
    reason: Optional[str] = Field(
        default=None, description="Optional audit note from administrator."
    )