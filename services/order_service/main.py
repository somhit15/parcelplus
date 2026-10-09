import asyncio
import time
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import BaseModel, Field

from shared import db
from shared.events import consume, publish
from shared.web import create_app
from shared.telemetry import increment, observe, event_log

scenario_flags = {"database_latency": False, "high_cpu_processing": False}


class OrderCreate(BaseModel):
    customer_id: str = Field(min_length=2)
    region: str = "central"
    priority: str = "standard"
    payment_method: str = "card"
    amount: float = Field(gt=0)


async def startup():
    await db.execute("""CREATE TABLE IF NOT EXISTS orders (id text primary key, customer_id text not null, region text not null, priority text not null, payment_method text not null, amount numeric not null, status text not null, driver_id text, created_at timestamptz not null, completed_at timestamptz)""")
    asyncio.create_task(consume("order-service", ["PaymentAuthorized", "PaymentFailed", "DriverAssigned", "DeliveryCompleted", "DeliveryDelayed", "ScenarioChanged"], handle_event))
    asyncio.create_task(recover_stuck_orders())


async def recover_stuck_orders():
    # Repair orders created by earlier versions that displayed OUT_FOR_DELIVERY
    # even though dispatch had no driver available.
    while True:
        await asyncio.sleep(4)
        rows = await db.fetch("SELECT id, region, priority, amount FROM orders WHERE status IN ('OUT_FOR_DELIVERY','DISPATCHING') AND driver_id IS NULL")
        for row in rows:
            await db.execute("UPDATE orders SET status='DISPATCHING' WHERE id=$1", row["id"])
            await publish("DispatchRetryRequested", {"order_id": row["id"], "region": row["region"], "priority": row["priority"], "amount": float(row["amount"])})


async def handle_event(event_type: str, payload: dict):
    if event_type == "ScenarioChanged":
        if payload["scenario"] in scenario_flags:
            scenario_flags[payload["scenario"]] = payload["enabled"]
        return
    order_id = payload["order_id"]
    transitions = {"PaymentAuthorized": "DISPATCHING", "PaymentFailed": "FAILED", "DriverAssigned": "OUT_FOR_DELIVERY", "DeliveryCompleted": "DELIVERED", "DeliveryDelayed": "DISPATCHING"}
    status = transitions.get(event_type)
    if status:
        await db.execute("UPDATE orders SET status=$1, driver_id=COALESCE($2, driver_id), completed_at=CASE WHEN $1='DELIVERED' THEN now() ELSE completed_at END WHERE id=$3", status, payload.get("driver_id"), order_id)
        metric = {
            "PaymentAuthorized": "parcelplus.orders.payment_authorized",
            "PaymentFailed": "parcelplus.orders.failed",
            "DriverAssigned": "parcelplus.orders.out_for_delivery",
            "DeliveryCompleted": "parcelplus.orders.delivered",
            "DeliveryDelayed": "parcelplus.orders.delayed",
        }.get(event_type)
        if metric:
            increment(metric, attributes={"region": payload.get("region", "unknown"), "priority": payload.get("priority", "unknown"), "status": status})
        event_log("order_status_changed", order_id=order_id, status=status, correlation_id=payload.get("correlation_id", "-"))


app = create_app("ParcelPulse Order Service", startup)


@app.post("/orders", status_code=201)
async def create_order(payload: OrderCreate):
    if scenario_flags["database_latency"]:
        await asyncio.sleep(0.75)
    if scenario_flags["high_cpu_processing"]:
        started = time.perf_counter()
        while time.perf_counter() - started < 0.2:
            _ = sum(index * index for index in range(2_000))
        observe("parcelplus.order.cpu_work_seconds", time.perf_counter() - started)
    order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
    created_at = datetime.now(timezone.utc)
    await db.execute("INSERT INTO orders (id, customer_id, region, priority, payment_method, amount, status, created_at) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)", order_id, payload.customer_id, payload.region, payload.priority, payload.payment_method, payload.amount, "PAYMENT_PENDING", created_at)
    await publish("OrderCreated", {"order_id": order_id, **payload.model_dump(), "created_at": created_at.isoformat()})
    increment("parcelplus.orders.created", attributes={"region": payload.region, "priority": payload.priority, "status": "PAYMENT_PENDING"})
    event_log("order_created", order_id=order_id, customer_id=payload.customer_id, amount=payload.amount)
    return {"id": order_id, **payload.model_dump(), "status": "PAYMENT_PENDING", "created_at": created_at}


@app.get("/orders")
async def list_orders(limit: int = 100):
    rows = await db.fetch("SELECT * FROM orders ORDER BY created_at DESC LIMIT $1", max(1, min(limit, 500)))
    return [dict(row) for row in rows]


@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    row = await db.fetchrow("SELECT * FROM orders WHERE id=$1", order_id)
    if not row:
        raise HTTPException(404, "Order not found")
    return dict(row)
