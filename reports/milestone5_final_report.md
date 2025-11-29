# Milestone 5 Report: Fairness, Security, Feedback Loops, and Final Demo

**Team MedicalAI**
**COT 6930 — AI & ML in Production**
**Florida Atlantic University • Fall 2025**
**Submission Date: November 2025**

**Repository**: https://github.com/mlops-group-proj/movie-recs
**Live API**: http://ec2-54-221-101-86.compute-1.amazonaws.com:8080
**Grafana**: http://ec2-54-221-101-86.compute-1.amazonaws.com:3000

---

## 1. Fairness Requirements & Metrics

### 1.1 Identified Harms

Our movie recommendation system can cause the following harms to stakeholders:

| Harm Type | Description | Affected Stakeholders |
|-----------|-------------|----------------------|
| **Quality-of-Service** | Popular item bias reduces discovery of niche content | Users with diverse tastes |
| **Economic** | Long-tail movies receive less exposure, reducing viewership | Independent filmmakers, niche content creators |
| **Representation** | Older/indie films underrepresented in recommendations | Classic film enthusiasts |
| **Allocation** | Low-activity users receive lower-quality (less personalized) recommendations | Cold-start users |

### 1.2 Fairness Requirements

| Level | Requirement | Metric | Target | Status |
|-------|-------------|--------|--------|--------|
| **System** | Limit head-item dominance | Tail share (% recs NOT in top 10%) | ≥ 70% | **PASS (78.8%)** |
| **System** | Diverse catalog exposure | Catalog coverage (unique items / total) | ≥ 40% | **NEAR (37.2%)** |
| **Model** | Equitable distribution | Gini coefficient of item exposures | ≤ 0.35 | **PASS (0.213)** |
| **Model** | Top-item cap | Top-10% popularity share | ≤ 30% | **PASS (21.2%)** |

---

## 2. Fairness Improvements

### 2.1 Collection-Phase Actions
- **Balanced sampling**: Oversample ratings for movies with < 50 ratings during training data preparation
- **Temporal diversity**: Stratified sampling by rating timestamp to avoid recency bias
- **Implicit signals**: Track browsing/search behavior for cold-start users, not just explicit ratings

### 2.2 Design-Phase Actions
- **Diversity re-ranking**: Apply MMR (Maximal Marginal Relevance) to penalize duplicate genres within recommendation lists
- **Exposure constraints**: Reserve 2-3 slots in top-10 recommendations for items outside top-20% popularity tier
- **Calibrated recommendations**: Match recommendation genre distribution to user's historical preferences

### 2.3 Monitoring-Phase Actions
- **Real-time Gini tracking**: Prometheus gauge `reco_exposure_gini` computed on rolling window
- **Tail share alerting**: Alert rule fires when `tail_share < 0.70` for 30+ minutes
- **A/B fairness comparison**: Per-variant Gini and coverage tracking in Grafana dashboard

---

## 3. Fairness Analysis (Telemetry Evidence)

We analyzed 200 recommendation requests (2,000 total item exposures) from production traffic.

### 3.1 Results Summary

| Metric | Observed Value | Threshold | Status |
|--------|----------------|-----------|--------|
| Total Recommendations | 2,000 | - | - |
| Unique Items Exposed | 1,446 | - | - |
| Catalog Coverage | 37.2% (1446/3883) | ≥ 40% | NEAR THRESHOLD |
| Gini Coefficient | 0.213 | ≤ 0.35 | **PASS** |
| Top-10% Popularity Share | 21.2% | ≤ 30% | **PASS** |
| Tail Share (bottom 90%) | 78.8% | ≥ 70% | **PASS** |

### 3.2 Segment Parity Analysis

| Segment | Request Count | Exposure Share | Deviation from Parity |
|---------|---------------|----------------|----------------------|
| Even user_ids | 100 | 50.0% | 0.0% |
| Odd user_ids | 100 | 50.0% | 0.0% |

**Interpretation**: Perfect parity between even/odd user segments indicates no systematic bias based on user_id (proxy for account creation order).

### 3.3 Conclusions

The NCF model **PASSES** most fairness requirements:
- Gini coefficient (0.213) is well below the 0.35 threshold
- Tail share (78.8%) exceeds the 70% target
- Top-10% items don't dominate (21.2% < 30% threshold)

**Gap**: Catalog coverage (37.2%) is slightly below the 40% target, suggesting we should implement exploration slots for long-tail items in the next iteration.

---

## 4. Feedback Loops

### 4.1 Loop 1: Popularity Echo Chamber

**Mechanism**: Popular items receive more recommendations → more user watches → more training signal → model learns stronger embeddings for popular items → even more recommendations.

```
Popular Item → Recommended More → More Watches → Stronger Embeddings → REPEAT
```

**Detection Metric**: Amplification factor = (% of recommendations) / (% of catalog)

