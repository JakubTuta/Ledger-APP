import logging
import logging.config
import typing

import analytics_workers.config as config


def setup_logging() -> logging.Logger:
    settings = config.get_settings()
    log_config = settings.get_log_config()
    logging.config.dictConfig(log_config)
    return logging.getLogger("analytics_workers")


def get_logger(name: str | None = None) -> logging.Logger:
    if name:
        return logging.getLogger(f"analytics_workers.{name}")
    return logging.getLogger("analytics_workers")
