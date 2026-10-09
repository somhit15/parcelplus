# ParcelPlus

ParcelPlus is a containerized delivery-operations application built to demonstrate application observability with Dynatrace. It simulates a customer journey: a customer places an order, payment is authorized, a driver is assigned, the parcel is tracked, delivery completes, and notifications are recorded.

The project is split into FastAPI services so it can produce distributed traces, business metrics, structured events, database activity, messaging activity, and controlled failure signals.

## What this repository provides

- React/Vite customer and operations web interface
- FastAPI microservices behind an API gateway
- PostgreSQL persistence
- RabbitMQ event-driven workflow
- Business KPI and operational metrics
- Correlation IDs and trace context across HTTP and RabbitMQ
- Optional OpenTelemetry export for traces, metrics, and logs
- Dynatrace OpenTelemetry Collector configuration
- Controlled scenarios for demonstrating impact and recovery

The application is the telemetry-producing workload. Dynatrace dashboards, SLOs, alerts, and dashboard-as-code deployment are the observability layer built on top of it.

## Architecture

```text
React frontend → API Gateway → Order / Customer / Analytics / Scenario services
                                    |
                                    v
                              RabbitMQ events
                                    |
                    Payment → Dispatch → Tracking → Notification

All services → PostgreSQL
All services → optional OpenTelemetry Collector → Dynatrace
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for service responsibilities, event contracts, data ownership, and request flows.

## Components

| Component | Responsibility | Port |
|---|---|---:|
| Frontend | Customer shipping/tracking experience and operations workspace | 3000 |
| Gateway | Public API entry point and routing | 8000 |
| Order Service | Order lifecycle and order events | 8001 |
| Customer Service | Customer profiles | 8002 |
| Payment Service | Simulated payment authorization and failure scenarios | 8003 |
| Dispatch Service | Driver capacity and assignment | 8004 |
| Tracking Service | Simulated delivery movement and completion | 8005 |
| Notification Service | Notification event recording and outage simulation | 8006 |
| Analytics Service | Business KPI aggregation | 8007 |
| Scenario Service | Failure-injection controls | 8008 |
| PostgreSQL | Durable service-owned data | 5432 |
| RabbitMQ | Asynchronous workflow events and management UI | 5672 / 15672 |

## Run locally with Docker

Requirements: Docker Desktop with Docker Compose.

```bash
docker compose up --build -d
```

Open the website at <http://localhost:3000>, API documentation at <http://localhost:8000/docs>, and RabbitMQ management at <http://localhost:15672> using `parcelpulse` / `parcelpulse`.

Create a test order:

```bash
curl -X POST http://localhost:8000/api/orders \
  -H 'content-type: application/json' \
  -d '{"customer_id":"customer-100","region":"central","priority":"express","payment_method":"card","amount":42.50}'
```

The order is processed asynchronously and normally becomes `DELIVERED` within a few seconds.

Useful endpoints include `/health`, `/metrics`, `/api/orders`, `/api/customers`, `/api/analytics/overview`, `/api/scenarios`, and `/api/scenarios/reset`.

## Demonstrate failure impact

Enable payment slowdown:

```bash
curl -X PUT http://localhost:8000/api/scenarios/payment_slowdown \
  -H 'content-type: application/json' \
  -d '{"enabled":true}'
```

Other scenarios are `payment_failure_spike`, `driver_shortage`, `notification_outage`, `database_latency`, and `high_cpu_processing`. Reset all scenarios with:

```bash
curl -X POST http://localhost:8000/api/scenarios/reset
```

## Dynatrace integration

Telemetry export is opt-in. Local development works without a Dynatrace account or token.

```bash
cp .env.example .env
```

Set `DT_ENDPOINT` and `DT_API_TOKEN` in `.env`, then run:

```bash
OTEL_ENABLED=true docker compose --profile observability up --build -d
```

The application services send OTLP data to the Collector at `http://otel-collector:4318`. The Collector forwards traces, metrics, and logs to Dynatrace. Keep tokens in `.env`, CI/CD secrets, or a secret manager; never commit them.

Read [docs/DYNATRACE_INTEGRATION.md](docs/DYNATRACE_INTEGRATION.md) for the telemetry model, token requirements, recommended dashboards, SLOs, validation steps, and GitOps deployment plan.

## Repository layout

```text
services/                  FastAPI microservices
shared/                    Database, events, web, telemetry helpers
frontend/                  React/Vite frontend
otel-collector-config.yaml Dynatrace Collector pipeline
docker-compose.yml         Local multi-container environment
docs/                      Architecture and integration documentation
tests/                     Application tests
```

## Development checks

Inside a Python environment with the dependencies installed:

```bash
python -m compileall -q shared services
python -m pytest -q
```

Docker remains the supported way to run the complete application because it supplies PostgreSQL, RabbitMQ, the microservices, and the frontend together.

## Project status

The ParcelPlus application and telemetry foundation are implemented. The next layer is the Dynatrace dashboard factory: dashboard JSON templates, SLO/alert definitions, validation rules, and GitLab/Monaco deployment automation.
