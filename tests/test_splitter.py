import pandas as pd
from src.data.splitter import chronological_split

def _toy_df():
    return pd.DataFrame(
        {
            "userId":   [1,1,1, 2,2, 3, 4,4],
            "movieId":  [10,11,12, 20,21, 30, 40,41],
            "rating":   [4,5,3, 5,4, 2, 4,3],
            "timestamp":[1000,1000,2000, 500,600, 700, 42,42],  # ties for user 1 & 4
        }
    )

def test_no_overlap_and_temporal_order():
    df = _toy_df()
    train, test = chronological_split(
        df,
        user_col="userId",
        timestamp_col="timestamp",
        holdout_ratio=0.4,               # 60/40 split
        min_user_interactions=2,
        drop_users_not_meeting_min=True,
        stable_tie_break=True,
    )

    # no overlap
    merged = train.merge(test, on=["userId", "movieId", "rating", "timestamp"])
    assert len(merged) == 0

    # user 1: 3 events -> floor(3*0.6)=1 -> 1 train, 2 test
    u1t, u1e = train[train.userId==1], test[test.userId==1]
    assert (len(u1t), len(u1e)) == (1,2)
    assert u1t.timestamp.max() <= u1e.timestamp.min()

    # user 2: 2 events -> 1/1
    u2t, u2e = train[train.userId==2], test[test.userId==2]
    assert (len(u2t), len(u2e)) == (1,1)
    assert u2t.timestamp.max() <= u2e.timestamp.min()

    # user 3: single -> dropped entirely
    assert not any(train.userId==3) and not any(test.userId==3)

    # user 4: ties handled stably (1/1)
    u4t, u4e = train[train.userId==4], test[test.userId==4]
    assert (len(u4t), len(u4e)) == (1,1)

def test_keep_small_users_in_train():
    df = _toy_df()
    train, test = chronological_split(
        df,
        user_col="userId",
        timestamp_col="timestamp",
        holdout_ratio=0.5,
        min_user_interactions=3,
        drop_users_not_meeting_min=False,
        stable_tie_break=True,
    )
    assert any(train.userId == 3) and not any(test.userId == 3)