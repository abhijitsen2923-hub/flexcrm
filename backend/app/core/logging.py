import json
import logging
import logging.config
from contextvars import ContextVar


request_id_context: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_context.get()
        return True


class JsonFormatter(logging.Formatter):
    """Single-line JSON per log record.

    Cloud Run's Logs Explorer (Cloud Logging) auto-parses JSON stdout and
    promotes top-level keys to filterable fields — so you can query
    `request_id="abc-123"` directly in the console without grepping.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "severity": record.levelname,  # Cloud Logging recognises `severity`
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Set up logging once at import time.

    Production / staging emit JSON (Cloud Logging-friendly); local + test emit
    the human-readable format so terminals stay greppable.
    """
    # Local import so we don't create a cycle with `config.py` (which itself
    # may log during validation).
    from app.core.config import get_settings

    environment = get_settings().environment
    formatter_name = "json" if environment in {"staging", "production"} else "standard"

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {
                "request_id": {
                    "()": RequestIdFilter,
                }
            },
            "formatters": {
                "standard": {
                    "format": "%(asctime)s %(levelname)s [%(name)s] [request_id=%(request_id)s] %(message)s",
                },
                "json": {
                    "()": JsonFormatter,
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": formatter_name,
                    "filters": ["request_id"],
                }
            },
            "root": {
                "handlers": ["console"],
                "level": "INFO",
            },
        }
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
