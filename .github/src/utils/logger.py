import logging, sys

def get_logger(name: str = "movie-recs"):
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        h = logging.StreamHandler(sys.stdout)
        fmt = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s")
        h.setFormatter(fmt)
        logger.addHandler(h)
    return logger