| Popularity Tier | % of Catalog | % of Recommendations | Amplification |
|-----------------|--------------|---------------------|---------------|
| High (top 10%) | 3.7% | 21.3% | **5.70x** |
| Medium (10-50%) | 14.9% | 42.6% | 2.86x |
| Low (50-90%) | 14.9% | 29.0% | 1.94x |
| Tail (bottom 10%) | 3.7% | 7.2% | 1.94x |
| Zero exposure | 63.5% | 0% | 0.00x |

**Finding**: Top-tier items are amplified 5.7x, confirming moderate popularity echo chamber effect.

### 4.2 Loop 2: Tail Starvation

**Mechanism**: Long-tail items rarely recommended → no new user interactions → sparse/noisy embeddings → never surface in top-k → items become "dead" in the catalog.

```
Niche Item → Rarely Recommended → No New Ratings → Weak Embeddings → NEVER RECOMMENDED
```

**Detection Metric**: Starvation index = items with zero recommendations / total catalog

**Finding**: **63.5% starvation index** (2,437 out of 3,883 movies received zero exposure in our sample). This is a significant risk that requires active intervention.

### 4.3 Mitigation Strategies

1. **Exploration slots**: Reserve 2-3 positions in each recommendation list for random long-tail items
2. **Inverse propensity scoring**: Down-weight popular items during training
3. **Popularity-aware negative sampling**: Sample negatives proportional to inverse popularity
4. **Periodic diversity audits**: Alert when starvation index increases across retraining cycles

---

## 5. Security Threat Model

### 5.1 Attack Surface

| Component | Assets | Threats |
|-----------|--------|---------|
| **Kafka** | User events (watch/rate) | Message injection, tampering, flooding |
| **API** | Recommendation endpoint | Rate abuse, DoS, model extraction |
| **Model Registry** | Model artifacts | Unauthorized switch, model poisoning |
| **Training Pipeline** | Training data | Data poisoning via rating spam |

### 5.2 Key Threat: Rating Spam / Poisoning Attack

**Attack Description**: Adversary creates fake accounts and submits coordinated ratings to manipulate recommendations.

| Attack Type | Goal | Method |
|-------------|------|--------|
| **Promotion** | Boost target movie | 100 fake users rate target 5 stars |
| **Demotion** | Suppress competitor | Rate competitor 1 star from many accounts |
| **Profile Injection** | Influence embeddings | Build strategic rating profiles |

**Impact**: Target movie appears in 30%+ more recommendations after retraining, degrading user trust.

### 5.3 Mitigations Implemented

| Layer | Mitigation | Implementation |
|-------|-----------|----------------|
| **Kafka** | SASL/SSL authentication | Confluent Cloud enforced |
| **Kafka** | Schema validation | Pydantic + Avro validation in ingestor |
| **API** | Rate limiting | slowapi middleware (100 req/min/IP) |
| **API** | Input validation | Pydantic models, parameter bounds |
| **Training** | Anomaly detection | Flag users > mean + 3σ events |
| **Training** | Account age weighting | Down-weight new accounts in training |
| **Registry** | Checksum verification | SHA256 hash validation before model load |
| **Monitoring** | Spike alerts | Prometheus alerts on unusual event volumes |

---

## 6. Security Analysis (Telemetry Evidence)

We analyzed 1,094 rating events from `rate_events.jsonl` using our anomaly detection script.

### 6.1 Detection Results

| Metric | Value |
|--------|-------|
| Total Events | 1,094 |
| Unique Users | 193 |
| Schema Errors | 0 |
| Mean Events/User | 5.67 |
| Std Dev | 7.67 |
| Detection Threshold | 28.68 (mean + 3σ) |
| **Flagged Users** | **2** |

### 6.2 Flagged Accounts

| User ID | Event Count | Multiple of Avg | Risk Level |
|---------|-------------|-----------------|------------|
| **9999** | 100 | 17.64x | **HIGH** |
| **8888** | 50 | 8.82x | **MEDIUM** |

**Interpretation**: User 9999 submitted 100 events (17.6x average), strongly indicating automated/spam behavior. User 8888 is also suspicious at 8.8x average.

### 6.3 Recommended Actions

1. **Immediate**: Quarantine ratings from flagged users
2. **Short-term**: Exclude from next training cycle
3. **Investigation**: Review for coordination patterns
4. **Prevention**: Implement velocity limits (max 20 ratings/hour)

---

## 7. Final Demo Description

### 7.1 Demo Structure (5-8 minutes)

| Section | Owner | Duration | Content |
|---------|-------|----------|---------|
| 1. Intro & Architecture | Dan | 60s | Pipeline overview, component walkthrough |
| 2. Live API Demo | Arvin | 90s | Health check, recommendations, provenance |
| 3. Grafana Dashboard | Lakshmi | 90s | Metrics, alerts, Kafka monitoring |
| 4. A/B Testing & Model Switch | Krushal | 60s | Rollout status, hot swap demo |
| 5. Security & Wrap-up | Dan | 75s | Threat model, fairness findings, reflection |

### 7.2 Live Demo Commands

