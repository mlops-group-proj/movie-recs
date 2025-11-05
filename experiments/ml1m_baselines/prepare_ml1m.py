import zipfile, pandas as pd, numpy as np, pathlib, time
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parents[2]  # repo root
ZIP = ROOT/"data/dataset/ml-1m.zip"
OUT = ROOT/"data/ml1m_prepared"
OUT.mkdir(parents=True, exist_ok=True)

with zipfile.ZipFile(ZIP) as z:
    with z.open("ml-1m/ratings.dat") as f:
        # ratings.dat format: UserID::MovieID::Rating::Timestamp
        df = pd.read_csv(f, sep="::", engine="python",
                         names=["user","item","rating","ts"])
# chronological sort per user
df = df.sort_values(["user","ts"])
# leave-one-out: last interaction per user → test, rest → train
last_idx = df.groupby("user")["ts"].idxmax()
test = df.loc[last_idx]
train = df.drop(index=last_idx)

# (optional) downcast for memory
for col in ["user","item","rating"]: 
    df[col] = pd.to_numeric(df[col], downcast="integer")

train.to_csv(OUT/"train.csv", index=False)
test.to_csv(OUT/"test.csv", index=False)
print("Wrote:", OUT/"train.csv", OUT/"test.csv", "users:", train.user.nunique(), "items:", train.item.nunique())
