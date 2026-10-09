import asyncio

from shared import db
from shared.events import consume, publish
from shared.web import create_app
from shared.telemetry import increment, observe, event_log


async def startup():
    await db.execute("CREATE TABLE IF NOT EXISTS tracking (order_id text primary key, driver_id text, started_at timestamptz, completed_at timestamptz)")
    asyncio.create_task(consume("tracking-service", ["DriverAssigned"], handle_event))


async def handle_event(_: str, payload: dict):
    started = asyncio.get_running_loop().time()
    await db.execute("INSERT INTO tracking (order_id, driver_id, started_at) VALUES ($1,$2,now()) ON CONFLICT (order_id) DO UPDATE SET driver_id=EXCLUDED.driver_id", payload["order_id"], payload["driver_id"])
    await publish("DeliveryStarted", payload)
    increment("parcelplus.deliveries.started", attributes={"region": payload.get("region", "central"), "status": "IN_TRANSIT"})
    await asyncio.sleep(2)
    await db.execute("UPDATE tracking SET completed_at=now() WHERE order_id=$1", payload["order_id"])
    await publish("DeliveryCompleted", payload)
    duration = asyncio.get_running_loop().time() - started
    increment("parcelplus.deliveries.completed", attributes={"region": payload.get("region", "central"), "status": "DELIVERED"})
    observe("parcelplus.delivery.duration_seconds", duration, attributes={"region": payload.get("region", "central"), "status": "DELIVERED"})
    event_log("delivery_completed", order_id=payload["order_id"], duration_seconds=round(duration, 2))


app = create_app("ParcelPulse Tracking Service", startup)
