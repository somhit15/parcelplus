from fastapi import HTTPException
from pydantic import BaseModel, Field

from shared import db
from shared.web import create_app
from shared.telemetry import increment, event_log


class Customer(BaseModel):
    name: str = Field(min_length=2)
    email: str


async def startup():
    await db.execute("CREATE TABLE IF NOT EXISTS customers (id text primary key, name text not null, email text not null, created_at timestamptz default now())")


app = create_app("ParcelPulse Customer Service", startup)


@app.post("/customers", status_code=201)
async def create_customer(payload: Customer):
    import uuid
    customer_id = f"CUS-{uuid.uuid4().hex[:8].upper()}"
    await db.execute("INSERT INTO customers (id,name,email) VALUES ($1,$2,$3)", customer_id, payload.name, payload.email)
    increment("parcelplus.customers.created", attributes={"status": "CREATED"})
    event_log("customer_created", customer_id=customer_id)
    return {"id": customer_id, **payload.model_dump()}


@app.get("/customers")
async def list_customers(limit: int = 100):
    rows = await db.fetch("SELECT * FROM customers ORDER BY created_at DESC LIMIT $1", max(1, min(limit, 500)))
    return [dict(row) for row in rows]


@app.get("/customers/{customer_id}")
async def get_customer(customer_id: str):
    row = await db.fetchrow("SELECT * FROM customers WHERE id=$1", customer_id)
    if not row:
        raise HTTPException(404, "Customer not found")
    return dict(row)
