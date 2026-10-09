from collections import Counter
from datetime import datetime, timezone
from threading import Lock

from .models import Order


class InMemoryStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self.orders: dict[str, Order] = {}
        self.scenarios: dict[str, bool] = {
            "payment_slowdown": False,
            "payment_failure_spike": False,
            "driver_shortage": False,
            "notification_outage": False,
            "database_latency": False,
            "high_cpu_processing": False,
        }
        self.drivers_by_region: dict[str, int] = {
            "north": 8,
            "central": 12,
            "south": 7,
            "east": 9,
            "west": 6,
        }

    def add_order(self, order: Order) -> Order:
        with self._lock:
            self.orders[order.id] = order
        return order

    def update_order(self, order: Order) -> Order:
        with self._lock:
            self.orders[order.id] = order
        return order

    def list_orders(self) -> list[Order]:
        with self._lock:
            return list(self.orders.values())

    def set_scenario(self, name: str, enabled: bool) -> None:
        with self._lock:
            self.scenarios[name] = enabled

    def snapshot(self) -> tuple[list[Order], dict[str, bool], dict[str, int]]:
        with self._lock:
            return list(self.orders.values()), dict(self.scenarios), dict(self.drivers_by_region)


store = InMemoryStore()

