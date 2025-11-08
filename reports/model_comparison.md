# Model Comparison Summary

This table combines model accuracy, training cost, and inference latency.

Generated automatically by `compare.py`.


| model      |   k |      HR@K |    NDCG@K |   train_seconds |   model_size_MB |      p50_ms |      p95_ms |
|:-----------|----:|----------:|----------:|----------------:|----------------:|------------:|------------:|
| ncf        |  10 | 0.137252  | 0.0668516 |       376.469   |            5.28 | 0.035541    | 0.0494473   |
| als        |  10 | 0.0988411 | 0.0489501 |         3.08029 |            2.58 | 0.0635835   | 0.0735861   |
| itemcf     |  10 | 0.0753311 | 0.0401158 |         6.23108 |           90.52 | 0.021458    | 0.0284191   |
| popularity |  10 | 0.0437086 | 0.0223218 |         1.11825 |            0.01 | 8.30041e-05 | 0.000125001 |