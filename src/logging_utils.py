import sys
import logging

logger = logging.getLogger("migrator")


def setup_logging(log_file: str = None):
    log_format = "%(asctime)s [%(levelname)s] %(message)s"
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=handlers,
        force=True,  # Overwrite any default configurations
    )
