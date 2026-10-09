import asyncio
import os
import random

from shared import db
from shared.events import consume, publish
from shared.web import create_app
from shared.telemetry import increment, set_gauge, event_log

shortage = False


async def startup():
    await db.execute("CREATE TABLE IF NOT EXISTS drivers (id text primary key, region text not null, available boolean default true)")
    for region, count in {"north": 8, "central": 12, "south": 7, "east": 9, "west": 6}.items():
        for index in range(count):
            await db.execute("INSERT INTO drivers (id, region) VALUES ($1,$2) ON CONFLICT DO NOTHING", f"DRV-{region[:2].upper()}-{index:03d}", region)
    # Reconcile capacity on service restart. Completed deliveries release
    # drivers during normal operation; this also repairs state from older runs.
    await db.execute("UPDATE drivers SET available=true")
    asyncio.create_task(consume("dispatch-service", ["PaymentAuthorized", "DispatchRetryRequested", "DeliveryDelayed", "DeliveryCompleted", "ScenarioChanged"], handle_event))


async def handle_event(event_type: str, payload: dict):
    global shortage
    if event_type == "ScenarioChanged":
        if payload["scenario"] == "driver_shortage":
            shortage = payload["enabled"]
        return
    if event_type == "DeliveryCompleted":
        if payload.get("driver_id"):
            await db.execute("UPDATE drivers SET available=true WHERE id=$1", payload["driver_id"])
        return
    if event_type == "DeliveryDelayed":
        if shortage:
            return
        await asyncio.sleep(1)
    driver = None if shortage else await db.fetchrow("SELECT * FROM drivers WHERE region=$1 AND available=true LIMIT 1", payload.get("region", "central"))
    if not driver:
        await publish("DeliveryDelayed", {"order_id": payload["order_id"], "region": payload.get("region", "central"), "reason": "no_drivers"})
        increment("parcelplus.dispatch.delayed", attributes={"region": payload.get("region", "central"), "status": "NO_DRIVER"})
        event_log("dispatch_delayed", order_id=payload["order_id"], reason="no_drivers", region=payload.get("region", "central"))
        return
    await db.execute("UPDATE drivers SET available=false WHERE id=$1", driver["id"])
    await publish("DriverAssigned", {"order_id": payload["order_id"], "driver_id": driver["id"], "region": payload.get("region", "central")})
    increment("parcelplus.dispatch.assignments", attributes={"region": payload.get("region", "central"), "status": "ASSIGNED"})
    event_log("driver_assigned", order_id=payload["order_id"], driver_id=driver["id"], region=payload.get("region", "central"))


app = create_app("ParcelPulse Dispatch Service", startup)
