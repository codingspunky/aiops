from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Use sqlite+aiosqlite for local dev; swap to
    # postgresql+asyncpg://user:pass@host:5432/db for Postgres.
    database_url: str = "sqlite+aiosqlite:///./aiops.db"

    # Correlation tuning
    correlation_window_seconds: int = 600     # alerts within this window can group
    dedup_suppress_seconds: int = 300         # repeat of same fingerprint suppressed
    correlation_label_keys: tuple[str, ...] = ("cluster", "namespace", "host", "instance")

    # LLM / RCA agent. Point base_url at WiseGateway / LiteLLM proxy.
    llm_base_url: str = "http://localhost:4000/v1"
    llm_api_key: str = "sk-placeholder"
    llm_model: str = "gpt-4o-mini"
    mock_llm: bool = True   # set False once base_url/key/model are real

    # Auto-run the RCA agent when an incident is created/updated
    rca_auto: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
