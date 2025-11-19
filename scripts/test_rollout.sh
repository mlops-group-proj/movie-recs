#!/bin/bash
# Test script for rollout and hot-swap functionality

set -e

API_URL="${API_URL:-http://localhost:8080}"
COLOR_GREEN='\033[0;32m'
COLOR_RED='\033[0;31m'
COLOR_BLUE='\033[0;34m'
COLOR_RESET='\033[0m'

echo -e "${COLOR_BLUE}=== Movie Recommender Rollout Test Script ===${COLOR_RESET}\n"

# Helper function for tests
test_endpoint() {
    local name="$1"
    local url="$2"
    local expected_status="${3:-200}"

    echo -n "Testing $name... "
    status=$(curl -s -o /dev/null -w "%{http_code}" "$url")

    if [ "$status" -eq "$expected_status" ]; then
        echo -e "${COLOR_GREEN}✓ PASS${COLOR_RESET} (HTTP $status)"
        return 0
    else
        echo -e "${COLOR_RED}✗ FAIL${COLOR_RESET} (expected $expected_status, got $status)"
        return 1
    fi
}

test_json_field() {
    local name="$1"
    local url="$2"
    local field="$3"
    local expected="$4"

    echo -n "Testing $name ($field)... "
    response=$(curl -s "$url")
    actual=$(echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin)${field})" 2>/dev/null || echo "ERROR")

    if [ "$actual" = "$expected" ]; then
        echo -e "${COLOR_GREEN}✓ PASS${COLOR_RESET} ($actual)"
        return 0
    else
        echo -e "${COLOR_RED}✗ FAIL${COLOR_RESET} (expected '$expected', got '$actual')"
        return 1
    fi
}

echo "1. Health Check"
test_endpoint "Healthz" "$API_URL/healthz"
echo

echo "2. Basic Endpoints"
test_endpoint "Metrics" "$API_URL/metrics"
test_endpoint "Recommend" "$API_URL/recommend/42?k=10"
echo

echo "3. Rollout Status"
test_endpoint "Rollout Status" "$API_URL/rollout/status"
curl -s "$API_URL/rollout/status" | python3 -m json.tool
echo

echo "4. Model Version Info"
echo "Current version:"
curl -s "$API_URL/healthz" | python3 -c "import sys, json; print(json.load(sys.stdin)['version'])"
echo

echo "5. Test Model Switch (if v0.2 exists)"
if [ -d "model_registry/v0.2" ]; then
    echo "Switching to v0.2..."
    curl -s "$API_URL/switch?model=v0.2" | python3 -m json.tool

    echo "Verifying switch..."
    test_json_field "Version after switch" "$API_URL/healthz" "['version']" "v0.2"

    echo "Switching back to v0.3..."
    curl -s "$API_URL/switch?model=v0.3" | python3 -m json.tool
    test_json_field "Version after rollback" "$API_URL/healthz" "['version']" "v0.3"
else
    echo "Skipping switch test (v0.2 not found)"
fi
echo

echo "6. Test Rollout Configuration Updates"
echo "Setting canary rollout (10%)..."
curl -s -X POST "$API_URL/rollout/update?strategy=canary&canary_version=v0.3&canary_percentage=10" | python3 -m json.tool

echo "Verifying rollout config..."
curl -s "$API_URL/rollout/status" | python3 -m json.tool

echo "Resetting to fixed strategy..."
curl -s -X POST "$API_URL/rollout/update?strategy=fixed" | python3 -m json.tool
echo

echo "7. Test Prometheus Metrics"
echo "Checking model version metrics..."
curl -s "$API_URL/metrics" | grep "model_version_info"

echo "Checking model switches..."
curl -s "$API_URL/metrics" | grep "model_switches_total"
echo

echo -e "${COLOR_GREEN}=== All Tests Complete ===${COLOR_RESET}"
echo
echo "Additional manual tests:"
echo "  - Check Grafana dashboard: http://localhost:3000"
echo "  - Check Prometheus: http://localhost:9090"
echo "  - View metrics: curl $API_URL/metrics"
