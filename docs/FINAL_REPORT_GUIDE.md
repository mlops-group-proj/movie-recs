# Final Report Generation Guide

This guide explains how to generate the complete Milestone 4 final report with all evidence, screenshots, and diagrams.

---

## Quick Start

```bash
# 1. Collect all evidence
python scripts/collect_evidence.py --output evidence/

# 2. Package deliverables
python scripts/package_deliverables.py --output deliverables/ --evidence evidence/

# 3. Generate report markdown
python scripts/generate_report.py --output reports/milestone4_report.md

# 4. Review the report
cat reports/milestone4_report.md
```

---

## Screenshots Required

The report includes placeholders for screenshots. Capture these before generating the PDF:

### 1. Grafana SLO Dashboard

**URL**: http://localhost:3000

**What to capture**:
- Overall dashboard view showing all SLO metrics
- Request rate panel
- P95 latency panel with SLO threshold line
- Error rate panel
- Availability gauge

**Save as**: `screenshots/grafana_slo_dashboard.png`

### 2. Prometheus Metrics

**URL**: http://localhost:9090

**What to capture**:
- Targets page showing healthy scraping (`/targets`)
- Graph showing availability query
- Graph showing model switches over time

**Save as**:
- `screenshots/prometheus_targets.png`
- `screenshots/prometheus_availability.png`
- `screenshots/prometheus_model_switches.png`

### 3. API Response with Provenance

**Command**:
```bash
curl "http://localhost:8080/recommend/123?k=10" | jq > screenshots/api_response.json
```

**Capture**: Terminal showing the formatted JSON with provenance fields highlighted

**Save as**: `screenshots/api_provenance_response.png`

### 4. Trace Retrieval Example

**Commands**:
```bash
# Get request_id
REQUEST_ID=$(curl -s "http://localhost:8080/recommend/456?k=5" | jq -r '.provenance.request_id')

# Retrieve trace
curl "http://localhost:8080/trace/$REQUEST_ID" | jq
```

**Save as**: `screenshots/trace_retrieval.png`

### 5. A/B Test Analysis

**Command**:
```bash
# First set up A/B test
curl -X POST "http://localhost:8080/rollout/update?strategy=ab_test&canary_version=v0.3"

# Generate traffic
for i in {1..2000}; do curl -s "http://localhost:8080/recommend/$i?k=10" > /dev/null; done

# Analyze
curl "http://localhost:8080/experiment/analyze?time_window_minutes=60" | jq
```

**Save as**: `screenshots/ab_test_results.png`

### 6. Model Switch Operation

**Commands**:
```bash
# Check current version
curl "http://localhost:8080/healthz" | jq

# Switch model
curl "http://localhost:8080/switch?model=v0.2" | jq

# Verify switch
curl "http://localhost:8080/healthz" | jq
```

**Save as**: `screenshots/model_switch.png`

### 7. Docker Services Running

**Command**:
```bash
docker compose ps
```

**Save as**: `screenshots/docker_services.png`

### 8. Availability Calculation

**Command**:
```bash
python scripts/calculate_availability.py --hours 72
```

**Save as**: `screenshots/availability_72h.png`

### 9. Model Updates Verification

**Command**:
```bash
python scripts/verify_model_updates.py
```

**Save as**: `screenshots/model_updates_verification.png`

### 10. Logs Showing Provenance

**Command**:
```bash
docker compose logs api --tail=50 | grep -A 5 "Recommendation success"
```

**Save as**: `screenshots/logs_provenance.png`

---

## Adding Screenshots to Report

### Option 1: Markdown with Image Links

Edit `reports/milestone4_report.md` and add image references:

```markdown
### Grafana SLO Dashboard

![Grafana SLO Dashboard](../screenshots/grafana_slo_dashboard.png)

The dashboard shows...
```

### Option 2: Pandoc with Embedded Images

When converting to PDF, Pandoc will automatically embed images:

```bash
pandoc reports/milestone4_report.md \
  -o milestone4_report.pdf \
  --toc \
  --pdf-engine=xelatex \
  --resource-path=.:screenshots
```

---

## Converting to PDF

### Method 1: Pandoc (Recommended)

