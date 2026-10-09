"""Small, dependency-light observability helpers shared by every service.

The application keeps Prometheus metrics for local development and exposes an
optional OTLP metrics pipeline for Dynatrace.  OTLP is disabled by default so
the existing Docker and test workflows continue to work without credentials.
"""

from __future__ import annotations

import logging
import json
from datetime import datetime, timezone
from typing import Any

from prometheus_client import Counter, Gauge, Histogram

from .config import ENVIRONMENT, OTEL_ENABLED, SERVICE_NAME

logger = logging.getLogger("parcelpulse")
logger.setLevel(logging.INFO)

_prom_counters: dict[str, Counter] = {}
_prom_histograms: dict[str, Histogram] = {}
_prom_gauges: dict[str, Gauge] = {}
_otel_meter = None
_otel_instruments: dict[tuple[str, str], Any] = {}
_DIMENSIONS = ("service", "environment", "region", "priority", "scenario", "status", "event")


def configure_otel_metrics() -> None:
    """Configure OTLP metrics only when explicitly enabled."""
    global _otel_meter
    if not OTEL_ENABLED or _otel_meter is not None:
        return

    from opentelemetry import metrics
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource

    from .config import OTEL_EXPORTER_OTLP_ENDPOINT

    exporter = OTLPMetricExporter(
        endpoint=OTEL_EXPORTER_OTLP_ENDPOINT.rstrip("/") + "/v1/metrics"
    )
    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=10_000)
    provider = MeterProvider(
        resource=Resource.create(
            {
                "service.name": SERVICE_NAME,
                "deployment.environment": ENVIRONMENT,
                "application.name": "parcelplus",
            }
        ),
        metric_readers=[reader],
    )
    metrics.set_meter_provider(provider)
    _otel_meter = provider.get_meter("parcelplus", "1.0.0")

    # Send the same structured application records as OTLP logs. Console
    # logging remains enabled through Uvicorn's normal logging handlers.
    try:
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

        log_provider = LoggerProvider(resource=Resource.create({
            "service.name": SERVICE_NAME,
            "deployment.environment": ENVIRONMENT,
            "application.name": "parcelplus",
        }))
        log_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter(endpoint=OTEL_EXPORTER_OTLP_ENDPOINT.rstrip("/") + "/v1/logs")))
        otel_handler = LoggingHandler(level=logging.INFO, logger_provider=log_provider)
        logger.addHandler(otel_handler)
    except ImportError:
        logger.warning("OTLP log export is unavailable; structured stdout logs remain enabled")


def _metric_key(name: str) -> str:
    return name.replace("-", "_").replace(".", "_")


def increment(name: str, value: float = 1, attributes: dict[str, Any] | None = None) -> None:
    """Increment a business counter in Prometheus and, when enabled, OTLP."""
    attrs = _attributes(attributes)
    key = _metric_key(name)
    counter = _prom_counters.get(key)
    if counter is None:
        counter = Counter(key, f"ParcelPlus {name}", list(_DIMENSIONS))
        _prom_counters[key] = counter
    counter.labels(**attrs).inc(value)

    if _otel_meter:
        instrument = _otel_instruments.get(("counter", name))
        if instrument is None:
            instrument = _otel_meter.create_counter(name, description=f"ParcelPlus {name}")
            _otel_instruments[("counter", name)] = instrument
        instrument.add(value, attrs)


def observe(name: str, value: float, attributes: dict[str, Any] | None = None) -> None:
    attrs = _attributes(attributes)
    key = _metric_key(name)
    histogram = _prom_histograms.get(key)
    if histogram is None:
        histogram = Histogram(key, f"ParcelPlus {name}", list(_DIMENSIONS))
        _prom_histograms[key] = histogram
    histogram.labels(**attrs).observe(value)

    if _otel_meter:
        instrument = _otel_instruments.get(("histogram", name))
        if instrument is None:
            instrument = _otel_meter.create_histogram(name, description=f"ParcelPlus {name}")
            _otel_instruments[("histogram", name)] = instrument
        instrument.record(value, attrs)


def set_gauge(name: str, value: float, attributes: dict[str, Any] | None = None) -> None:
    attrs = _attributes(attributes)
    key = _metric_key(name)
    gauge = _prom_gauges.get(key)
    if gauge is None:
        gauge = Gauge(key, f"ParcelPlus {name}", list(_DIMENSIONS))
        _prom_gauges[key] = gauge
    gauge.labels(**attrs).set(value)

    if _otel_meter:
        instrument = _otel_instruments.get(("gauge", name))
        if instrument is None:
            instrument = _otel_meter.create_up_down_counter(name, description=f"ParcelPlus {name}")
            _otel_instruments[("gauge", name)] = instrument
        instrument.add(value, attrs)


def _attributes(attributes: dict[str, Any] | None) -> dict[str, str]:
    values = {"service": SERVICE_NAME, "environment": ENVIRONMENT}
    for dimension in _DIMENSIONS[2:]:
        values[dimension] = str((attributes or {}).get(dimension, "unknown"))
    return values


def event_log(event: str, **fields: Any) -> None:
    """Emit one JSON log record without requiring a logging framework."""
    logger.info(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "service": SERVICE_NAME,
        "environment": ENVIRONMENT,
        **fields,
    }, default=str))
