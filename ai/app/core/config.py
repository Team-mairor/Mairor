from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.paths import AI_DIR, DEFAULT_CATALOG_RUN_DIR, DEFAULT_CATALOG_SITES_DIR

ENV_FILE = AI_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["local", "dev", "prod"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["text", "json"] = "text"

    gms_api_key: SecretStr | None = None
    llm_base_url: str = "https://gms.ssafy.io/gmsapi/api.anthropic.com"
    llm_model: str = "claude-haiku-5-5"
    llm_effort: Literal["low", "medium", "high", "xhigh", "max"] = "high"
    llm_max_tokens: int = Field(default=16000, gt=0)
    llm_timeout_seconds: float = Field(default=60, gt=0)
    llm_max_retries: int = Field(default=2, ge=0)
    llm_max_concurrency: int = Field(default=50, gt=0)

    gemini_base_url: str = "https://gms.ssafy.io/gmsapi/generativelanguage.googleapis.com"
    gemini_model: str = "gemini-2.5-flash"
    gemini_timeout_seconds: float = Field(default=60, gt=0)
    gemini_max_retries: int = Field(default=2, ge=0)

    callback_timeout_seconds: float = Field(default=10, gt=0)
    callback_max_retries: int = Field(default=3, ge=0)
    callback_retry_delay_seconds: float = Field(default=1, ge=0)

    progress_interval_seconds: float = Field(default=1, gt=0)
    progress_timeout_seconds: float = Field(default=3, gt=0)

    frame_download_concurrency: int = Field(default=16, gt=0)
    frame_download_timeout_seconds: float = Field(default=30, gt=0)
    frame_download_max_retries: int = Field(default=1, ge=0)
    area_max_concurrency: int = Field(default=1, gt=0)
    area_lines: int = Field(default=2, gt=0)
    area_onnx_threads: int = Field(default=1, gt=0)
    area_opencv_threads: int = Field(default=1, gt=0)
    area_work_dir: Path | None = None

    catalog_run_dir: Path = DEFAULT_CATALOG_RUN_DIR
    catalog_run_keep_days: int = Field(default=30, gt=0)
    catalog_runs_store: Literal["local", "s3"] = "local"
    catalog_runs_s3_bucket: str | None = None
    catalog_runs_s3_prefix: str = "catalog-runs/"
    catalog_runs_s3_region: str = "ap-northeast-2"
    catalog_contact: str | None = None
    catalog_min_interval_seconds: float = Field(default=1.5, ge=0)
    catalog_request_timeout_seconds: float = Field(default=30, gt=0)
    catalog_max_retries: int = Field(default=3, ge=0)
    catalog_retry_base_delay_seconds: float = Field(default=1, ge=0)
    catalog_max_interval_seconds: float = Field(default=30, gt=0)
    catalog_robots_exempt_hosts: frozenset[str] = frozenset()
    catalog_sites_store: Literal["local", "s3"] = "local"
    catalog_sites_dir: Path = DEFAULT_CATALOG_SITES_DIR
    catalog_sites_s3_bucket: str | None = None
    catalog_sites_s3_prefix: str = "catalog-sites/"
    catalog_sites_s3_region: str = "ap-northeast-2"
    catalog_site_ttl_days: int = Field(default=30, gt=0)
    catalog_site_negative_ttl_days: int = Field(default=7, gt=0)
    catalog_backend_url: str | None = None
    catalog_internal_token: SecretStr | None = None
    catalog_backend_timeout_seconds: float = Field(default=60, gt=0)
    catalog_import_limit: int = Field(default=500, ge=1, le=2000)
    catalog_job_max_candidates: int = Field(default=3, ge=1, le=10)
    catalog_queue_url: str | None = None
    catalog_queue_region: str = "ap-northeast-2"
    catalog_worker_wait_seconds: int = Field(default=20, ge=0, le=20)
    catalog_worker_visibility_seconds: int = Field(default=900, ge=60, le=43200)
    catalog_worker_retry_delay_seconds: int = Field(default=60, ge=0, le=43200)
    catalog_worker_max_receives: int = Field(default=3, ge=1)
    catalog_worker_idle_exit_seconds: float = Field(default=0, ge=0)
    catalog_llm_model: str = "claude-sonnet-4-6"
    catalog_llm_effort: Literal["low", "medium", "high", "xhigh", "max"] = "low"

    tracing_endpoint: str | None = None
    tracing_project: str = "ai-guide"

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()
