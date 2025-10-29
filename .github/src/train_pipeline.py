import numpy as np
from utils.config import load_config
from utils.logger import get_logger
from data.loader import load_ratings_csv
from data.splitter import chronological_split
from models.als_model import ALSModel
from evaluation.evaluator import evaluate_topk

log = get_logger()

def run_training(cfg_path="config.yaml"):
    cfg = load_config(cfg_path)
    np.random.seed(cfg.train.seed)

    df = load_ratings_csv(cfg.data.ratings_path)

    train_df, test_df = chronological_split(
        df,
        user_col=cfg.data.user_col,
        timestamp_col=cfg.data.timestamp_col,
        holdout_ratio=0.2,
    )

    if cfg.train.model_type == "als":
        model = ALSModel(rank=cfg.train.als_rank, reg=cfg.train.als_reg, iters=cfg.train.als_iters)
        model.fit(train_df, cfg.data.user_col, cfg.data.item_col, cfg.data.rating_col)
    else:
        raise NotImplementedError("Only ALS stub is wired for now.")

    metrics = evaluate_topk(
        model,
        test_df=test_df,
        user_col=cfg.data.user_col,
        item_col=cfg.data.item_col,
        k=cfg.eval.top_k,
    )
    log.info(f"Evaluation: {metrics}")
    return metrics

if __name__ == "__main__":
    run_training()