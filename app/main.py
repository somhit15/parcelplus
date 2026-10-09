import asyncio
import random
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from logging import getLogger

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware

from .config import get_settings
from .models import Order, OrderCreate, OrderStatus, ScenarioUpdate
from .observability import (
    correlation_id, configure_logging, deliveries_late, delivery_duration,
    drivers_available, event_log, http_request_latency, http_requests,
    orders_created, orders_failed, orders_waiting, orders_completed,
    payment_attempts, payment_latency, revenue_total, scenario_active,
    scenario_events, configure_tracing,
)
from .store import store

settings = get_settings()
configure_logging(settings)
configure_tracing(settings)
logger = getLogger("parcelpulse")


class RequestMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-correlation-id", f"corr-{uuid.uuid4().hex[:12]}")
        token = correlation_id.set(request_id)
        started = time.perf_counter()
        response = None
        try:
            response = await call_next(request)
            return response
        finally:
            elapsed = time.perf_counter() - started
            route = request.scope.get("route")
            route_name = getattr(route, "path", request.url.path)
            status = str(response.status_code if response else 500)
            http_request_latency.labels(request.method, route_name, status).observe(elapsed)
            http_requests.labels(request.method, route_name, status).inc()
            if response:
                response.headers["x-correlation-id"] = request_id
            correlation_id.reset(token)


def now() -> datetime:
    return datetime.now(timezone.utc)


async def authorize_payment(order: Order) -> bool:
    _, scenarios, _ = store.snapshot()
    delay = 0.05
    if scenarios["payment_slowdown"]:
        delay = 1.5
    if scenarios["database_latency"]:
        delay += 0.35
    started = time.perf_counter()
    await asyncio.sleep(delay)
    failure_rate = settings.payment_failure_rate * (8 if scenarios["payment_failure_spike"] else 1)
    success = random.random() >= failure_rate
    status = "success" if success else "failure"
    payment_latency.labels(status).observe(time.perf_counter() - started)
    payment_attempts.labels(status, order.payment_method).inc()
    return success


async def process_order(order: Order) -> Order:
    order.status = OrderStatus.PAYMENT_PENDING
    store.update_order(order)
    if not await authorize_payment(order):
        order.status = OrderStatus.FAILED
        store.update_order(order)
        orders_failed.labels(order.region, "payment_failed").inc()
        event_log(logger, "payment_failed", order_id=order.id, region=order.region, amount=order.amount)
        return order

    order.status = OrderStatus.PAID
    revenue_total.labels(order.region).inc(order.amount)
    order.status = OrderStatus.DISPATCHING
    _, scenarios, drivers = store.snapshot()
    available = 0 if scenarios["driver_shortage"] else drivers[order.region]
    if available < 1:
        orders_waiting.labels(order.region).inc()
        event_log(logger, "driver_unavailable", order_id=order.id, region=order.region)
        return store.update_order(order)
    await asyncio.sleep(0.03)
    order.driver_id = f"DRV-{random.randint(100, 999)}"
    order.status = OrderStatus.OUT_FOR_DELIVERY
    store.update_order(order)
    event_log(logger, "driver_assigned", order_id=order.id, driver_id=order.driver_id, region=order.region)
    return order


async def simulator() -> None:
    while True:
        if settings.order_simulator_enabled:
            await asyncio.sleep(settings.order_simulator_interval_seconds)
            sample = OrderCreate(customer_id="sim-customer", region=random.choice(["north", "central", "south", "east", "west"]), amount=round(random.uniform(12, 125), 2))
            await create_order(sample, simulated=True)
            for order in store.list_orders():
                if order.status == OrderStatus.OUT_FOR_DELIVERY and random.random() < 0.35:
                    order.status = OrderStatus.DELIVERED
                    order.completed_at = now()
                    order.actual_delivery_minutes = max(10, int(random.gauss(order.estimated_delivery_minutes, 12)))
                    delivery_duration.labels(order.region).observe(order.actual_delivery_minutes * 60)
                    if order.actual_delivery_minutes > order.estimated_delivery_minutes:
                        deliveries_late.labels(order.region).inc()
                        event_log(logger, "delivery_delayed", order_id=order.id, region=order.region, delay_minutes=order.actual_delivery_minutes - order.estimated_delivery_minutes)
                    else:
                        orders_completed.labels(order.region).inc()
                        event_log(logger, "delivery_completed", order_id=order.id, region=order.region)
                    store.update_order(order)
        else:
            await asyncio.sleep(60)


