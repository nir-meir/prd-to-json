"""
Logging utilities for PRD-to-JSON generator.

Provides consistent logging configuration across all modules.
"""

import logging
import sys
from pathlib import Path
from typing import Optional
from datetime import datetime


# Default format
DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Module-level logger cache
_loggers: dict = {}
_configured = False


def setup_logging(
    level: str = "INFO",
    format_string: Optional[str] = None,
    log_file: Optional[Path | str] = None,
    console: bool = True,
) -> None:
    """
    Configure logging for the application.

    Should be called once at application startup.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_string: Custom format string (uses DEFAULT_FORMAT if None)
        log_file: Optional path to log file
        console: Whether to log to console (default True)
    """
    global _configured

    # Get numeric level
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Create formatter
    formatter = logging.Formatter(
        format_string or DEFAULT_FORMAT,
        datefmt=DEFAULT_DATE_FORMAT
    )

    # Get root logger for our package
    root_logger = logging.getLogger("prdtojson")
    root_logger.setLevel(numeric_level)

    # Clear existing handlers
    root_logger.handlers.clear()

    # Add console handler
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # Add file handler if specified
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_path, encoding='utf-8')
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for the given module name.

    Args:
        name: Module name (typically __name__)

    Returns:
        Configured logger instance
    """
    global _configured

    # Auto-configure with defaults if not done
    if not _configured:
        setup_logging()

    # Create child logger under our package
    if name.startswith("src."):
        name = name[4:]  # Remove "src." prefix

    logger_name = f"prdtojson.{name}" if not name.startswith("prdtojson") else name

    if logger_name not in _loggers:
        _loggers[logger_name] = logging.getLogger(logger_name)

    return _loggers[logger_name]


class LogContext:
    """
    Context manager for structured logging with context.

    Example:
        with LogContext(logger, "Processing feature", feature_id="F-01"):
            # logs will include feature_id context
            logger.info("Starting...")
    """

    def __init__(self, logger: logging.Logger, operation: str, **context):
        self.logger = logger
        self.operation = operation
        self.context = context
        self.start_time = None

    def __enter__(self):
        self.start_time = datetime.now()
        context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
        self.logger.info(f"Starting: {self.operation} ({context_str})")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = (datetime.now() - self.start_time).total_seconds()

        if exc_type is None:
            self.logger.info(f"Completed: {self.operation} ({duration:.2f}s)")
        else:
            self.logger.error(
                f"Failed: {self.operation} ({duration:.2f}s) - {exc_type.__name__}: {exc_val}"
            )

        return False  # Don't suppress exceptions


class ProgressLogger:
    """
    Helper for logging progress updates.

    Example:
        progress = ProgressLogger(logger, "Generating nodes", total=10)
        for i in range(10):
            progress.update(i + 1)
        progress.complete()
    """

    def __init__(
        self,
        logger: logging.Logger,
        operation: str,
        total: int,
        log_interval: int = 10,  # Log every N percent
    ):
        self.logger = logger
        self.operation = operation
        self.total = total
        self.log_interval = log_interval
        self.current = 0
        self.last_logged_pct = -1
        self.start_time = datetime.now()

    def update(self, current: int, message: Optional[str] = None) -> None:
        """Update progress."""
        self.current = current
        pct = int((current / self.total) * 100) if self.total > 0 else 100

        # Log at intervals
        if pct >= self.last_logged_pct + self.log_interval:
            self.last_logged_pct = pct
            msg = f"{self.operation}: {pct}% ({current}/{self.total})"
            if message:
                msg += f" - {message}"
            self.logger.info(msg)

    def increment(self, message: Optional[str] = None) -> None:
        """Increment progress by 1."""
        self.update(self.current + 1, message)

    def complete(self, message: Optional[str] = None) -> None:
        """Mark progress as complete."""
        duration = (datetime.now() - self.start_time).total_seconds()
        msg = f"{self.operation}: Complete ({duration:.2f}s)"
        if message:
            msg += f" - {message}"
        self.logger.info(msg)


def log_exception(logger: logging.Logger, message: str, exc: Exception) -> None:
    """
    Log an exception with full traceback at ERROR level.

    Args:
        logger: Logger instance
        message: Context message
        exc: Exception to log
    """
    logger.error(f"{message}: {type(exc).__name__}: {exc}", exc_info=True)


def log_json(logger: logging.Logger, message: str, data: dict, level: int = logging.DEBUG) -> None:
    """
    Log JSON data in a readable format.

    Args:
        logger: Logger instance
        message: Context message
        data: JSON-serializable data
        level: Log level (default DEBUG)
    """
    import json
    formatted = json.dumps(data, indent=2, default=str)
    logger.log(level, f"{message}:\n{formatted}")
