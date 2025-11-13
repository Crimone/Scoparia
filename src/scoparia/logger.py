"""Logger configuration for Scoparia."""

import logging
import sys


def setup_logger(name: str = "Scoparia", level: str = "INFO") -> logging.Logger:
    """Setup and configure logger.

    Args:
        name: Logger name. Defaults to "Scoparia".
        level: Log level string. Defaults to "INFO".

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level.upper()))

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    # Add handler if not already added
    if not logger.handlers:
        logger.addHandler(handler)

    return logger


# Default logger
_logger = setup_logger()


def get_logger() -> logging.Logger:
    """Get the default Scoparia logger.

    Returns:
        Default logger instance.
    """
    return _logger


def set_level(level: str) -> None:
    """Set log level for the default logger.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    _logger.setLevel(getattr(logging, level.upper()))
    for handler in _logger.handlers:
        handler.setLevel(getattr(logging, level.upper()))


# Convenience functions
def debug(msg: str, *args, **kwargs) -> None:
    """Log debug message."""
    _logger.debug(msg, *args, **kwargs)


def info(msg: str, *args, **kwargs) -> None:
    """Log info message."""
    _logger.info(msg, *args, **kwargs)


def warning(msg: str, *args, **kwargs) -> None:
    """Log warning message."""
    _logger.warning(msg, *args, **kwargs)


def error(msg: str, *args, **kwargs) -> None:
    """Log error message."""
    _logger.error(msg, *args, **kwargs)


def critical(msg: str, *args, **kwargs) -> None:
    """Log critical message."""
    _logger.critical(msg, *args, **kwargs)


def exception(msg: str, *args, **kwargs) -> None:
    """Log exception message."""
    _logger.exception(msg, *args, **kwargs)
