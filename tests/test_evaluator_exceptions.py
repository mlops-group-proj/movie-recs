import pandas as pd
from recommender.evaluator import evaluate_batch as evaluate_offline

def test_evaluate_offline_empty_df(tmp_path):
    df = pd.DataFrame(columns=["user", "item", "rating"])
    result = evaluate_offline(df, tmp_path)
    assert isinstance(result, dict)
    assert "hr@10" in result
    assert "ndcg@10" in result
