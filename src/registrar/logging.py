import logging

from loguru import logger
from rich.logging import RichHandler


def setup_logging(level: str = "INFO"):
    logger.remove()

    logger.add(
        RichHandler(
            rich_tracebacks=True,
            markup=True,
        ),
        level=level,
        format="{message}",
    )

    logger.add(
        "registrar.log",
        level="DEBUG",
        rotation="10 MB",
        compression="zip",
        serialize=True,
    )

    # intercept stdlib logs (httpx, tenacity, etc.)
    class InterceptHandler(logging.Handler):
        def emit(self, record):
            try:
                logger.opt(depth=6).log(record.levelname, record.getMessage())
            except Exception:
                pass

    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    return logger


log = setup_logging()
