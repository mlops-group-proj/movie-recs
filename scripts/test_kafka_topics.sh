#!/bin/bash

# Load environment variables
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
set -a
source "$SCRIPT_DIR/../.env"
set +a

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to test a topic
test_topic() {
    local topic="$KAFKA_TEAM.$1"
    echo -e "\n${GREEN}Testing topic: $topic${NC}"
    
    # Try to produce a message
    echo "Producing test message..."
    message="Test message for $topic at $(date -Iseconds)"
    echo "$message" | docker run --rm -i \
        -e KAFKA_BOOTSTRAP -e KAFKA_API_KEY -e KAFKA_API_SECRET \
        edenhill/kcat:1.7.0 -P \
        -b "$KAFKA_BOOTSTRAP" \
        -X security.protocol=SASL_SSL \
        -X sasl.mechanisms=PLAIN \
        -X sasl.username="$KAFKA_API_KEY" \
        -X sasl.password="$KAFKA_API_SECRET" \
        -t "$topic"
    
    if [ $? -eq 0 ]; then
        echo "✓ Successfully produced message to $topic"
    else
        echo -e "${RED}✗ Failed to produce message to $topic${NC}"
        return 1
    fi
    
    # Try to consume the message with a 5-second timeout
    echo "Consuming messages (last 5)..."
    timeout 5s docker run --rm \
        -e KAFKA_BOOTSTRAP -e KAFKA_API_KEY -e KAFKA_API_SECRET \
        edenhill/kcat:1.7.0 -C \
        -b "$KAFKA_BOOTSTRAP" \
        -X security.protocol=SASL_SSL \
        -X sasl.mechanisms=PLAIN \
        -X sasl.username="$KAFKA_API_KEY" \
        -X sasl.password="$KAFKA_API_SECRET" \
        -t "$topic" \
        -o end -c 5 -e
    
    if [ $? -eq 0 ]; then
        echo "✓ Successfully consumed from $topic"
    else
        echo -e "${RED}✗ Failed to consume from $topic${NC}"
        return 1
    fi
}

# Test all topics
topics=("watch" "rate" "reco_requests" "reco_responses")
failed=0

echo "Starting Kafka topic connectivity tests..."
echo "Using bootstrap server: $KAFKA_BOOTSTRAP"
echo "Team name: $KAFKA_TEAM"

for topic in "${topics[@]}"; do
    if ! test_topic "$topic"; then
        ((failed++))
    fi
done

echo -e "\n=== Test Summary ==="
if [ $failed -eq 0 ]; then
    echo -e "${GREEN}✓ All topics tested successfully!${NC}"
else
    echo -e "${RED}✗ $failed topic(s) had errors${NC}"
fi