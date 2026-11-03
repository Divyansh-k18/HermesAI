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
    email_poll_seconds: int = 20  # how often connected mailboxes are checked for new orders
    # AI step: any OpenAI-compatible chat completions endpoint (for example Google AI Studio or Groq).
    # All three must be set in backend/.env for AI steps to run. The key is never returned by the API.
    ai_base_url: str = ""
    ai_api_key: str = ""
    ai_model: str = ""
    ai_calls_per_hour: int = 200  # per organization
    ai_max_input_chars: int = 8000
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
