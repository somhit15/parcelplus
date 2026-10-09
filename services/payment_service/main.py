import asyncio
import os
import random
import time

from shared import db
from shared.events import consume, publish
from shared.web import create_app
from shared.telemetry import increment, observe, event_log

failure_rate = float(os.getenv("PAYMENT_FAILURE_RATE", "0.03"))
scenarios: dict[str, bool] = {"payment_slowdown": False, "payment_failure_spike": False}


async def startup():
    await db.execute("CREATE TABLE IF NOT EXISTS payments (id bigserial primary key, order_id text unique not null, amount numeric not null, status text not null, latency_ms numeric, created_at timestamptz default now())")
    asyncio.create_task(consume("payment-service", ["OrderCreated", "ScenarioChanged"], handle_event))


async def handle_event(event_type: str, payload: dict):
    if event_type == "ScenarioChanged":
        if payload["scenario"] in scenarios:
            scenarios[payload["scenario"]] = payload["enabled"]
        return
    delay = 1.5 if scenarios["payment_slowdown"] else 0.05
    started = time.perf_counter()
    await asyncio.sleep(delay)
    success = random.random() >= failure_rate * (8 if scenarios["payment_failure_spike"] else 1)
    status = "AUTHORIZED" if success else "FAILED"
    latency_ms = (time.perf_counter() - started) * 1000
    await db.execute("INSERT INTO payments (order_id, amount, status, latency_ms) VALUES ($1,$2,$3,$4) ON CONFLICT (order_id) DO UPDATE SET status=EXCLUDED.status, latency_ms=EXCLUDED.latency_ms", payload["order_id"], payload["amount"], status, latency_ms)
    await publish("PaymentAuthorized" if success else "PaymentFailed", {"order_id": payload["order_id"], "amount": payload["amount"], "payment_method": payload["payment_method"], "region": payload.get("region", "central"), "priority": payload.get("priority", "standard")})
    attributes = {"region": payload.get("region", "central"), "priority": payload.get("priority", "standard"), "status": status}
    increment("parcelplus.payments.processed", attributes=attributes)
    increment("parcelplus.payments.authorized" if success else "parcelplus.payments.failed", attributes=attributes)
    observe("parcelplus.payment.latency_ms", latency_ms, attributes=attributes)
    event_log("payment_processed", order_id=payload["order_id"], status=status, latency_ms=round(latency_ms, 2))


app = create_app("ParcelPulse Payment Service", startup)


@app.get("/payments/{order_id}")
async def get_payment(order_id: str):
    row = await db.fetchrow("SELECT * FROM payments WHERE order_id=$1", order_id)
    return dict(row) if row else {"order_id": order_id, "status": "PENDING"}
