import os


SERVICE_NAME = os.getenv("SERVICE_NAME", "parcelpulse-service")
PORT = int(os.getenv("PORT", "8000"))
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://parcelpulse:parcelpulse@localhost:5432/parcelpulse")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://parcelpulse:parcelpulse@localhost:5672/")
ENVIRONMENT = os.getenv("APP_ENV", "local")
OTEL_ENABLED = os.getenv("OTEL_ENABLED", "false").lower() == "true"
OTEL_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME") or SERVICE_NAME
OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