```bash
# Install pandoc
brew install pandoc          # macOS
apt-get install pandoc      # Linux

# Generate PDF with table of contents
pandoc reports/milestone4_report.md \
  -o milestone4_report.pdf \
  --toc \
  --toc-depth=2 \
  --pdf-engine=xelatex \
  --variable geometry:margin=1in \
  --variable fontsize=11pt \
  --highlight-style=tango
```

### Method 2: Markdown to HTML to PDF

```bash
# Convert to HTML first
pandoc reports/milestone4_report.md \
  -o milestone4_report.html \
  --standalone \
  --toc \
  --css=style.css

# Then print to PDF from browser
open milestone4_report.html
# File → Print → Save as PDF
```

### Method 3: Using Online Tools

1. Copy content from `reports/milestone4_report.md`
2. Paste into [StackEdit](https://stackedit.io/) or [Dillinger](https://dillinger.io/)
3. Export as PDF

---

## Report Customization

### Adding Your Own Sections

Edit `scripts/generate_report.py` and add new functions:

```python
def create_custom_section() -> str:
    return """
## My Custom Section

Your content here...

---
"""

# Then add to main():
report += create_custom_section()
```

### Updating Evidence

If you collect new evidence:

```bash
# Re-collect
python scripts/collect_evidence.py --output evidence/

# Re-package
python scripts/package_deliverables.py --output deliverables/

# Re-generate report
python scripts/generate_report.py --output reports/milestone4_report.md
```

---

## Final Checklist

Before submitting, verify:

- [ ] All services are running (`docker compose ps`)
- [ ] Availability ≥70% for required windows
- [ ] ≥2 model updates verified
- [ ] All screenshots captured
- [ ] Evidence collected (`evidence/` directory complete)
- [ ] Deliverables packaged (`deliverables/` directory complete)
- [ ] Report generated (`reports/milestone4_report.md`)
- [ ] PDF created and < 4 pages
- [ ] All code committed and pushed to GitHub
- [ ] Repository link included in report

---

## Example Complete Workflow

```bash
# Day 1: Start services (72h before submission)
docker compose up -d

# Perform model updates (spread over 7 days)
curl "http://localhost:8080/switch?model=v0.2"
# ... wait 2 days ...
curl "http://localhost:8080/switch?model=v0.3"

# Day 4: Collect evidence (72h after start)
python scripts/collect_evidence.py --output evidence/

# Verify requirements
python scripts/calculate_availability.py --hours 72
python scripts/verify_model_updates.py

# Capture all screenshots (follow guide above)
# ... capture screenshots ...

# Generate report
python scripts/generate_report.py --output reports/milestone4_report.md

# Add screenshots to report
# ... edit markdown to include images ...

# Package everything
python scripts/package_deliverables.py --output deliverables/

# Generate PDF
pandoc reports/milestone4_report.md -o milestone4_report.pdf --toc

# Review PDF (should be ≤4 pages)
open milestone4_report.pdf

# Submit!
```

---

## Troubleshooting

### "Pandoc not found"

```bash
# macOS
brew install pandoc basictex

# Ubuntu/Debian
sudo apt-get install pandoc texlive-xetex

# Verify
pandoc --version
```

### "PDF too large (>4 pages)"

**Solutions**:
- Use smaller screenshots
- Reduce margins: `--variable geometry:margin=0.75in`
- Use smaller font: `--variable fontsize=10pt`
- Remove less critical sections
- Use two-column layout: `--variable classoption=twocolumn`

### "Images not showing in PDF"

```bash
# Use absolute paths or --resource-path
pandoc report.md -o report.pdf --resource-path=/full/path/to/screenshots
```

### "Missing evidence files"

```bash
# Re-run collection
python scripts/collect_evidence.py --output evidence/

# Check evidence summary
cat evidence/EVIDENCE_SUMMARY.json | jq
```

---

## Additional Resources

- Main README: `../README.md`
- Deliverables README: `DELIVERABLES_README.md`
- API Reference: `API_REFERENCE.md`
- Pandoc Manual: https://pandoc.org/MANUAL.html

---

**Generated**: 2025-11-19
**Team**: MLOps Team
