import asyncio

from shared import db
from shared.events import consume
from shared.web import create_app


async def startup():
    await db.execute("CREATE TABLE IF NOT EXISTS kpis (key text primary key, value numeric not null default 0, updated_at timestamptz default now())")
    for key in ["orders_created", "orders_completed", "orders_failed", "revenue", "late_deliveries"]:
        await db.execute("INSERT INTO kpis (key,value) VALUES ($1,0) ON CONFLICT DO NOTHING", key)
    asyncio.create_task(consume("analytics-service", ["OrderCreated", "PaymentFailed", "DeliveryCompleted", "DeliveryDelayed", "PaymentAuthorized"], handle_event))


async def increment(key: str, amount: float = 1):
    await db.execute("INSERT INTO kpis (key,value) VALUES ($1,$2) ON CONFLICT (key) DO UPDATE SET value=kpis.value+EXCLUDED.value, updated_at=now()", key, amount)


async def handle_event(event_type: str, payload: dict):
    if event_type == "OrderCreated":
        await increment("orders_created")
    elif event_type == "PaymentFailed":
        await increment("orders_failed")
    elif event_type == "PaymentAuthorized":
        await increment("revenue", float(payload["amount"]))
    elif event_type == "DeliveryCompleted":
        await increment("orders_completed")
    elif event_type == "DeliveryDelayed":
        await increment("late_deliveries")


app = create_app("ParcelPulse Analytics Service", startup)


@app.get("/analytics/overview")
async def overview():
    rows = await db.fetch("SELECT key,value FROM kpis")
    values = {row["key"]: float(row["value"]) for row in rows}
    created = values.get("orders_created", 0)
    return {**values, "order_completion_rate": round(values.get("orders_completed", 0) / created, 4) if created else 0, "payment_conversion_rate": round((created - values.get("orders_failed", 0)) / created, 4) if created else 0}

