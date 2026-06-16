import logging

from loguru import logger
from rich.logging import RichHandler


class InterceptHandler(logging.Handler):
    def emit(self, record):
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_back and depth > 0:
            frame = frame.f_back
            depth -= 1

        logger.opt(depth=6, exception=record.exc_info).log(level, record.getMessage())


def setup_logging(level: str = "INFO") -> logger:  # ty:ignore[invalid-type-form]
    logger.remove()

    logger.add(
        RichHandler(rich_tracebacks=True, markup=True),
        level=level,
        format="{message}",
    )
    logger.add("registrar.log", level=level)

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(handlers=[InterceptHandler()], level=numeric_level, force=True)

    return logger


# Module-level logger; configure via setup_logging() at entry point.
# Defaults to INFO so imports don't silently suppress warnings.
log = logger
