import logging
import os
import sys
from typing import Any

from zxtg.config import config


class RedactTokenFilter(logging.Filter):
    """Filter that prevents TELEGRAM_TOKEN from ever appearing in logs (NFR-09)."""

    def filter(self, record: logging.LogRecord) -> bool:
        token = os.getenv("TELEGRAM_TOKEN") or config.TELEGRAM_TOKEN
        if token and len(token) > 4:
            if isinstance(record.msg, str):
                record.msg = record.msg.replace(token, "***REDACTED_TOKEN***")
            if record.args:
                new_args: list[Any] = []
                for arg in record.args if isinstance(record.args, (list, tuple)) else [record.args]:
                    if isinstance(arg, str):
                        new_args.append(arg.replace(token, "***REDACTED_TOKEN***"))
                    else:
                        new_args.append(arg)
                record.args = tuple(new_args)
        return True


def setup_logging(level: str | None = None) -> logging.Logger:
    """Configure structured logging and attach the security filter."""
    log_level_str = (level or config.LOG_LEVEL or "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    logger = logging.getLogger("zxtg")
    logger.setLevel(log_level)

    # Avoid adding duplicate handlers on multiple calls
    if not any(isinstance(f, RedactTokenFilter) for f in logger.filters):
        logger.addFilter(RedactTokenFilter())

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(log_level)
        formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        handler.addFilter(RedactTokenFilter())
        logger.addHandler(handler)

    return logger


logger = setup_logging()
