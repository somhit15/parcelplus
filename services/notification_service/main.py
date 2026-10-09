import asyncio

from shared import db
from shared.events import consume
from shared.web import create_app
from shared.telemetry import increment, event_log

outage = False


async def startup():
    await db.execute("CREATE TABLE IF NOT EXISTS notifications (id bigserial primary key, order_id text, event_type text, status text, created_at timestamptz default now())")
    asyncio.create_task(consume("notification-service", ["OrderCreated", "PaymentFailed", "DriverAssigned", "DeliveryCompleted", "ScenarioChanged"], handle_event))


async def handle_event(event_type: str, payload: dict):
    global outage
    if event_type == "ScenarioChanged":
        if payload["scenario"] == "notification_outage":
            outage = payload["enabled"]
        return
    status = "FAILED" if outage else "SENT"
    await db.execute("INSERT INTO notifications (order_id, event_type, status) VALUES ($1,$2,$3)", payload.get("order_id"), event_type, status)
    increment("parcelplus.notifications.sent" if status == "SENT" else "parcelplus.notifications.failed", attributes={"event": event_type, "status": status})
    event_log("notification_processed", order_id=payload.get("order_id", "-"), notification_event=event_type, status=status)


app = create_app("ParcelPulse Notification Service", startup)
