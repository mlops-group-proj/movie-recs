# Deliverables Generation Guide

**Last Updated**: 2025-11-19
**Owner**: MLOps Team

---

## Overview

This guide explains how to generate the complete deliverables package for submission. The process is automated through a series of Python scripts that:

1. Calculate availability from Prometheus metrics
2. Verify model update requirements
3. Collect all evidence
4. Package everything for PDF generation

---

## Prerequisites

- **System Running**: All Docker containers must be running (`docker compose up -d`)
- **Prometheus Accessible**: http://localhost:9090
- **API Accessible**: http://localhost:8080
- **Historical Data**: At least 72 hours of metrics in Prometheus
- **Model Updates**: At least 2 model switches must have occurred

---

## Quick Start

### Complete Workflow (Automated)

```bash
# 1. Ensure services are running
docker compose up -d

# 2. Collect all evidence
python scripts/collect_evidence.py --output evidence/

# 3. Package for submission
python scripts/package_deliverables.py --output deliverables/ --evidence evidence/

# 4. Review the package
cat deliverables/DELIVERABLES_CHECKLIST.txt
```

The complete package will be in `deliverables/` directory.

---

## Individual Scripts

### 1. Calculate Availability

**Script**: `scripts/calculate_availability.py`

**Purpose**: Query Prometheus and calculate API availability percentage.

#### Usage

```bash
# Calculate 72-hour availability (before submission)
python scripts/calculate_availability.py --hours 72

# Calculate 144-hour availability (after submission)
python scripts/calculate_availability.py --hours 144

# Custom time window
python scripts/calculate_availability.py \
  --start 2025-11-18T00:00:00Z \
  --end 2025-11-25T23:59:59Z

# Output as JSON
python scripts/calculate_availability.py --hours 72 --format json --output availability_72h.json
```

#### Output Example

```
╔══════════════════════════════════════════════════════════════════╗
║                  API AVAILABILITY REPORT                          ║
╚══════════════════════════════════════════════════════════════════╝

Time Window:
  Start:     2025-11-16T12:00:00Z
  End:       2025-11-19T12:00:00Z
  Duration:  72.0 hours

Request Metrics:
  Total Requests:      15,432
  Successful (200):    14,891
  Errors (500):        541
  Availability:        96.49%

SLO Compliance:
  Required:            ≥70%
  Actual:              96.49%
  Status:              *  PASS
  Margin:              +26.49 percentage points

*  The API meets the ≥70% availability requirement!
```

#### Exit Codes

- `0`: Success (availability ≥70%)
- `1`: Failure (availability <70%)

---

### 2. Verify Model Updates

**Script**: `scripts/verify_model_updates.py`

**Purpose**: Verify that ≥2 model updates occurred within a 7-day window.

#### Usage

```bash
# Check last 7 days
python scripts/verify_model_updates.py

# Custom time window
python scripts/verify_model_updates.py \
  --start 2025-11-12T00:00:00Z \
  --end 2025-11-19T23:59:59Z

# Output as JSON
python scripts/verify_model_updates.py --format json --output model_updates.json
```

#### Output Example

```
╔══════════════════════════════════════════════════════════════════╗
║              MODEL UPDATE VERIFICATION REPORT                     ║
╚══════════════════════════════════════════════════════════════════╝

Observation Period:
  Start:     2025-11-12T00:00:00Z
  End:       2025-11-19T23:59:59Z
  Duration:  7 days

Model Switches Found:
  Total:     3 switches

All Model Switches:
  1. [2025-11-13T10:30:15Z] v0.2 → v0.3
  2. [2025-11-15T14:22:03Z] v0.3 → v0.2
  3. [2025-11-17T09:15:42Z] v0.2 → v0.3

Best 7-Day Window:
  Window:    2025-11-13T10:30:15Z to 2025-11-20T10:30:15Z
  Switches:  3 updates

Requirement Check:
  Required:  ≥2 updates within 7 days
  Actual:    3 updates
  Status:    *  PASS

*  The system meets the model update requirement!
```

#### Exit Codes

