import logging
from pathlib import Path


def get_logger(name: str, log_file: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.INFO)
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(file_handler)
    return logger
