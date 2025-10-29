from dataclasses import dataclass
from pathlib import Path
import os, yaml

@dataclass
class DataConfig:
    ratings_path: str = "data/ratings.csv"
    user_col: str = "userId"
    item_col: str = "movieId"
    rating_col: str = "rating"
    timestamp_col: str = "timestamp"

@dataclass
class TrainConfig:
    model_type: str = "als"
    seed: int = 42
    als_rank: int = 64
    als_reg: float = 0.01
    als_iters: int = 15
    top_k: int = 10

@dataclass
class EvalConfig:
    top_k: int = 10

@dataclass
class Config:
    data: DataConfig
    train: TrainConfig
    eval: EvalConfig

def load_config(path: str = "config.yaml") -> Config:
    cfg_path = Path(path)
    with cfg_path.open("r") as f:
        raw = yaml.safe_load(f)

    rp = os.getenv("RATINGS_PATH", raw["data"]["ratings_path"])

    data = DataConfig(
        ratings_path=rp,
        user_col=raw["data"]["user_col"],
        item_col=raw["data"]["item_col"],
        rating_col=raw["data"]["rating_col"],
        timestamp_col=raw["data"]["timestamp_col"],
    )
    train = TrainConfig(**raw["train"])
    evalc = EvalConfig(**raw["eval"])
    return Config(data=data, train=train, eval=evalc)