- `0`: Success (≥2 updates found)
- `1`: Failure (<2 updates)

---

### 3. Collect Evidence

**Script**: `scripts/collect_evidence.py`

**Purpose**: Collect all evidence files for the deliverables package.

#### Usage

```bash
# Collect all evidence to default directory (evidence/)
python scripts/collect_evidence.py

# Specify custom output directory
python scripts/collect_evidence.py --output my_evidence/

# Specify custom URLs
python scripts/collect_evidence.py \
  --api-url http://api.example.com:8080 \
  --prometheus-url http://prom.example.com:9090
```

#### What Gets Collected

The script collects:

1. **Availability Reports**
   - 72-hour calculation (JSON + text)
   - 144-hour calculation (JSON + text)

2. **Model Update Verification**
   - Verification report (JSON + text)

3. **API Samples**
   - `/healthz` response
   - `/recommend/{user_id}` sample
   - `/recommend/{user_id}` with full provenance
   - `/trace/{request_id}` sample
   - `/rollout/status` response
   - `/metrics` export

4. **Model Registry Info**
   - Summary of all model versions
   - Metadata for each version

5. **Git History**
   - Recent commits (last 50)
   - Current git SHA
   - Branch information

6. **System Info**
   - Docker Compose service status
   - Docker images list
   - Requirements files

7. **Log Samples**
   - API logs (last 500 lines)
   - Prometheus logs (last 200 lines)

8. **Evidence Summary**
   - `EVIDENCE_SUMMARY.json` - Complete index of all collected files

#### Directory Structure

```
evidence/
├── EVIDENCE_SUMMARY.json
├── availability/
│   ├── availability_72h.json
│   ├── availability_72h.txt
│   ├── availability_144h.json
│   └── availability_144h.txt
├── model_updates/
│   ├── model_updates_verification.json
│   └── model_updates_verification.txt
├── api_samples/
│   ├── healthz.json
│   ├── recommend_sample.json
│   ├── recommend_with_provenance.json
│   ├── trace_sample.json
│   ├── rollout_status.json
│   └── metrics.txt
├── model_registry/
│   └── versions_summary.json
├── git_history/
│   ├── commits.txt
│   ├── current_sha.txt
│   └── branches.txt
├── system_info/
│   ├── docker_services.txt
│   ├── docker_images.txt
│   └── reqs-*.txt
└── logs/
    ├── api_logs_sample.txt
    └── prometheus_logs_sample.txt
```

---

### 4. Package Deliverables

**Script**: `scripts/package_deliverables.py`

**Purpose**: Create final deliverables package with everything needed for submission.

#### Usage

```bash
# Package with default settings
python scripts/package_deliverables.py

# Specify directories
python scripts/package_deliverables.py \
  --output deliverables/ \
  --evidence evidence/
```

#### What Gets Packaged

The script creates a complete package including:

1. **Evidence** (from `collect_evidence.py`)
2. **Documentation**
   - README.md
   - API_REFERENCE.md
   - RUNBOOK.md
   - AB_TESTING_GUIDE.md
   - PROVENANCE_GUIDE.md

3. **Code Samples**
   - Key service files (app.py, loader.py, middleware.py, etc.)
   - Recommender implementation
   - Avro schemas
   - Configuration files

4. **Deliverables Checklist**
   - `DELIVERABLES_CHECKLIST.json` - Machine-readable checklist
   - `DELIVERABLES_CHECKLIST.txt` - Human-readable checklist

5. **Master README**
   - Complete package overview
   - Summary of all deliverables
   - Verification instructions

#### Final Package Structure

```
deliverables/
├── README.md                        # Master README
├── DELIVERABLES_CHECKLIST.txt       # Checklist
├── DELIVERABLES_CHECKLIST.json      # Checklist (JSON)
├── evidence/                        # All evidence
│   └── (same structure as from collect_evidence.py)
├── docs/                            # Documentation
│   ├── README.md
│   ├── API_REFERENCE.md
│   ├── RUNBOOK.md
│   ├── AB_TESTING_GUIDE.md
│   └── PROVENANCE_GUIDE.md
└── code_samples/                    # Key code files
    ├── service/
    ├── recommender/
    ├── stream/
    └── docker-compose.yml
```

