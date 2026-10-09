import time
import uuid
import logging
from contextlib import asynccontextmanager
from contextvars import ContextVar

from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from .config import ENVIRONMENT, OTEL_ENABLED, OTEL_EXPORTER_OTLP_ENDPOINT, OTEL_SERVICE_NAME, SERVICE_NAME
from .db import close, connect
from .telemetry import configure_otel_metrics, event_log

requests = Counter("parcelpulse_service_requests_total", "Service requests", ["service", "method", "path", "status"])
latency = Histogram("parcelpulse_service_request_duration_seconds", "Service request latency", ["service", "path"])
correlation_id_context: ContextVar[str] = ContextVar("correlation_id", default="-")


def create_app(title: str, startup=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await connect()
        if startup:
            await startup()
        yield
        await close()

    app = FastAPI(title=title, version="1.0.0", lifespan=lifespan)

    if OTEL_ENABLED:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create({"service.name": OTEL_SERVICE_NAME, "deployment.environment": ENVIRONMENT}))
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=OTEL_EXPORTER_OTLP_ENDPOINT.rstrip("/") + "/v1/traces")))
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)
        try:
            from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
            HTTPXClientInstrumentor().instrument()
        except ImportError:
            logging.getLogger("parcelpulse").warning("httpx OpenTelemetry instrumentation is unavailable")

    configure_otel_metrics()

    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        started = time.perf_counter()
        correlation_id = request.headers.get("x-correlation-id") or f"corr-{uuid.uuid4().hex[:12]}"
        token = correlation_id_context.set(correlation_id)
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        path = request.scope.get("route").path if request.scope.get("route") else request.url.path
        elapsed = time.perf_counter() - started
        requests.labels(SERVICE_NAME, request.method, path, str(response.status_code)).inc()
        latency.labels(SERVICE_NAME, path).observe(elapsed)
        response.headers["x-correlation-id"] = correlation_id
        event_log("http_request", method=request.method, path=path, status=response.status_code, duration_ms=round(elapsed * 1000, 2), correlation_id=correlation_id)
        correlation_id_context.reset(token)
        return response

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": SERVICE_NAME, "environment": ENVIRONMENT}

    @app.get("/metrics")
    async def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app
