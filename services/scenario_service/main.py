from fastapi import HTTPException
from pydantic import BaseModel

from shared import db
from shared.events import publish
from shared.web import create_app

SCENARIOS = ["payment_slowdown", "payment_failure_spike", "driver_shortage", "notification_outage", "database_latency", "high_cpu_processing"]


class ScenarioUpdate(BaseModel):
    enabled: bool


async def startup():
    await db.execute("CREATE TABLE IF NOT EXISTS scenarios (name text primary key, enabled boolean not null default false, updated_at timestamptz default now())")
    for name in SCENARIOS:
        await db.execute("INSERT INTO scenarios (name,enabled) VALUES ($1,false) ON CONFLICT DO NOTHING", name)


app = create_app("ParcelPulse Scenario Service", startup)


@app.get("/scenarios")
async def list_scenarios():
    rows = await db.fetch("SELECT name,enabled FROM scenarios ORDER BY name")
    return {row["name"]: row["enabled"] for row in rows}


@app.put("/scenarios/{name}")
async def update_scenario(name: str, payload: ScenarioUpdate):
    if name not in SCENARIOS:
        raise HTTPException(404, "Unknown scenario")
    await db.execute("UPDATE scenarios SET enabled=$1,updated_at=now() WHERE name=$2", payload.enabled, name)
    await publish("ScenarioChanged", {"scenario": name, "enabled": payload.enabled})
    return {"scenario": name, "enabled": payload.enabled}


@app.post("/scenarios/reset")
async def reset():
    await db.execute("UPDATE scenarios SET enabled=false,updated_at=now()")
    for name in SCENARIOS:
        await publish("ScenarioChanged", {"scenario": name, "enabled": False})
    return await list_scenarios()

