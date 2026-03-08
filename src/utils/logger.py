"""
logger.py
=========
Cau hinh he thong logging tap trung cho toan du an.

Chuc nang:
    - Log ra file (RotatingFileHandler, 10MB, 5 backup) va console dong thoi
    - Su dung UTC time cho tat ca log entries
    - Cung cap get_logger() de moi module lay logger instance

Cach dung:
    from src.utils.logger import get_logger
    logger = get_logger()          # logger goc (system_strategy)
    logger = get_logger("core")    # logger con  (system_strategy.core)
"""

import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Optional


class UTCFormatter(logging.Formatter):
    """Custom formatter su dung UTC time thay vi local time."""

    def formatTime(self, record, datefmt=None):
        ct = datetime.fromtimestamp(record.created, tz=timezone.utc)
        if datefmt:
            return ct.strftime(datefmt)
        return ct.strftime("%Y-%m-%d %H:%M:%S")


def setup_logger(
    name: str = "system_strategy",
    log_file: str = "system_strategy.log",
    level: int = logging.INFO,
    max_bytes: int = 10 * 1024 * 1024,   # 10 MB
    backup_count: int = 5,
) -> logging.Logger:
    """
    Thiet lap logger voi file va console output.

    Args:
        name         : Ten logger
        log_file     : Duong dan file log
        level        : Muc do log (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        max_bytes    : Kich thuoc toi da file log truoc khi rotate (10MB)
        backup_count : So file backup giu lai (5)

    Returns:
        Logger instance da cau hinh
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Xoa handlers cu neu co (tranh duplicate khi goi lai)
    if logger.handlers:
        logger.handlers.clear()

    # Format: [2026-03-08 23:10:05 UTC] [INFO    ] Message
    formatter = UTCFormatter(
        "[%(asctime)s UTC] [%(levelname)-8s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler voi rotation
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


# Global logger instance (singleton)
_logger = setup_logger()


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Lay logger instance.

    Args:
        name : Ten logger con (optional).
               None  -> tra ve logger goc "system_strategy"
               "xyz" -> tra ve logger con "system_strategy.xyz"

    Returns:
        Logger instance
    """
    if name:
        return logging.getLogger(f"{_logger.name}.{name}")
    return _logger


__all__ = ["setup_logger", "get_logger"]
