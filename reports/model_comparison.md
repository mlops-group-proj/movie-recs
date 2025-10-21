# Model Comparison

Combined quality and performance at top-K.

| model      | version   |   k |   HR@K |   NDCG@K |   train_seconds |   peak_mem_mb |   p50_ms |   p95_ms |
|:-----------|:----------|----:|-------:|---------:|----------------:|--------------:|---------:|---------:|
| popularity | v0.1      |  10 | 0.121  |   0.064  |            0    |           nan |     0.18 |     0.49 |
| itemcf     | v0.1      |  10 | 0.2303 |   0.1275 |            0    |           nan |    41.06 |   251.4  |
| als        | v0.2      |  10 | 0.016  |   0.0075 |            1.17 |           nan |     0.49 |     1.04 |