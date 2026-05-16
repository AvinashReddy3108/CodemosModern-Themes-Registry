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


def setup_logging(level: str = "INFO"):
    # Remove default loguru handlers
    logger.remove()

    # Add Rich console handler
    logger.add(
        RichHandler(rich_tracebacks=True, markup=True),
        level=level,
        format="{message}",
    )

    # Add file sink
    logger.add("registrar.log", level=level)

    # Map string level to numeric logging level
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Intercept standard logging with chosen level
    logging.basicConfig(handlers=[InterceptHandler()], level=numeric_level)

    # TODO: Optionally tune noisy libraries
    # logging.getLogger("httpx").setLevel(numeric_level)
    # logging.getLogger("asyncio").setLevel(logging.WARNING)
    # logging.getLogger("tenacity").setLevel(logging.DEBUG)
    # logging.getLogger("pyrate_limiter").setLevel(logging.INFO)

    return logger


log = setup_logging()
