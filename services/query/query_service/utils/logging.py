import logging
import logging.config
import typing

import query_service.config as config


def setup_logging() -> logging.Logger:
    settings = config.get_settings()
    log_config = settings.get_log_config()
    logging.config.dictConfig(log_config)
    return logging.getLogger("query_service")


def get_logger(name: str | None = None) -> logging.Logger:
    if name:
        return logging.getLogger(f"query_service.{name}")
    return logging.getLogger("query_service")
