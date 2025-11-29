# Demo Script - Dan's Sections

## SECTION 1: Introduction & Architecture Overview (~60-75 seconds)

### Opening (10 sec)
*[Screen: Title slide with team name and project logo]*

"Hi everyone, we're Team MedicalAI presenting our Movie Recommender System - a production-grade MLOps pipeline built for real-world deployment."

### Architecture Walkthrough (50 sec)
*[Screen: Architecture diagram showing the full pipeline]*

"Let me walk you through our end-to-end architecture:

**Data Ingestion Layer:**
- We consume user events from Confluent Cloud Kafka - specifically `watch`, `rate`, and recommendation request topics
- Our stream ingestor validates schemas using Avro and persists hourly snapshots to S3 as Parquet files
- This gives us exactly-once semantics and allows replay for retraining

**Model Training & Registry:**
- We train four model types: Popularity baseline, ItemCF, ALS collaborative filtering, and Neural Collaborative Filtering (NCF)
- Our NCF model leads with 13.7% Hit Rate at K=10 - roughly 3x better than popularity
- The model registry stores versioned artifacts with full provenance: git SHA, data snapshot hash, and offline metrics

**Serving Layer:**
- FastAPI serves recommendations on EC2 at around 35ms P50 latency
- We support hot model swaps, A/B testing, and canary rollouts without restart
- Prometheus scrapes metrics; Grafana displays dashboards

**Monitoring & Retraining:**
- GitHub Actions orchestrates scheduled retraining every Monday and Thursday
- Alerts fire to Slack when latency exceeds SLOs or error rates spike
- We also monitor Kafka consumer lag from Confluent Cloud directly

Now let me hand it off to [Next Person] who will show you the live system..."

---

## SECTION 5: Provenance, Security, Feedback Loops, & Wrap-up (~75-90 seconds)

### Provenance & Traceability (20 sec)
*[Screen: Show `/recommend` response with provenance fields, then `/trace` endpoint]*

"Every prediction carries full provenance metadata. Here you see `request_id`, `model_version`, `git_sha`, and `data_snapshot_id`. This lets us trace any recommendation back to the exact code commit and training data that produced it.

We can query our trace endpoint with any request ID and get the complete context - this is critical for debugging production issues and audit compliance."

### Feedback Loops Analysis (20 sec)
*[Screen: Show feedback loop diagram and amplification table from FAIRNESS_SECURITY_ANALYSIS.md]*

"We identified two feedback loops in our system:

First, **Popularity Echo Chamber**: popular items get recommended more, which generates more watches, which amplifies their training signal. Our analysis shows top-10% items have 5.7x amplification.

Second, **Tail Starvation**: 63.5% of our catalog - over 2,400 movies - received zero exposure in our sample. These items never get recommended, so users never discover them, and the model never learns to recommend them.

We mitigate this through diversity re-ranking and exposure quotas for long-tail items."

### Security Analysis (20 sec)
*[Screen: Show security analysis visualization with flagged users]*

"On security, our threat model covers Kafka injection, API rate abuse, and model poisoning attacks.

Our anomaly detection flagged two suspicious accounts: User 9999 with 100 rating events - that's 17.6x the average - and User 8888 with 50 events at 8.8x average. Both exceed our 3-sigma threshold and would be quarantined from training data.

We also use Kafka SASL/SSL, API rate limiting, and schema validation as defense layers."

### Key Learnings & Reflection (15 sec)
*[Screen: Final summary slide]*

"Looking back, our biggest challenges were Kafka offset management during retraining and handling cold-start users. If we did this again, we'd implement feature stores like Feast from day one and add distributed tracing with Jaeger.

Overall, building a production ML system is about 20% modeling and 80% operational infrastructure - monitoring, versioning, rollback, and observability."

### Closing (5 sec)
"Thank you! Our repo is at github.com/mlops-group-proj/movie-recs, and the API is live at our EC2 endpoint. Questions?"

---

## Demo Resources Quick Reference

### Live Endpoints for Demo
- **API Health**: `http://ec2-54-221-101-86.compute-1.amazonaws.com:8080/health`
- **Get Recommendations**: `http://ec2-54-221-101-86.compute-1.amazonaws.com:8080/recommend/42?k=10`
- **Provenance Trace**: `http://ec2-54-221-101-86.compute-1.amazonaws.com:8080/trace/{request_id}`
- **Grafana Dashboard**: `http://ec2-54-221-101-86.compute-1.amazonaws.com:3000` (admin/admin)
- **Prometheus**: `http://ec2-54-221-101-86.compute-1.amazonaws.com:9090`

### Key Numbers to Cite
- **NCF Hit Rate@10**: 13.7%
- **ALS Hit Rate@10**: 9.9%
- **P50 Latency**: ~35ms
- **Gini Coefficient**: 0.213 (PASS - threshold 0.35)
- **Catalog Coverage**: 37.2% (NEAR - threshold 40%)
- **Tail Share**: 78.8% (PASS - threshold 70%)
- **Starvation Index**: 63.5% of catalog with zero exposure
- **Flagged Spam Accounts**: 2 users (IDs 8888, 9999)
- **High-tier Amplification**: 5.7x

### Curl Commands for Live Demo
```bash
# Basic recommendation with provenance
curl -s "http://ec2-54-221-101-86.compute-1.amazonaws.com:8080/recommend/42?k=5" | jq

# Get trace for a request
REQUEST_ID=$(curl -s "http://ec2-54-221-101-86.compute-1.amazonaws.com:8080/recommend/123?k=5" | jq -r '.provenance.request_id')
curl -s "http://ec2-54-221-101-86.compute-1.amazonaws.com:8080/trace/$REQUEST_ID" | jq

# Check model version and rollout status
curl -s "http://ec2-54-221-101-86.compute-1.amazonaws.com:8080/rollout/status" | jq

# Health check with model info
curl -s "http://ec2-54-221-101-86.compute-1.amazonaws.com:8080/health" | jq
```

### Slides to Prepare
1. **Title Slide**: Team MedicalAI - Movie Recommender System
2. **Architecture Diagram**: Full pipeline from Kafka to API to Grafana
3. **Provenance Response**: Screenshot of `/recommend` JSON with provenance fields
4. **Feedback Loop Diagram**: Popularity echo chamber visualization
5. **Security Analysis**: Flagged users chart
6. **Summary Slide**: Key metrics, lessons learned, next steps
