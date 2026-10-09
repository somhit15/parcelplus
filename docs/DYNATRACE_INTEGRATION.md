# Dynatrace integration guide

## Integration model

ParcelPlus is the application being observed. Dynatrace receives traces, metrics, and structured logs:

```text
ParcelPlus activity → OpenTelemetry Collector → Dynatrace
```

The application does not require Dynatrace for its core workflow. This keeps the demo runnable locally and prevents an unavailable observability backend from blocking order processing.

## Configuration

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Configure:

```text
OTEL_ENABLED=true
DT_ENDPOINT=https://YOUR_ENVIRONMENT.live.dynatrace.com/api/v2/otlp
DT_API_TOKEN=<secret>
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
```

The application containers use the internal Collector address. `DT_ENDPOINT` is used only by the Collector to reach Dynatrace.

Start the stack:

```bash
OTEL_ENABLED=true docker compose --profile observability up --build -d
```

Generate activity:

```bash
curl -s -X POST http://localhost:8000/api/orders \
  -H 'content-type: application/json' \
  -d '{"customer_id":"dynatrace-demo","region":"central","priority":"express","payment_method":"card","amount":42.50}'
```

Then verify in Dynatrace that ParcelPlus services, distributed traces, metrics, and correlated logs are visible.

## Service identity

Each container sets a stable `SERVICE_NAME` and `APP_ENV`. These become OpenTelemetry resource attributes:

```text
service.name
deployment.environment
application.name=parcelplus
```

Stable identity is required for reusable dashboards across Demo, UAT, and Production environments.

## Recommended business metrics

| Metric | Meaning |
|---|---|
| `parcelplus.orders.created` | Orders accepted by Order Service |
| `parcelplus.orders.delivered` | Orders reaching delivery completion |
| `parcelplus.orders.failed` | Orders failing payment or workflow processing |
| `parcelplus.payments.authorized` | Successful authorizations |
| `parcelplus.payments.failed` | Failed authorizations |
| `parcelplus.payment.latency_ms` | Payment processing duration |
| `parcelplus.dispatch.assignments` | Successful driver assignments |
| `parcelplus.dispatch.delayed` | Orders delayed because capacity was unavailable |
| `parcelplus.delivery.duration_seconds` | Simulated delivery duration |
| `parcelplus.notifications.failed` | Failed notification outcomes |
| `parcelplus.events.published` | Events published to RabbitMQ |
| `parcelplus.events.consumed` | Events processed by consumers |

Supported dimensions are intentionally bounded: `service`, `environment`, `region`, `priority`, `scenario`, `status`, and `event`. Order IDs belong in traces and logs, not metric dimensions.

## Failure demonstration

Enable payment slowdown:

```bash
curl -X PUT http://localhost:8000/api/scenarios/payment_slowdown \
  -H 'content-type: application/json' \
  -d '{"enabled":true}'
```

Generate orders and observe increased payment latency, slower order completion, and the affected payment traces and histograms.

For driver shortage:

```bash
curl -X PUT http://localhost:8000/api/scenarios/driver_shortage \
  -H 'content-type: application/json' \
  -d '{"enabled":true}'
```

Observe dispatch delays, unassigned orders, and delivery impact. Reset before the next demonstration:

```bash
curl -X POST http://localhost:8000/api/scenarios/reset
```

## Initial dashboard set

1. ParcelPlus business overview
2. Customer order journey
3. Payment performance and conversion
4. Dispatch capacity and delivery risk
5. Notification and event processing
6. Service health and dependencies
7. SLO and failure-impact view

Start with one manually verified dashboard before introducing AI generation. This proves that the telemetry model and queries are correct.

## Initial SLO candidates

These are starting points for the Demo tenant and should be confirmed with the problem owner:

- Order API availability: 99.5%
- Payment authorization success: 99%
- 95% of payment authorizations under three seconds
- Delivery completion: 99%
- On-time delivery: 95%
- Notification processing success: 99%

## GitOps dashboard lifecycle

Dashboard definitions should eventually live in a separate observability repository or an `observability/` directory:

```text
observability/
├── dashboards/
├── slos/
├── alerts/
├── templates/
├── schemas/
└── validation/
```

Recommended pipeline:

```text
Request → generate dashboard JSON → validate → merge request
       → deploy to Demo → smoke verify → promote → rollback through Git
```

Monaco or the approved Dynatrace configuration-as-code tool should perform tenant deployment. ParcelPlus produces the data; the dashboard factory manages Dynatrace assets.

## Security notes

- Never commit `.env` or Dynatrace tokens.
- Use a CI/CD secret for deployment credentials.
- Use the least-privileged token scopes needed for ingestion and configuration deployment.
- Do not put customer or order identifiers into high-cardinality metric dimensions.
- Use synthetic demo data only.
