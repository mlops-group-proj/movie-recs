import pytest
from src.evaluation.metrics import hr_at_k, ndcg_at_k

def test_hr_simple():
    assert hr_at_k([5], [5,4,3], 1) == 1.0
    assert hr_at_k([5], [4,3,2], 3) == 0.0
    assert hr_at_k([1,2], [2,9,8], 2) == 1.0

def test_ndcg_binary():
    # perfect at rank 1
    assert ndcg_at_k([42], [42, 7, 8], 3) == pytest.approx(1.0, 1e-9)
    # relevant at rank 3
    v = ndcg_at_k([42], [7, 8, 42], 3)
    # DCG = 1/log2(3+1) = 1/2 ; IDCG = 1/log2(1+1)=1
    assert v == pytest.approx(0.5, 1e-9)

    # two relevant items in list
    v2 = ndcg_at_k([1,2], [2, 1, 3, 4], 3)
    # DCG = 1/log2(2) + 1/log2(3) = 1 + 1/1.58496...
    # IDCG for 2 relevant within k=3 = same as above -> NDCG=1
    assert v2 == pytest.approx(1.0, 1e-9)
