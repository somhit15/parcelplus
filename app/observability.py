import json
import logging
import sys
import time
from contextvars import ContextVar
from typing import Any

from prometheus_client import Counter, Gauge, Histogram

from .config import Settings

correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")

orders_created = Counter("parcelpulse_orders_created_total", "Orders created", ["region", "priority"])
orders_completed = Counter("parcelpulse_orders_completed_total", "Orders completed", ["region"])
orders_failed = Counter("parcelpulse_orders_failed_total", "Orders failed", ["region", "reason"])
payment_attempts = Counter("parcelpulse_payment_attempts_total", "Payment attempts", ["status", "method"])
payment_latency = Histogram("parcelpulse_payment_latency_seconds", "Payment authorization latency", ["status"])
revenue_total = Counter("parcelpulse_revenue_total", "Revenue from completed payments", ["region"])
drivers_available = Gauge("parcelpulse_active_drivers", "Available drivers", ["region"])
orders_waiting = Gauge("parcelpulse_orders_waiting_for_driver", "Orders waiting for driver", ["region"])
deliveries_late = Counter("parcelpulse_late_deliveries_total", "Late deliveries", ["region"])
delivery_duration = Histogram("parcelpulse_delivery_duration_seconds", "Delivery duration", ["region"])
scenario_active = Gauge("parcelpulse_scenario_active", "Whether a failure scenario is active", ["scenario"])
scenario_events = Counter("parcelpulse_scenario_events_total", "Scenario changes", ["scenario", "action"])
http_request_latency = Histogram("parcelpulse_http_request_duration_seconds", "HTTP request latency", ["method", "route", "status"])
http_requests = Counter("parcelpulse_http_requests_total", "HTTP requests", ["method", "route", "status"])


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": correlation_id.get(),
        }
        if hasattr(record, "event"):
            payload["event"] = record.event
        if hasattr(record, "data"):
            payload.update(record.data)
        return json.dumps(payload, default=str)


def configure_logging(settings: Settings) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())


def event_log(logger: logging.Logger, event: str, **data: Any) -> None:
    logger.info(event, extra={"event": event, "data": data})


def configure_tracing(settings: Settings) -> None:
    """Enable OTLP traces only when explicitly configured.

    Keeping this opt-in means local development never blocks on a collector,
    while Dynatrace deployments can export standard OpenTelemetry spans.
    """
    if not settings.otel_enabled:
        return
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({
        "service.name": settings.otel_service_name,
        "deployment.environment": settings.app_env,
    })
    provider = TracerProvider(resource=resource)
    endpoint = settings.otel_exporter_otlp_endpoint.rstrip("/") + "/v1/traces"
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
