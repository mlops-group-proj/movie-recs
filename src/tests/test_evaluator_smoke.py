import numpy as np
import pandas as pd
from evaluation.evaluator import evaluate_topk

class DummyModel:
    def score_items(self, user_id, item_ids):
        return np.asarray(item_ids, dtype=float)

def test_evaluator_smoke():
    train = pd.DataFrame(
        {"user_id":[1,1,1,2,2], "item_id":[10,11,12,20,21], "rating":[4,5,3,5,4], "timestamp":[1,2,3,1,2]}
    )
    test  = pd.DataFrame({"user_id":[1,2], "item_id":[13,22], "rating":[5,5], "timestamp":[4,3]})
    res = evaluate_topk(
        model=DummyModel(),
        test_df=test, user_col="user_id", item_col="item_id",
        k=3, train_df=train, negatives_per_user=30
    )
    assert res.users == 2
    assert 0.0 <= res.hr   <= 1.0
    assert 0.0 <= res.ndcg <= 1.0
