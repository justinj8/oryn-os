"""Runtime configuration. Every setting has an offline-friendly default."""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"

    database_url_app: str = "postgresql+asyncpg://oryn_app:oryn_app@localhost:55432/oryn"
    database_url_owner: str = "postgresql+asyncpg://oryn_owner:oryn_owner@localhost:55432/oryn"
    redis_url: str = "redis://localhost:56379/0"

    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "oryn-main"

    jwt_secret: SecretStr = SecretStr("dev-only-change-me-oryn-jwt-secret-32b")
    jwt_ttl_minutes: int = 720
    # Fernet key for connector secrets; dev default is a fixed, documented, non-secret key.
    fernet_key: SecretStr = SecretStr("b3J5bi1kZXYtb25seS1mZXJuZXQta2V5LTMyYnl0ZXM=")

    llm_provider: Literal["replay", "anthropic"] = "replay"
    anthropic_api_key: SecretStr | None = None
    default_model: str = "claude-sonnet-5-5"

    twilio_account_sid: str | None = None
    twilio_auth_token: SecretStr | None = None
    twilio_from_number: str | None = None
    smtp_url: str | None = None
    smtp_from: str = "agents@oryn.local"

    sandbox_failure_rate: float = 0.0
    sandbox_latency_ms: int = 0
    demo_time_scale: float = 1.0

    public_base_url: str = "http://localhost:8800"

    @property
    def effective_llm_provider(self) -> Literal["replay", "anthropic"]:
        if self.llm_provider == "anthropic" and self.anthropic_api_key:
            return "anthropic"
        return "replay"


@lru_cache
def get_settings() -> Settings:
    return Settings()
