#!/usr/bin/env python3
"""Register JSON schemas for all Kafka topics in Confluent Schema Registry."""

import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

# Schema Registry configuration
SR_URL = os.environ.get("SCHEMA_REGISTRY_URL")
SR_API_KEY = os.environ.get("SCHEMA_REGISTRY_API_KEY")
SR_API_SECRET = os.environ.get("SCHEMA_REGISTRY_API_SECRET")
KAFKA_TEAM = os.environ.get("KAFKA_TEAM", "myteam")

# Avro Schemas for each topic
SCHEMAS = {
    f"{KAFKA_TEAM}.watch-value": {
        "schema": json.dumps({
            "type": "record",
            "name": "WatchEvent",
            "namespace": "com.movierecommender",
            "fields": [
                {"name": "user_id", "type": "int"},
                {"name": "movie_id", "type": "int"},
                {"name": "timestamp", "type": "string"}
            ]
        }),
        "schemaType": "AVRO"
    },
    f"{KAFKA_TEAM}.rate-value": {
        "schema": json.dumps({
            "type": "record",
            "name": "RateEvent",
            "namespace": "com.movierecommender",
            "fields": [
                {"name": "user_id", "type": "int"},
                {"name": "movie_id", "type": "int"},
                {"name": "rating", "type": "double"},
                {"name": "timestamp", "type": "string"}
            ]
        }),
        "schemaType": "AVRO"
    },
    f"{KAFKA_TEAM}.reco_requests-value": {
        "schema": json.dumps({
            "type": "record",
            "name": "RecoRequest",
            "namespace": "com.movierecommender",
            "fields": [
                {"name": "user_id", "type": "int"},
                {"name": "timestamp", "type": "string"}
            ]
        }),
        "schemaType": "AVRO"
    },
    f"{KAFKA_TEAM}.reco_responses-value": {
        "schema": json.dumps({
            "type": "record",
            "name": "RecoResponse",
            "namespace": "com.movierecommender",
            "fields": [
                {"name": "user_id", "type": "int"},
                {"name": "movie_ids", "type": {"type": "array", "items": "int"}},
                {"name": "scores", "type": {"type": "array", "items": "double"}},
                {"name": "timestamp", "type": "string"}
            ]
        }),
        "schemaType": "AVRO"
    }
}

def register_schema(subject: str, schema_def: dict) -> dict:
    """Register a schema in Confluent Schema Registry."""
    url = f"{SR_URL}/subjects/{subject}/versions"
    headers = {"Content-Type": "application/vnd.schemaregistry.v1+json"}

    response = requests.post(
        url,
        auth=(SR_API_KEY, SR_API_SECRET),
        headers=headers,
        json=schema_def
    )

    return {
        "subject": subject,
        "status_code": response.status_code,
        "response": response.json() if response.ok else response.text
    }

def main():
    print("=" * 60)
    print("Confluent Schema Registry - JSON Schema Registration")
    print("=" * 60)

    # Check credentials
    if not all([SR_URL, SR_API_KEY, SR_API_SECRET]):
        print("\nERROR: Missing Schema Registry credentials.")
        print("Please set the following in your .env file:")
        print("  SCHEMA_REGISTRY_URL=https://psrc-xxxxx.region.aws.confluent.cloud")
        print("  SCHEMA_REGISTRY_API_KEY=your-key")
        print("  SCHEMA_REGISTRY_API_SECRET=your-secret")
        print("\nTo get these credentials:")
        print("1. Go to Confluent Cloud -> Your Environment")
        print("2. Click 'Schema Registry' in the right panel")
        print("3. Click 'API credentials' and create a new key")
        return

    print(f"\nSchema Registry: {SR_URL}")
    print(f"Registering {len(SCHEMAS)} schemas...")
    print()

    results = []
    for subject, schema_def in SCHEMAS.items():
        print(f"Registering: {subject}")
        result = register_schema(subject, schema_def)
        results.append(result)

        if result["status_code"] == 200:
            schema_id = result["response"].get("id", "?")
            print(f"  -> Success (schema ID: {schema_id})")
        else:
            print(f"  -> Failed: {result['response']}")

    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)

    success = sum(1 for r in results if r["status_code"] == 200)
    print(f"Registered: {success}/{len(SCHEMAS)} schemas")

    if success == len(SCHEMAS):
        print("\nAll schemas registered successfully!")
        print("Your topics now have data contracts enforced.")
    else:
        print("\nSome schemas failed to register. Check the errors above.")

if __name__ == "__main__":
    main()
