from recommender import evaluator

def test_metrics_run():
    preds = [[1,2,3],[2,3,4]]
    truth = [{2},{3}]
    out = evaluator.evaluate_batch(preds, truth, k=3)
    assert all(0 <= v <= 1 for v in out.values())
