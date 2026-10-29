from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["local", "dev", "prod"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["text", "json"] = "text"

    gms_api_key: SecretStr | None = None
    llm_base_url: str = "https://gms.ssafy.io/gmsapi/api.anthropic.com"
    llm_model: str = "claude-haiku-5-5"
    llm_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    llm_max_tokens: int = Field(default=16000, gt=0)
    llm_timeout_seconds: float = Field(default=60, gt=0)
    llm_max_retries: int = Field(default=2, ge=0)
    llm_max_concurrency: int = Field(default=50, gt=0)

    callback_timeout_seconds: float = Field(default=10, gt=0)
    callback_max_retries: int = Field(default=3, ge=0)
    callback_retry_delay_seconds: float = Field(default=1, ge=0)

    tracing_endpoint: str | None = None
    tracing_project: str = "ai-guide"

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()
