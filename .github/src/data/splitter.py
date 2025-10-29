import pandas as pd
from typing import Tuple

def chronological_split(
    df: pd.DataFrame,
    user_col: str,
    timestamp_col: str,
    holdout_ratio: float = 0.2
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    def _split_user(g: pd.DataFrame):
        g = g.sort_values(timestamp_col)
        n_test = max(1, int(len(g) * holdout_ratio))
        return g.iloc[:-n_test], g.iloc[-n_test:]

    train_parts, test_parts = [], []
    for _, g in df.groupby(user_col):
        tr, te = _split_user(g)
        train_parts.append(tr)
        test_parts.append(te)
    return pd.concat(train_parts), pd.concat(test_parts)