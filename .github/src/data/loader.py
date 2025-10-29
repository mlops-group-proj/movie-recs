import pandas as pd
from ..utils.logger import get_logger

log = get_logger()

def load_ratings_csv(path: str) -> pd.DataFrame:
    log.info(f"Loading ratings from {path}")
    df = pd.read_csv(path)
    return df