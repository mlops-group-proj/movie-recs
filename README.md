# Movie Recommender System — Team *MedicalAI*

<!-- CI/CD & Coverage Badges -->
[![Probes](https://github.com/mlops-group-proj/movie-recs/actions/workflows/probes.yml/badge.svg)](https://github.com/mlops-group-proj/movie-recs/actions/workflows/probes.yml)
[![CI & CD Pipeline](https://github.com/mlops-group-proj/movie-recs/actions/workflows/ci.yml/badge.svg)](https://github.com/mlops-group-proj/movie-recs/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/mlops-group-proj/movie-recs/branch/main/graph/badge.svg)](https://codecov.io/gh/mlops-group-proj/movie-recs)
[![Docker Image](https://img.shields.io/badge/docker-ready-blue)](https://ghcr.io/medicalai/movie-recs)
[![Deploy: AWS ECS](https://img.shields.io/badge/deploy-AWS%20ECS-blue.svg?logo=amazonaws)](https://us-east-2.console.aws.amazon.com/ecs/v2/clusters/movie-recs-cluster-v2/services/movie-recs-task-service-4xo8z7x0/details)
[![Grafana](https://img.shields.io/badge/monitoring-grafana-orange)](#monitoring)
[![Python 3.11](https://img.shields.io/badge/python-3.11-yellow.svg?logo=python)](https://www.python.org/)


> **COT 6930 – AI & ML in Production**  
> Florida Atlantic University • Fall 2025  
> Instructor: **Dr. Hamzah Al-Najada**

---

## Overview
This repository implements a **cloud-native movie recommender system** designed for real-world **MLOps** practice.  
It integrates streaming ingestion, containerized training, CI/CD automation, monitoring, retraining, and responsible-AI analysis.

The system ingests user events from **Kafka**, trains and evaluates models on the **MovieLens 1M** dataset, and serves ranked movie recommendations through a **FastAPI** endpoint deployed to **AWS ECS Fargate**.

---

<details>
<summary><b>Architecture</b></summary>

```mermaid
flowchart LR
  K[Kafka Topics<br>(watch, rate, reco_requests)] --> I[Stream Ingestor<br>(schema validation → S3 snapshot)]
  I --> T[Batch Trainer<br>(offline eval + model publish)]
  T --> R[Model Registry<br>v0.1–v0.3]
  R --> A[Recommender API<br>/recommend /metrics /healthz]
  A -->|Probes| K2[reco_responses]
  A --> M[Grafana + Prometheus<br>(latency, error rate)]
```

**Core Services**
- `stream-ingestor` — Kafka consumer → schema validation → snapshot (Parquet/CSV).
- `batch-trainer` — Offline training of Popularity, ItemCF, ALS, Neural MF.
- `recommender-api` — FastAPI service with `/recommend`, `/metrics`, `/healthz`.
- `probe.py` — Periodic HTTP probes; logs latency metrics to Kafka.
- `ab_switch` — Routes traffic between model versions for A/B testing.

**Cloud Runtime:** AWS ECS Fargate  
**Registry:** GitHub Container Registry  
**Monitoring:** Prometheus + Grafana  
**CI/CD:** GitHub Actions

</details>

---

## Milestone Progress

| Milestone | Focus | Key Deliverables | Status |
|:-----------|:------|:-----------------|:-------:|
| **1** | Team Formation & Proposal | Contract, architecture diagram, CI/CD plan | Done |
| **2** | Kafka Wiring & Baselines | Kafka topics verified, baseline models trained (ItemCF, ALS), first cloud deploy | Done |
| **3** | Evaluation & Quality Gates | Offline + online metrics, schema & drift checks, CI/CD pipeline | Done |
| **4** | Monitoring & Retraining | Dashboards, alerts, automated model updates, A/B tests | In Progress |
| **5** | Fairness & Security | Bias metrics, feedback loop detection, threat model + final demo | Coming Soon |

---

## Offline Evaluation (Milestone 3)

| model      |   k |      HR@K |    NDCG@K |   train_seconds |   size_MB |      p50_ms |      p95_ms |
|:-----------|----:|----------:|----------:|----------------:|----------:|------------:|------------:|
| ncf        |  10 | 0.137252  | 0.0668516 |       376.469   |      5.28 | 0.035541    | 0.0494473   |
| als        |  10 | 0.0988411 | 0.0489501 |         3.08029 |      2.58 | 0.0635835   | 0.0735861   |
| itemcf     |  10 | 0.0753311 | 0.0401158 |         6.23108 |     90.52 | 0.021458    | 0.0284191   |
| popularity |  10 | 0.0437086 | 0.0223218 |         1.11825 |      0.01 | 8.30041e-05 | 0.000125001 |

---

## Deployment Guide

1. **Set Environment Variables**
   ```bash
   cp infra/kafka.env.example .env
   export $(cat .env | xargs)
   ```

2. **Build & Run**
   ```bash
   docker compose up --build
   ```

3. **Test Endpoints**
   ```bash
   curl http://localhost:8080/healthz
   curl http://localhost:8080/recommend/42?k=10&model=ncf
   curl http://localhost:8080/metrics
   ```
   Deployed to AWS ECS Fargate at: http://movie-recs-alb-782825466.us-east-2.elb.amazonaws.com:8080
   

4. **Probe**
   ```bash
   python scripts/probe.py --interval 300
   ```

5. **View Dashboard**
   - Grafana: [http://movie-recs-alb-782825466.us-east-2.elb.amazonaws.com:3000](http://movie-recs-alb-782825466.us-east-2.elb.amazonaws.com:3000)
   - Prometheus endpoint: `/metrics`

---

## Automated Retraining & Model Registry

- **Scheduled retrain:** `.github/workflows/retrain.yml` runs every Monday & Thursday at 05:30 UTC and on demand. It trains ALS on `data/ml1m_prepared/ratings.csv`, exports artifacts via `scripts/export_model.py`, commits to repository, and uploads the newly versioned registry folder as a workflow artifact.
- **Manual export:**
  ```bash
  python scripts/train_als.py \
      --ratings_csv data/ml1m_prepared/ratings.csv \
      --output_dir artifacts/latest/als
  python scripts/export_model.py \
      --source artifacts/latest/als \
      --registry model_registry \
      --model-name als \
      --data-path data/ml1m_prepared/ratings.csv
  ```
  This creates `model_registry/vX.Y/als/` plus a `meta.json` manifest with git SHA, snapshot hash, and metrics, and updates `model_registry/latest.txt`.
- **Hot swap endpoint:** `GET /switch?model=v0.3` reloads the requested version without redeploying. FastAPI exposes the active version via `/healthz`.
- **Rollout strategies:** Support for canary deployments, A/B testing, and shadow mode. Configure via environment variables or REST API:
  ```bash
  # Canary rollout: 10% traffic to v0.4
  curl -X POST "http://localhost:8080/rollout/update?strategy=canary&canary_version=v0.4&canary_percentage=10"
  # Check status
  curl http://localhost:8080/rollout/status
  ```
- **Prometheus metrics:** Track model versions, switches, and rollout status:
  - `model_version_info` - Current active version with git SHA and data snapshot
  - `model_switches_total` - Hot-swap operations (success/failure)
  - Standard metrics: latency, error rates, drift indicators
- **Provenance fields:** Each inference now records `model_version`, while registry manifests capture `git_sha`, `data_snapshot_id`, `image_digest`, and metrics for traceability.

📖 **[Full Rollout Guide](docs/ROLLOUT_GUIDE.md)** — Comprehensive guide for deployment strategies, canary rollouts, A/B testing, and troubleshooting.

---

## Key Learnings

- Building **stream-aware** ML pipelines with Kafka.  
- Designing **observable, retrainable** production ML systems.  
- Implementing **schema validation, drift detection**, and CI/CD gates.  
- Conducting **offline + online evaluation** using HR@K, NDCG@K, and personalized-rate KPIs.  
- Applying **responsible AI principles** (fairness, feedback loops, security).

---

## Team MedicalAI

| Role | Member |
|:------|:-------|
| Project Manager | **Daniel Zimmerman** |
| Data & Streaming Lead | **Arvin Nourian** |
| ML Lead | **LakshmiNarayana Latchireddi** |
| Cloud Engineer | **Krushal Kalkani** |

---

## References
- Geoff Hulten — *Building Intelligent Systems*  
- Sculley et al. — *Hidden Technical Debt in ML Systems*  
- FAU COT 6930 Labs 1–5 (API Security, Kafka, Git, Model Testing, Docker)

---

## License
Educational use only — part of **FAU COT 6930 AI & ML in Production** coursework.
