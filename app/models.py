from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class OrderStatus(StrEnum):
    CREATED = "CREATED"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    PAID = "PAID"
    DISPATCHING = "DISPATCHING"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class OrderCreate(BaseModel):
    customer_id: str = Field(min_length=2, max_length=64)
    region: str = Field(default="central", pattern="^(north|central|south|east|west)$")
    priority: str = Field(default="standard", pattern="^(standard|express)$")
    payment_method: str = Field(default="card", pattern="^(card|wallet|cash)$")
    amount: float = Field(gt=0, le=10000)


class Order(BaseModel):
    id: str
    customer_id: str
    region: str
    priority: str
    payment_method: str
    amount: float
    status: OrderStatus
    driver_id: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    estimated_delivery_minutes: int = 45
    actual_delivery_minutes: int | None = None


class ScenarioUpdate(BaseModel):
    enabled: bool

