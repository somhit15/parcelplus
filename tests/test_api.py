from fastapi.testclient import TestClient

from app import main
from app.main import app


def test_health_and_metrics() -> None:
    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"
        assert "parcelpulse_orders_created_total" in client.get("/metrics").text


def test_order_flow_and_kpis() -> None:
    original_failure_rate = main.settings.payment_failure_rate
    main.settings.payment_failure_rate = 0
    with TestClient(app) as client:
        response = client.post("/api/orders", json={"customer_id": "cust-test", "region": "central", "amount": 25.5})
        assert response.status_code == 201
        order = response.json()
        assert order["id"].startswith("ORD-")
        overview = client.get("/api/analytics/overview").json()
        assert overview["orders_total"] >= 1
        assert overview["revenue"] >= 25.5
    main.settings.payment_failure_rate = original_failure_rate


def test_scenario_control() -> None:
    with TestClient(app) as client:
        response = client.put("/api/scenarios/driver_shortage", json={"enabled": True})
        assert response.json() == {"scenario": "driver_shortage", "enabled": True}
        assert client.get("/api/scenarios").json()["driver_shortage"] is True
        client.post("/api/scenarios/reset")
        assert client.get("/api/scenarios").json()["driver_shortage"] is False