async def create_order(payload: OrderCreate, simulated: bool = False) -> Order:
    order = Order(id=f"ORD-{uuid.uuid4().hex[:8].upper()}", **payload.model_dump(), status=OrderStatus.CREATED, created_at=now())
    store.add_order(order)
    orders_created.labels(order.region, order.priority).inc()
    event_log(logger, "order_created", order_id=order.id, region=order.region, priority=order.priority, amount=order.amount, simulated=simulated)
    await process_order(order)
    return order


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(simulator())
    yield
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


app = FastAPI(title="ParcelPulse API", version="1.0.0", description="Delivery operations telemetry demo for Dynatrace", lifespan=lifespan)
if settings.otel_enabled:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    FastAPIInstrumentor.instrument_app(app)
app.add_middleware(RequestMetricsMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health", tags=["system"])
def health() -> dict:
    return {"status": "ok", "service": settings.otel_service_name, "environment": settings.app_env}


@app.get("/metrics", tags=["observability"])
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/api/orders", response_model=Order, status_code=201, tags=["orders"])
async def create_order_endpoint(payload: OrderCreate) -> Order:
    return await create_order(payload)


@app.get("/api/orders", response_model=list[Order], tags=["orders"])
def list_orders(limit: int = 100) -> list[Order]:
    return store.list_orders()[:max(1, min(limit, 500))]


@app.get("/api/orders/{order_id}", response_model=Order, tags=["orders"])
def get_order(order_id: str) -> Order:
    order = next((item for item in store.list_orders() if item.id == order_id), None)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@app.get("/api/analytics/overview", tags=["analytics"])
def analytics_overview() -> dict:
    orders, scenarios, drivers = store.snapshot()
    total = len(orders)
    completed = sum(order.status == OrderStatus.DELIVERED for order in orders)
    failed = sum(order.status == OrderStatus.FAILED for order in orders)
    paid = sum(order.status in {OrderStatus.PAID, OrderStatus.DISPATCHING, OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED} for order in orders)
    delivered = [order for order in orders if order.status == OrderStatus.DELIVERED and order.actual_delivery_minutes]
    on_time = sum(order.actual_delivery_minutes <= order.estimated_delivery_minutes for order in delivered)
    revenue = sum(order.amount for order in orders if order.status != OrderStatus.FAILED)
    by_region = {region: sum(order.region == region for order in orders) for region in drivers}
    return {
        "generated_at": now(), "orders_total": total, "orders_completed": completed,
        "orders_failed": failed, "order_completion_rate": round(completed / total, 4) if total else 0,
        "payment_conversion_rate": round(paid / total, 4) if total else 0,
        "on_time_delivery_rate": round(on_time / len(delivered), 4) if delivered else 0,
        "revenue": round(revenue, 2), "average_order_value": round(revenue / total, 2) if total else 0,
        "active_deliveries": sum(order.status == OrderStatus.OUT_FOR_DELIVERY for order in orders),
        "available_drivers_by_region": drivers, "orders_by_region": by_region,
        "active_scenarios": [name for name, enabled in scenarios.items() if enabled],
    }


@app.get("/api/analytics/service-health", tags=["analytics"])
def service_health() -> dict:
    _, scenarios, drivers = store.snapshot()
    return {"services": {name: {"status": "degraded" if enabled else "healthy", "active_scenario": name if enabled else None} for name, enabled in scenarios.items()}, "driver_capacity": drivers}


@app.get("/api/scenarios", tags=["scenarios"])
def get_scenarios() -> dict[str, bool]:
    return store.snapshot()[1]


@app.put("/api/scenarios/{scenario_name}", tags=["scenarios"])
def update_scenario(scenario_name: str, payload: ScenarioUpdate) -> dict:
    if scenario_name not in store.snapshot()[1]:
        raise HTTPException(status_code=404, detail="Unknown scenario")
    store.set_scenario(scenario_name, payload.enabled)
    scenario_active.labels(scenario_name).set(1 if payload.enabled else 0)
    scenario_events.labels(scenario_name, "enabled" if payload.enabled else "disabled").inc()
    event_log(logger, "scenario_enabled" if payload.enabled else "scenario_disabled", scenario=scenario_name)
    return {"scenario": scenario_name, "enabled": payload.enabled}


@app.post("/api/scenarios/reset", tags=["scenarios"])
def reset_scenarios() -> dict:
    for name in store.snapshot()[1]:
        store.set_scenario(name, False)
        scenario_active.labels(name).set(0)
    event_log(logger, "scenarios_reset")
    return store.snapshot()[1]


for region, count in store.drivers_by_region.items():
    drivers_available.labels(region).set(count)
