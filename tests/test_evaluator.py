from recommender import evaluator

def test_hit_rate_and_ndcg():
    preds = [[1,2,3], [3,4,5]]
    truth = [2,5]
    hr = evaluator.hit_rate(preds, truth, k=3)
    nd = evaluator.ndcg(preds, truth, k=3)
    assert 0 <= hr <= 1
    assert 0 <= nd <= 1

def test_empty_inputs():
    assert evaluator.hit_rate([], [], k=3) == 0
    assert evaluator.ndcg([], [], k=3) == 0
