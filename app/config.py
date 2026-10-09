from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ParcelPulse"
    app_env: str = "local"
    log_level: str = "INFO"
    order_simulator_enabled: bool = True
    order_simulator_interval_seconds: float = 5.0
    payment_failure_rate: float = 0.03
    otel_enabled: bool = True
    otel_service_name: str = "parcelpulse"
    otel_exporter_otlp_endpoint: str = "http://localhost:4318"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()

