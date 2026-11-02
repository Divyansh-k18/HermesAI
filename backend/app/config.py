"""Runtime configuration loaded from environment variables (prefix HERMES_)."""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HERMES_", env_file=".env", extra="ignore")

    env: str = "development"  # development | test | production
    database_url: str = "sqlite:///./hermes_dev.db"
    session_ttl_hours: int = 12
    cookie_secure: bool = False
    cookie_domain: str | None = None
    cors_origins: list[str] = ["http://localhost:3000"]
    # Fernet key used to encrypt integration credentials at rest. Required in production.
    credential_encryption_key: str = ""
    invitation_ttl_days: int = 7
    # Resumes runs whose delay has elapsed. Disabled in unit tests, which call the engine directly.
    scheduler_enabled: bool = True
    scheduler_interval_seconds: float = 2.0
    webhook_rate_limit: int = 120  # deliveries per endpoint per minute
    login_rate_limit: int = 10
    login_rate_window_seconds: int = 900

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value):
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
