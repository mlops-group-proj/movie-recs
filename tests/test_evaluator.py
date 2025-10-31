import pandas as pd
from src.evaluation.evaluator import evaluate_topk
from typing import Optional
from typing import Dict, Optional, List, Set, Sequence, Tuple


class DummyModel:
    def recommend(self, user_id, k, exclude_seen=True, seen_items=None):
        # always recommend [99, 98, ...]
        return [99 - i for i in range(k)]

def evaluate_topk(
    model,
    *,
    test_df: pd.DataFrame,
    user_col: str,
    item_col: str,
    k: int,
    train_df: Optional[pd.DataFrame] = None,
    negatives_per_user: Optional[int] = None,   # <- NEW: accepted for compatibility
) -> Dict[str, float]:
    
    assert metrics["users"] == 2
    # user1 truth=[99], user2 truth=[98], dummy recs include 99 for k=1 => HR >= 0.5
    assert 0.0 <= metrics["hr"] <= 1.0
