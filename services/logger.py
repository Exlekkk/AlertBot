import logging
import sys
from pathlib import Path


def get_logger(name: str, log_file: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    try:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = logging.FileHandler(log_file)
    except OSError:
        # Local tests or restricted deployments may not be able to create
        # /opt/smct-alert/logs.  Logging must not block FastAPI/scanner import.
        handler = logging.StreamHandler(sys.stderr)

    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger
