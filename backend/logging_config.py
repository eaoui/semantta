"""Semantta backend logging configuration."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from paths import LOG_FILE, ensure_data_dirs


LOGGER_NAME = "semantta"

MAX_LOG_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 3


def configure_logging() -> logging.Logger:
    """
    Configure Semantta application logging.

    Logs are written both to stderr and to the user-data log file.
    Repeated calls do not add duplicate handlers.
    """
    ensure_data_dirs()

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=MAX_LOG_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


logger = configure_logging()