 ## Proposed app name: ParcelPulse

  “ParcelPulse” sounds professional, communicates real-time delivery operations, and fits well as a Dynatrace demo application.

  The project would live separately at:

  /Users/somnathdutta/dev/Hackathon/parcelpulse

  ## Product concept

  ParcelPulse is a delivery operations platform where customers place delivery orders, payments are processed, drivers are assigned, and delivery progress is tracked.

  The application continuously generates realistic operational activity and provides controls to inject failures such as payment delays, database slowness, unavailable drivers, and overloaded queues.

  The goal is to demonstrate the following via Dynatrace:

  - Business KPIs
  - Service health
  - Distributed traces
  - Logs
  - Custom metrics
  - Alerts
  - SLOs
  - Incident investigation
  - Failure impact on business operations

  ## Proposed architecture

                      React frontend
                            |
                            v
                      API Gateway
                            |
         +------------------+------------------+
         |                  |                  |
         v                  v                  v
    Order Service     Customer Service    Operations API
         |
         +---------- events via RabbitMQ --------+
         |                  |                    |
         v                  v                    v
   Payment Service   Dispatch Service     Notification Service
                            |
                            v
                     Tracking Service
                            |
                            v
                      Analytics Service

  Infrastructure:
  PostgreSQL | Redis | RabbitMQ | OpenTelemetry Collector

  All backend services would use FastAPI.

  ## Services

  ### 1. API Gateway

  Responsibilities:

  - Single public entry point
  - Request authentication
  - Routing to backend services
  - Correlation ID generation
  - Rate limiting
  - API documentation

  Example routes:

  /api/orders
  /api/customers
  /api/payments
  /api/deliveries
  /api/analytics
  /api/scenarios

  This service makes the application look like a normal production platform while keeping internal services private.

  ### 2. Order Service

  Responsibilities:

  - Create and update orders
  - Validate addresses and delivery details
  - Maintain order lifecycle
  - Publish order events

  Order states:

  CREATED
  PAYMENT_PENDING
  PAID
  DISPATCHING
  OUT_FOR_DELIVERY
  DELIVERED
  CANCELLED
  FAILED

  Important metrics:

  - Orders created
  - Orders completed
  - Order creation latency
  - Cancellation rate
  - Failed-order rate
  - Orders by region and priority

  ### 3. Customer Service

  Responsibilities:

  - Customer profiles
  - Addresses
  - Delivery preferences
  - Customer history

  This service gives us realistic database queries and customer-related traces without making the domain too complex.

  ### 4. Payment Service

  Responsibilities:

  - Authorize payments
  - Simulate an external payment provider
  - Retry failed payments
  - Publish payment success/failure events

  Failure scenarios:

  - Payment provider latency
  - Payment provider errors
  - Increased decline rate
  - Timeout during payment authorization

  Important metrics:

  - Payment success rate
  - Payment failure rate
  - Payment latency
  - Retry count
  - Payment amount
  - Revenue lost from failed payments

  ### 5. Dispatch Service

  Responsibilities:

  - Find available drivers
  - Assign drivers to orders
  - Manage delivery capacity
  - Estimate delivery times

  Failure scenarios:

  - No drivers available
  - Slow driver matching
  - Regional driver shortage
  - Dispatch worker crash

  Important metrics:

  - Available drivers
  - Orders awaiting dispatch
  - Dispatch latency
  - Average assignment time
  - Unassigned orders
  - Delivery estimate accuracy

  ### 6. Tracking Service

  Responsibilities:

  - Receive simulated driver location updates
  - Track delivery progress
  - Update estimated arrival time
  - Detect late deliveries

  A background simulator can generate driver movement every few seconds.

  Important metrics:

  - Active deliveries
  - Location updates per second
  - Late deliveries
  - Average delivery duration
  - Distance travelled
  - Tracking update delay

  ### 7. Notification Service

  Responsibilities:

  - Send simulated email/SMS/push notifications
  - Consume order and delivery events
  - Retry failed notifications

  Failure scenarios:

  - Notification provider unavailable
  - Slow notification delivery
  - Growing notification queue

  Important metrics:

  - Notifications sent
  - Notification failures
  - Notification queue size
  - Notification delivery latency
  - Retry count

  ### 8. Analytics Service

  Responsibilities:

  - Calculate business KPIs
  - Aggregate events
  - Provide dashboard data
  - Store daily and hourly summaries

  Example endpoints:

  GET /api/analytics/overview
  GET /api/analytics/orders
  GET /api/analytics/deliveries
  GET /api/analytics/revenue
  GET /api/analytics/service-health

  This service gives the frontend clean business-level data without querying operational databases directly.

  ### 9. Scenario Service

  Responsibilities:

  - Enable and disable failure scenarios
  - Store active scenarios
  - Expose a control panel to the frontend
  - Publish scenario state changes

  Example scenarios:

  payment_slowdown
  payment_failure_spike
  database_latency
  driver_shortage
  dispatch_worker_failure
  notification_outage
  tracking_backlog
  high_cpu_processing

  This service is particularly useful for Dynatrace demonstrations.

  ## Event-driven communication

  Services should communicate asynchronously through RabbitMQ for important workflow events.

  Example events:

  OrderCreated
  PaymentAuthorized
  PaymentFailed
  DriverAssigned
  DeliveryStarted
  DeliveryDelayed
  DeliveryCompleted
  NotificationFailed

  Example order flow:

  Order Service
       |
       | OrderCreated
       v
  Payment Service
       |
       | PaymentAuthorized
       v
  Dispatch Service
       |
       | DriverAssigned
       v
  Tracking Service
       |
       | DeliveryCompleted
       v
  Analytics Service

  Synchronous REST calls can still be used for queries and commands where immediate responses are required.

  ## Data storage

  For industry-style boundaries:

  - Each service owns its own database tables.
  - Services do not directly access another service’s tables.
  - RabbitMQ events are used to share state changes.
  - PostgreSQL is the primary database.
  - Redis is optional for caching and short-lived operational state.

  For local development, we can run one PostgreSQL container with separate databases or schemas. In a production deployment, these could be separated further.

  Suggested databases:

  parcelpulse_orders
  parcelpulse_customers
  parcelpulse_payments
  parcelpulse_dispatch
  parcelpulse_tracking
  parcelpulse_analytics

  ## Frontend

  Use React with Vite and TypeScript.

  Main screens:

  ### Operations overview

  - Orders per minute
  - Revenue
  - Delivery success rate
  - Average delivery time
  - Active deliveries
  - Current incidents

  ### Orders

  - Order list
  - Order details
  - Current status
  - Payment state
  - Assigned driver
  - Delivery timeline

  ### Live delivery map

  A simple map or simulated city grid showing:

  - Drivers
  - Active deliveries
  - Delayed orders
  - Regional problems

  ### Scenario control

  Buttons to enable and disable failures:

  Enable payment slowdown
  Enable driver shortage
  Enable notification outage
  Enable high CPU processing
  Reset all scenarios

  ### Service health

  - Request latency
  - Error rates
  - Queue sizes
  - Failed background jobs
  - Active scenarios

  ## Dynatrace observability design

  All services should use OpenTelemetry.

  ### Traces

  Every request should carry:

  - Trace ID
  - Span ID
  - Correlation ID
  - Order ID where applicable
  - Customer ID where applicable

  A checkout trace should look like:

  POST /orders
   ├── validate customer
   ├── reserve delivery capacity
   ├── authorize payment
   ├── publish OrderCreated
   └── create notification

  ### Metrics

  Use standard HTTP metrics plus custom business metrics.

  Examples:

  parcelpulse_orders_created_total
  parcelpulse_orders_completed_total
  parcelpulse_orders_failed_total
  parcelpulse_payment_failures_total
  parcelpulse_payment_latency_seconds
  parcelpulse_delivery_duration_seconds
  parcelpulse_late_deliveries_total
  parcelpulse_orders_waiting_for_driver
  parcelpulse_queue_age_seconds
  parcelpulse_revenue_total
  parcelpulse_active_drivers
  parcelpulse_notifications_failed_total

  Metrics should include useful dimensions such as:

  service
  region
  order_priority
  payment_method
  delivery_type
  failure_scenario

  Labels should be kept controlled to avoid creating excessive metric cardinality.

  ### Logs

  Use structured JSON logs containing fields such as:

  {
    "event": "delivery_delayed",
    "order_id": "ORD-10024",
    "region": "north",
    "delay_minutes": 18,
    "trace_id": "..."
  }

  Useful event types:

  - order_created
  - payment_failed
  - driver_assigned
  - delivery_delayed
  - notification_failed
  - scenario_enabled

  ### Business events

  Business events can represent meaningful customer and company activity:

  - Order placed
  - Payment completed
  - Order cancelled
  - Delivery completed
  - Delivery delayed
  - Revenue generated
  - Payment failed

  These can be used for business dashboards and conversion analysis.

  ## Important KPIs

  ### Business KPIs

  - Orders per minute
  - Order completion rate
  - Revenue per hour
  - Average order value
  - Payment conversion rate
  - Cancellation rate
  - On-time delivery percentage
  - Average delivery duration
  - Orders by geographic region

  ### Technical KPIs

  - Request throughput
  - Error rate
  - P50/P95/P99 latency
  - Queue depth
  - Queue processing age
  - Database latency
  - Worker failure rate
  - Retry count
  - CPU and memory usage

  ### Suggested SLOs

  99.5% of order requests complete successfully
  95% of payment requests finish within 1 second
  99% of completed orders are delivered successfully
  95% of deliveries arrive within the estimated window
  99% of notification events are processed within 30 seconds

  ## Example alerts

  Dynatrace dashboards and anomaly detection could highlight:

  - Payment failure rate above 5%
  - Order API P95 latency above 1 second
  - More than 10% late deliveries
  - Queue age above 2 minutes
  - No available drivers in a region
  - Notification failures above 3%
  - Database latency above 500 ms
  - CPU above 80%
  - Order completion rate below 95%

  A particularly useful demonstration would be:

  Payment slowdown enabled
          |
          v
  Payment latency increases
          |
          v
  Order requests become slower
          |
          v
  Payment queue grows
          |
          v
  Order completion rate drops
          |
          v
  Revenue decreases

  This shows both technical impact and business impact.

  ## Project structure

  A suitable repository structure would be:

  parcelpulse/
  ├── services/
  │   ├── api-gateway/
  │   ├── order-service/
  │   ├── customer-service/
  │   ├── payment-service/
  │   ├── dispatch-service/
  │   ├── tracking-service/
  │   ├── notification-service/
  │   ├── analytics-service/
  │   └── scenario-service/
  ├── frontend/
  ├── shared/
  │   ├── events/
  │   ├── observability/
  │   ├── logging/
  │   └── config/
  ├── infrastructure/
  │   ├── docker/
  │   ├── postgres/
  │   ├── rabbitmq/
  │   └── otel-collector/
  ├── dashboards/
  ├── docs/
  ├── compose.yaml
  ├── compose.dev.yaml
  ├── Makefile
  └── README.md

  ## Recommended implementation phases

  ### Phase 1: Foundation

  - Create the new parcelpulse repository
  - Add Docker Compose
  - Add PostgreSQL and RabbitMQ
  - Add API gateway
  - Add OpenTelemetry setup
  - Add basic frontend shell

  ### Phase 2: Core business flow

  - Implement order service
  - Implement customer service
  - Implement payment service
  - Add order and payment events
  - Display orders in the frontend

  ### Phase 3: Delivery workflow

  - Add dispatch service
  - Add tracking service
  - Add simulated drivers
  - Add delivery status updates
  - Add notification service

  ### Phase 4: Analytics and KPIs

  - Add analytics service
  - Add KPI endpoints
  - Add business event publishing
  - Add dashboard charts

  ### Phase 5: Failure scenarios

  - Add scenario service
  - Add payment slowdown
  - Add driver shortage
  - Add queue backlog
  - Add database latency
  - Add CPU stress scenario

  ### Phase 6: Dynatrace integration

  - Configure OTLP export
  - Add service metadata
  - Add custom metrics
  - Add log correlation
  - Add dashboards
  - Add alerting and SLO definitions
  - Document investigation walkthroughs

  ## Recommended initial scope

  To keep the first version manageable, start with:

  API Gateway
  Order Service
  Payment Service
  Dispatch Service
  Analytics Service
  Scenario Service
  React Frontend
  PostgreSQL
  RabbitMQ
  OpenTelemetry Collector

  Customer, tracking, and notification services can follow once the core flow works.

  This gives us a realistic microservice system without recreating EasyTrade’s level of complexity, while still providing enough telemetry to build meaningful Dynatrace dashboards and alerts.