---

## Complete Workflow Example

### Before Submission (72h window)

```bash
# 1. Start services (must be running for ≥72h)
docker compose up -d

# 2. During the 72h period, perform ≥2 model updates
curl -X POST "http://localhost:8080/rollout/update?strategy=fixed"
curl "http://localhost:8080/switch?model=v0.2"

# Wait some time...

curl "http://localhost:8080/switch?model=v0.3"

# 3. After 72h, collect evidence
python scripts/collect_evidence.py --output evidence_before_submission/

# 4. Check availability (should be ≥70%)
python scripts/calculate_availability.py --hours 72

# 5. Verify model updates (should have ≥2)
python scripts/verify_model_updates.py
```

### After Submission (144h window)

```bash
# Keep services running for 144h after submission

# After 144h, collect final evidence
python scripts/collect_evidence.py --output evidence_after_submission/

# Verify 144h availability
python scripts/calculate_availability.py --hours 144

# Package everything
python scripts/package_deliverables.py \
  --output final_deliverables/ \
  --evidence evidence_after_submission/

# Review the package
cat final_deliverables/README.md
cat final_deliverables/DELIVERABLES_CHECKLIST.txt
```

---

## Troubleshooting

### "No data found in Prometheus"

**Problem**: Prometheus doesn't have enough historical data

**Solutions**:
1. Check Prometheus is running: `curl http://localhost:9090/api/v1/targets`
2. Verify metrics are being scraped: `curl http://localhost:8080/metrics`
3. Ensure services have been running long enough
4. Check Prometheus retention period in `prometheus/prometheus.yml`

### "API not accessible"

**Problem**: Cannot reach API endpoints

**Solutions**:
```bash
# Check services are running
docker compose ps

# Restart if needed
docker compose restart api

# Check logs
docker compose logs api
```

### "Insufficient model updates"

**Problem**: <2 model updates found

**Solutions**:
```bash
# Perform additional model switches
curl "http://localhost:8080/switch?model=v0.2"
sleep 60
curl "http://localhost:8080/switch?model=v0.3"

# Verify switches are tracked
curl "http://localhost:8080/metrics" | grep model_switches_total
```

---

## Generating the PDF

Once you have the complete `deliverables/` package:

### Option 1: Using Markdown to PDF Tools

```bash
# Install pandoc
brew install pandoc  # macOS
apt-get install pandoc  # Linux

# Generate PDF
pandoc deliverables/README.md \
  -o deliverables.pdf \
  --toc \
  --pdf-engine=xelatex
```

### Option 2: Manual PDF Creation

1. Open `deliverables/README.md` in a markdown viewer
2. Include screenshots from `evidence/` directory
3. Add graphs from Grafana dashboards
4. Export as PDF

### Option 3: LaTeX

Create a LaTeX document that includes:
- Content from `deliverables/README.md`
- Tables from `DELIVERABLES_CHECKLIST.txt`
- Code snippets from `code_samples/`
- Evidence from `evidence/`

---

## Verification Checklist

Before submitting, verify:

- [ ] All services running for required time windows
- [ ] Availability ≥70% (check `availability/*.txt`)
- [ ] ≥2 model updates within 7 days (check `model_updates/*.txt`)
- [ ] All API samples collected (check `evidence/api_samples/`)
- [ ] Provenance fields present in responses
- [ ] Documentation complete (check `docs/`)
- [ ] Git history captured (check `evidence/git_history/`)
- [ ] Logs collected (check `evidence/logs/`)
- [ ] `DELIVERABLES_CHECKLIST.txt` shows all items * 

---

## Additional Resources

- [Main README](../README.md)
- [API Reference](API_REFERENCE.md)
- [Runbook](RUNBOOK.md)
- [A/B Testing Guide](AB_TESTING_GUIDE.md)
- [Provenance Guide](PROVENANCE_GUIDE.md)

---

**Generated by**: MLOps Team
**Last Updated**: 2025-11-19
