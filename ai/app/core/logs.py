"""로그 형식을 정한다.

text는 로컬에서 읽기 좋은 한 줄이고, json은 서버에서 Loki가 칸별로 읽는 형식이다.
json의 칸 이름은 BE(Spring Boot logstash 형식)와 맞추고, 작업 중에는 job_id·video_id·step_id와
traceId·spanId를 붙인다. uvicorn 로그도 같은 json으로 나오게 한다.
"""

import logging
from typing import Any, Literal

from pythonjsonlogger.core import RESERVED_ATTRS
from pythonjsonlogger.json import JsonFormatter

from app.core.config import Settings
from app.core.tracing import log_fields

LogFormat = Literal["text", "json"]

TEXT_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
LEVELS = {"WARNING": "WARN", "CRITICAL": "ERROR"}
UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.__dict__.update(log_fields())
        return True


class ServerJsonFormatter(JsonFormatter):
    """레벨은 BE와 같은 DEBUG·INFO·WARN·ERROR로 쓴다. color_message는 uvicorn이 붙이는 색 글이다."""

    def __init__(self) -> None:
        super().__init__(
            "{message}{levelname}{name}",
            style="{",
            rename_fields={"levelname": "level", "name": "logger_name", "exc_info": "stack_trace"},
            reserved_attrs=[*RESERVED_ATTRS, "color_message"],
            timestamp="@timestamp",
            json_ensure_ascii=False,
        )

    def process_log_record(self, log_data: dict[str, Any]) -> dict[str, Any]:
        log_data["level"] = LEVELS.get(log_data["level"], log_data["level"])
        return log_data


def build_handler(log_format: LogFormat) -> logging.Handler:
    handler = logging.StreamHandler()
    if log_format == "json":
        handler.setFormatter(ServerJsonFormatter())
        handler.addFilter(ContextFilter())
    else:
        handler.setFormatter(logging.Formatter(TEXT_FORMAT))
    return handler


def setup_logging(settings: Settings) -> None:
    """json이면 uvicorn 로거가 따로 찍지 않고 같은 handler로 보내게 한다."""
    logging.basicConfig(level=settings.log_level, handlers=[build_handler(settings.log_format)])
    if settings.log_format == "json":
        for name in UVICORN_LOGGERS:
            uvicorn_logger = logging.getLogger(name)
            uvicorn_logger.handlers.clear()
            uvicorn_logger.propagate = True
