#!/bin/bash
# Test script for Feast feature store metrics

echo "==================================================================="
echo "Testing Feast Feature Store Metrics"
echo "==================================================================="

# 1. Test API health
echo -e "\n1. Testing API health..."
curl -s http://localhost:8080/healthz | jq '.'

# 2. Get recommendations (this will trigger feature lookups)
echo -e "\n2. Getting recommendations for user 123..."
curl -s "http://localhost:8080/recommend/123?k=10" | jq '{
  user_id,
  model,
  recommendations: .recommendations[0:3],
  variant
}'

# 3. Check Prometheus metrics for feature store
echo -e "\n3. Checking feature store metrics..."
curl -s http://localhost:8080/metrics | grep -E "feature_retrieval|feature_coverage"

# 4. Generate some traffic to populate metrics
echo -e "\n4. Generating traffic (20 requests)..."
for i in {1..20}; do
  curl -s "http://localhost:8080/recommend/$((100 + i))?k=10" > /dev/null
  echo -n "."
done
echo " Done!"

# 5. Check updated metrics
echo -e "\n5. Feature store metrics after traffic:"
echo "   Feature retrieval latency:"
curl -s http://localhost:8080/metrics | grep "feature_retrieval_latency_seconds_sum"

echo -e "\n   Feature coverage:"
curl -s http://localhost:8080/metrics | grep "feature_coverage_ratio"

echo -e "\n   Feature retrieval counts:"
curl -s http://localhost:8080/metrics | grep "feature_retrieval_total"

echo -e "\n==================================================================="
echo "Test complete!"
echo "==================================================================="
echo ""
echo "Next steps:"
echo "1. Open Grafana: http://localhost:3000"
echo "2. Import dashboard from: grafana/dashboards/feast_feature_store.json"
echo "3. View metrics in real-time"
