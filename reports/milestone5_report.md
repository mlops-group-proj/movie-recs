# Milestone 5 — Fairness, Security, Feedback Loops, Demo, Reflection

Submission date: **TODO**  
Team: **MedicalAI**  
Repo: `https://github.com/mlops-group-proj/movie-recs`

---

## 1) Fairness Requirements & Metrics
- Say the harm you’re mitigating, the metric, the target, and whether you met it.

| Level | Requirement | Metric | Target | How to measure | Status |
| --- | --- | --- | --- | --- | --- |
| System | Limit head-item dominance to avoid popularity echo | Tail exposure share = % of recommendations not in top 10% most shown items | ≥ 0.25 | `python scripts/fairness_bias_scan.py --responses deliverables/evidence/reco_responses.jsonl --out deliverables/evidence/fairness/reco_bias.json` (tail_share) | TODO: met / not met |
| Model | Diversify per-user lists | Intra-list diversity (1 - average Jaccard of genres among K items) | ≥ 0.15 | Compute on sampled responses (needs genre metadata) | TODO: met / not met |

Notes: “System” = overall traffic; “Model” = per-response list. Popularity bias uses head vs tail exposure; diversity uses genres in `items.csv`.

## 2) Fairness Improvements (design + monitoring)
- List concrete levers you use to improve the metrics and how you watch them.
- Exposure constraints: enforce `tail_share >= 0.25` via post-filtering; alert when `tail_share < 0.2`.
- Diversity re-ranking: penalize duplicate genres within a list (MMR-style re-rank).
- Data collection: log `variant`, `model_version`, and `movie_ids` (already in `reco_responses`) plus simple genre lookup to monitor diversity.
- Dashboard: add `tail_share` and `unique_items` time-series to Grafana; alert at `P1` when under target for 30 minutes.

## 3) Fairness Analysis (telemetry)
- Show the numbers you observed on recent traffic; include a short table/plot and a one-line judgment.

Run after exporting the last 24–72h of reco responses from Kafka to JSONL:
```bash
python scripts/fairness_bias_scan.py \
  --responses deliverables/evidence/reco_responses.jsonl \
  --top-percent 0.1 \
  --out deliverables/evidence/fairness/reco_bias.json
```
Record `tail_share`, `top_pop_share`, and `gini_exposure` in the PDF. If diversity is computed, add a small table comparing Variant A vs B.

## 4) Feedback Loops
- What this means: call out two self-reinforcing patterns and the metric that would expose them; say whether you saw evidence in data.
- Loop 1 (popularity echo): head items get over-recommended → more watches → even more head exposure.
- Loop 2 (tail starvation): new/tail items rarely shown → no feedback → model never learns them.
- Detection approach: track `tail_share` and unique items/day; compare Variant A/B for divergence. A null finding is acceptable if the metrics stay stable.

Loop analysis command: same as fairness scan above; attach plot/table from `reco_bias.json` showing head vs tail share over time if available.

## 5) Security: Threat Model & Mitigations
- What this means: list assets → threats → what you did/will do to reduce risk.
- Attack surface: Kafka ingress, FastAPI `/recommend` and `/metrics`, model registry artifacts, GitHub Actions secrets.
- Model/data attacks: rating spam / poisoning on `{team}.rate`; probing/DoS on `/recommend`.
- Mitigations:
  - Kafka SASL_SSL, schema validation, and consumer group isolation.
  - Rate-limit `/recommend`; validate query params; reject overly large `k`.
  - Artifact integrity: sha256 + versioned `meta.json`; restrict registries to team.
  - GH Actions: env-scoped secrets; no secrets in logs; pinned Docker base images.
  - Monitoring: alert on spike in requests/user or schema errors.

## 6) Security Analysis (telemetry)
Export recent `watch` or `rate` events to JSONL and run:
```bash
python scripts/security_anomaly_scan.py \
  --events deliverables/evidence/rate_events.jsonl \
  --out deliverables/evidence/security/rate_anomalies.json
```
Report flagged users (if any) or state “null finding; no outliers beyond 3σ”. Also note `schema_errors` count as evidence of validation effectiveness.

## 7) Final Demo Assets
- What to show: live API call, dashboard, A/B status, model switch. Keep the link here.
- **Video (5–8 min)**: walkthrough live API call, Grafana dashboard, A/B status, and a hot model switch.
  - Link placeholder: `TODO: https://…`
- **Slide deck**: place `deliverables/milestone5/slides.pdf`.
  - Cover: architecture recap, fairness/security findings, experiment results, retrain cadence, next steps.
- **Live links**: API base URL, Grafana, registry image, latest GH Action run.

## 8) Reflection (1–2 pages)
- What to write: candid lessons learned; keep it specific.
- Hardest pieces (offset management, schema evolution, cold-start mitigation, backpressure).
- Fragilities and how to harden before prod (autoscaling, canary SLOs, rollback).
- If we redid it (tooling or design changes).
- Team process reflection (what worked, what didn’t).

Place the reflection text at the end of the PDF or as `deliverables/milestone5/reflection.md` for easy export.

---

### Evidence Pointers to Commit Before Submit
- `deliverables/evidence/reco_responses.jsonl` (Kafka export)
- `deliverables/evidence/fairness/reco_bias.json` (from fairness scan)
- `deliverables/evidence/security/rate_anomalies.json` (from security scan)
- `deliverables/milestone5/slides.pdf`
- Video link added to this report

Ensure all paths resolve relative to repo root when generating the final PDF.
