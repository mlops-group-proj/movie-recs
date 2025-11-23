#!/bin/bash
# Test Feast metrics on deployed Render API

API_URL="https://movie-recommender-api-jobv.onrender.com"
PROM_URL="https://movie-recommender-prometheus.onrender.com"

echo "========================================================================="
echo "Testing Feast Feature Store on Deployed Render API"
echo "========================================================================="

echo -e "\n1. Checking API health..."
curl -s "$API_URL/healthz" | jq '{status, version}'

echo -e "\n2. Waiting for deployment to complete (checking for new features)..."
for i in {1..5}; do
    echo "   Attempt $i/5..."
    RESPONSE=$(curl -s "$API_URL/recommend/1?k=3")

    # Check if recommendations field exists (new feature)
    if echo "$RESPONSE" | jq -e '.recommendations' > /dev/null 2>&1; then
        echo "   New code detected! Recommendations field found."
        echo "$RESPONSE" | jq '.recommendations[0:2]'
        break
    else
        echo "   Old code still running. Waiting 30s..."
        if [ $i -lt 5 ]; then
            sleep 30
        fi
    fi
done

echo -e "\n3. Generating traffic to populate Feast metrics..."
for i in {1..50}; do
    curl -s "$API_URL/recommend/$i?k=10" > /dev/null
    if [ $((i % 10)) -eq 0 ]; then
        echo -n "."
    fi
done
echo " Done! (50 requests sent)"

echo -e "\n4. Checking Feast metrics on Prometheus..."
echo "   Feature retrieval latency:"
curl -s "$PROM_URL/api/v1/query?query=feature_retrieval_latency_seconds_count" | \
    jq -r '.data.result[] | "\(.metric.feature_type): \(.value[1]) lookups"' 2>/dev/null || \
    echo "   (Not available yet - may need more time for deployment)"

echo -e "\n   Feature coverage:"
curl -s "$PROM_URL/api/v1/query?query=feature_coverage_ratio" | \
    jq -r '.data.result[] | "\(.metric.feature_type): \(.value[1] * 100)% coverage"' 2>/dev/null || \
    echo "   (Not available yet)"

echo -e "\n   Feature retrieval total:"
curl -s "$PROM_URL/api/v1/query?query=feature_retrieval_total" | \
    jq -r '.data.result[] | "\(.metric.feature_type) [\(.metric.status)]: \(.value[1]) requests"' 2>/dev/null || \
    echo "   (Not available yet)"

echo -e "\n5. Sample recommendation with titles:"
curl -s "$API_URL/recommend/1?k=5" | jq '{
    user_id,
    model,
    recommendations: .recommendations[0:3]
}'

echo -e "\n========================================================================="
echo "Deployment Check Complete!"
echo "========================================================================="
echo ""
echo "Next steps:"
echo "1. Open Grafana: https://movie-recommender-grafana.onrender.com"
echo "2. Go to Dashboards → Import"
echo "3. Upload: grafana/dashboards/feast_feature_store.json"
echo "4. View the populated Feast metrics dashboard"
echo ""
echo "If metrics show '(Not available yet)', wait a few minutes for:"
echo "- Render deployment to complete"
echo "- Prometheus to scrape the new metrics"
echo "- Then run this script again"