```bash
# Health check with model info
curl http://ec2-54-221-101-86.compute-1.amazonaws.com:8080/health

# Recommendation with provenance
curl "http://ec2-54-221-101-86.compute-1.amazonaws.com:8080/recommend/42?k=10" | jq

# Trace retrieval
curl "http://ec2-54-221-101-86.compute-1.amazonaws.com:8080/trace/{request_id}" | jq

# Rollout status
curl "http://ec2-54-221-101-86.compute-1.amazonaws.com:8080/rollout/status" | jq

# Model switch
curl -X POST "http://ec2-54-221-101-86.compute-1.amazonaws.com:8080/switch?model=v0.6"
```

### 7.3 Key Evidence to Show

1. **Provenance fields** in recommendation response
2. **Grafana dashboards**: Latency, error rate, Kafka lag
3. **AlertManager**: Slack integration for critical alerts
4. **Fairness metrics**: Gini = 0.213, Tail share = 78.8%
5. **Security scan**: 2 flagged spam accounts

---

## 8. Reflection

### 8.1 Hardest Pieces

1. **Kafka Offset Management**: Ensuring exactly-once processing during retraining was challenging. We solved this with hourly S3 snapshots and replay capability.

2. **Schema Evolution**: Avro schema changes required careful migration. Adding provenance fields to `reco_response` broke downstream consumers until we made fields optional with defaults.

3. **Cold-Start Users**: Users with < 5 ratings get poor recommendations. We partially addressed this with popularity fallback but would benefit from content-based features.

4. **Monitoring Stack Integration**: Getting Prometheus to scrape Confluent Cloud metrics required understanding their authentication (Cloud API keys vs Kafka API keys) and setting `honor_timestamps: false`.

### 8.2 Fragilities & Hardening for Production

| Fragility | Risk | Hardening Plan |
|-----------|------|----------------|
| Single EC2 instance | No fault tolerance | Migrate to ECS Fargate with auto-scaling |
| In-memory trace store | Traces lost on restart | Integrate distributed tracing (Jaeger/X-Ray) |
| Manual canary promotion | Human error in rollouts | Automated canary analysis with rollback |
| S3 single region | Data loss risk | Enable cross-region replication |
| No feature store | Feature skew between training/serving | Implement Feast for consistent features |

### 8.3 If We Redid It

1. **Start with Feast**: Feature stores eliminate training-serving skew and enable feature sharing
2. **Use Kubernetes from day one**: EKS would give us better scaling and blue-green deployments
3. **Implement distributed tracing early**: Jaeger/Zipkin from the start would have saved debugging time
4. **CI/CD with canary automation**: ArgoCD + Flagger for automatic rollout analysis
5. **Better model evaluation harness**: A/B testing with statistical significance calculations built-in

### 8.4 Team Process Reflection

**What Worked:**
- Weekly standups kept everyone aligned on priorities
- Code reviews caught several edge cases before production
- Shared Slack channel for real-time debugging was invaluable
- Clear ownership of components (streaming, ML, infra, PM) avoided conflicts

**What Didn't Work:**
- Initial underestimation of Kafka complexity led to schedule slip
- Documentation lagged behind code changes
- Insufficient integration testing between components

**Key Takeaway**: Building a production ML system is about 20% modeling and 80% operational infrastructure. The "last mile" of deployment, monitoring, and reliability engineering is where most of the work lives.

---

## Appendix: Evidence Artifacts

| Evidence | Location |
|----------|----------|
| Fairness analysis results | `deliverables/evidence/analysis/fairness_analysis.json` |
| Security scan results | `deliverables/evidence/analysis/security_analysis.json` |
| Feedback loop analysis | `deliverables/evidence/analysis/feedback_loop_analysis.json` |
| Analysis visualizations | `deliverables/evidence/analysis/*.png` |
| Recommendation logs | `deliverables/evidence/reco_responses.jsonl` |
| Rating events | `deliverables/evidence/rate_events.jsonl` |
| Full fairness/security doc | `deliverables/milestone5/FAIRNESS_SECURITY_ANALYSIS.md` |
| Demo script | `deliverables/milestone5/DEMO_SCRIPT_DAN.md` |

---

## Summary Table

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Fairness requirements defined | COMPLETE | 4 metrics with thresholds |
| Fairness improvements documented | COMPLETE | Collection, design, monitoring actions |
| Fairness analysis conducted | COMPLETE | Gini 0.213 (PASS), Coverage 37.2% (NEAR) |
| Feedback loops identified | COMPLETE | Popularity echo (5.7x amplification), Tail starvation (63.5%) |
| Security threat model created | COMPLETE | Kafka/API/Registry/Training threats mapped |
| Security analysis conducted | COMPLETE | 2 spam accounts flagged (users 8888, 9999) |
| Final demo prepared | COMPLETE | 5-8 min video with live system walkthrough |
| Reflection written | COMPLETE | Lessons learned, fragilities, improvements |

---

**Team MedicalAI**
Daniel Zimmerman (PM) • Arvin Nourian (Data & Streaming) • LakshmiNarayana Latchireddi (ML) • Krushal Kalkani (Cloud)
