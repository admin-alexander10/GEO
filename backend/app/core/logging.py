import logging
import sys

def setup_logging():
    """Configura un logger estructurado y visualmente claro para eventos de rescate y emergencias."""
    logger = logging.getLogger("georescue")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [GEORESCUE-IA] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger

logger = setup_logging()
