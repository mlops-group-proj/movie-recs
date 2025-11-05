import logging
import os

def get_logger(name: str = "movie-recs", level: str = "INFO"):
    """
    Simple reusable logger for console + optional file logging.
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(log_level)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    log_dir = os.path.join("artifacts", "logs")
    os.makedirs(log_dir, exist_ok=True)
    fh = logging.FileHandler(os.path.join(log_dir, "pipeline.log"), mode="a", encoding="utf-8")
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    return logger
