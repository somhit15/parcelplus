# ParcelPlus architecture

## Purpose

ParcelPlus is a realistic delivery workflow used as a reference workload for Dynatrace observability. It is not intended to be a production carrier platform. Its purpose is to make business journeys and failure impact visible across a microservice system.

## Runtime components

### Frontend

The React/Vite frontend provides parcel creation, tracking lookup, customer selection and creation, KPI overview, service health, and failure-scenario controls. It calls only the API Gateway.

### API Gateway

The gateway is the public backend boundary. It routes requests to Order, Customer, Analytics, and Scenario services and forwards the request correlation ID. It is the natural starting point for an end-to-end HTTP trace.

### Order Service

Owns the order lifecycle and `orders` table. It creates orders in `PAYMENT_PENDING`, publishes `OrderCreated`, and responds to payment, dispatch, delay, and completion events.

### Customer Service

Owns customer profiles and the `customers` table. It provides customer creation, listing, and lookup for the frontend and order flow.

### Payment Service

Consumes `OrderCreated`, simulates authorization latency and failures, owns the `payments` table, and publishes `PaymentAuthorized` or `PaymentFailed`.

### Dispatch Service

Consumes payment and retry events, owns driver capacity in the `drivers` table, assigns a driver, and publishes `DriverAssigned`. Driver shortage produces `DeliveryDelayed`.

### Tracking Service

Consumes `DriverAssigned`, owns tracking records, simulates a short delivery journey, and publishes `DeliveryStarted` and `DeliveryCompleted`.

### Notification Service

Consumes workflow events and records notification outcomes in the `notifications` table. The notification outage scenario changes successful sends into failed sends.

### Analytics Service

Consumes business events and maintains aggregate KPI values in the `kpis` table. The frontend reads the overview endpoint, while Dynatrace receives service and business telemetry directly from the services.

### Scenario Service

Owns enabled failure scenarios in the `scenarios` table. Changes are persisted and broadcast as `ScenarioChanged` events so participating services can change behavior without direct service coupling.

## Event flow

```text
OrderCreated
    ├── Payment Service
    ├── Notification Service
    └── Analytics Service

PaymentAuthorized
    ├── Order Service
    └── Dispatch Service

DriverAssigned
    ├── Order Service
    ├── Tracking Service
    └── Notification Service

DeliveryCompleted
    ├── Order Service
    ├── Dispatch Service
    ├── Notification Service
    └── Analytics Service
```

Every event includes metadata for the producing service, correlation ID, and OpenTelemetry trace context when tracing is enabled. Existing event payload fields remain compatible with service handlers.

## Data ownership

The local demonstration uses one PostgreSQL instance with service-owned tables:

```text
orders, customers, payments, drivers,
tracking, notifications, kpis, scenarios
```

This keeps local setup simple. The service boundaries do not depend on a shared application query model and can later move to separate databases without changing event contracts.

## Observability design

Each service exposes `/health` and `/metrics`, request counters and latency histograms, business counters and histograms, and structured JSON event logs.

When `OTEL_ENABLED=true`, services configure OTLP exporters:

```text
FastAPI services → OpenTelemetry SDKs → OpenTelemetry Collector → Dynatrace
```

The Collector is placed behind a Compose profile so credentials are never required for a normal local run.

## Design principles

1. Keep existing service boundaries stable.
2. Use events for workflow transitions, not direct cross-service database access.
3. Keep Dynatrace credentials outside source control.
4. Use stable service names and environment metadata.
5. Keep business metric dimensions bounded; do not use order IDs as metric dimensions.
6. Make failure scenarios deterministic and reversible.
7. Keep telemetry optional so local development remains simple.
