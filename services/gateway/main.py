import os

import httpx
from fastapi import FastAPI, Request, Response

from shared.web import create_app

ORDER_URL = os.getenv("ORDER_SERVICE_URL", "http://localhost:8001")
CUSTOMER_URL = os.getenv("CUSTOMER_SERVICE_URL", "http://localhost:8002")
ANALYTICS_URL = os.getenv("ANALYTICS_SERVICE_URL", "http://localhost:8007")
SCENARIO_URL = os.getenv("SCENARIO_SERVICE_URL", "http://localhost:8008")

app = create_app("ParcelPulse API Gateway")


async def proxy(request: Request, target: str, path: str) -> Response:
    body = await request.body()
    async with httpx.AsyncClient(timeout=15) as client:
        upstream = await client.request(request.method, f"{target}{path}", content=body, params=request.query_params, headers={"content-type": request.headers.get("content-type", "application/json"), "x-correlation-id": request.state.correlation_id})
    return Response(content=upstream.content, status_code=upstream.status_code, headers={"content-type": upstream.headers.get("content-type", "application/json")})


@app.api_route("/api/orders", methods=["GET", "POST"])
async def orders(request: Request):
    return await proxy(request, ORDER_URL, "/orders")


@app.api_route("/api/orders/{order_id}", methods=["GET"])
async def order(request: Request, order_id: str):
    return await proxy(request, ORDER_URL, f"/orders/{order_id}")


@app.api_route("/api/customers", methods=["GET", "POST"])
async def customers(request: Request):
    return await proxy(request, CUSTOMER_URL, "/customers")


@app.api_route("/api/customers/{customer_id}", methods=["GET"])
async def customer(request: Request, customer_id: str):
    return await proxy(request, CUSTOMER_URL, f"/customers/{customer_id}")


@app.api_route("/api/analytics/overview", methods=["GET"])
async def analytics(request: Request):
    return await proxy(request, ANALYTICS_URL, "/analytics/overview")


@app.api_route("/api/scenarios", methods=["GET"])
async def scenarios(request: Request):
    return await proxy(request, SCENARIO_URL, "/scenarios")


@app.api_route("/api/scenarios/reset", methods=["POST"])
async def reset_scenarios(request: Request):
    return await proxy(request, SCENARIO_URL, "/scenarios/reset")


@app.api_route("/api/scenarios/{name}", methods=["PUT"])
async def scenario(request: Request, name: str):
    return await proxy(request, SCENARIO_URL, f"/scenarios/{name}")
