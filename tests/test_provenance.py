"""Unit tests for provenance logging and tracing."""

import pytest
import uuid
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

from service.middleware import (
    get_request_id,
    get_request_context,
    store_trace,
    get_trace,
    _trace_store
)


class TestMiddleware:
    """Tests for request ID middleware and context management."""

    def test_store_and_retrieve_trace(self):
        """Test storing and retrieving trace data."""
        request_id = str(uuid.uuid4())
        trace_data = {
            "user_id": 123,
            "model_version": "v0.3",
            "git_sha": "abc123",
            "latency_ms": 50
        }

        # Store trace
        store_trace(request_id, trace_data)

        # Retrieve trace
        retrieved = get_trace(request_id)
        assert retrieved is not None
        assert retrieved["user_id"] == 123
        assert retrieved["model_version"] == "v0.3"
        assert retrieved["git_sha"] == "abc123"
        assert "stored_at" in retrieved  # Automatically added

    def test_get_nonexistent_trace(self):
        """Test retrieving a trace that doesn't exist."""
        fake_id = str(uuid.uuid4())
        result = get_trace(fake_id)
        assert result is None

    def test_trace_store_lru_eviction(self):
        """Test that trace store evicts oldest entries when full."""
        from service.middleware import MAX_TRACES, _trace_store

        # Clear store
        _trace_store.clear()

        # Fill beyond max
        for i in range(MAX_TRACES + 100):
            request_id = f"request_{i}"
            store_trace(request_id, {"index": i})

        # Should not exceed max size
        assert len(_trace_store) <= MAX_TRACES

        # Oldest entries should be evicted
        assert get_trace("request_0") is None
        assert get_trace("request_1") is None

        # Recent entries should still exist
        recent_id = f"request_{MAX_TRACES + 50}"
        assert get_trace(recent_id) is not None


class TestProvenanceIntegration:
    """Integration tests for provenance in API responses."""

    @pytest.fixture
    def client(self):
        """Create a test client for the API."""
        # Import here to avoid circular dependencies
        from service.app import app
        return TestClient(app)

    def test_recommend_includes_provenance(self, client):
        """Test that /recommend endpoint includes provenance fields."""
        response = client.get("/recommend/123?k=5")

        assert response.status_code == 200
        data = response.json()

        # Check main fields
        assert "user_id" in data
        assert "model" in data
        assert "items" in data

        # Check provenance fields
        assert "provenance" in data
        prov = data["provenance"]

        # Required provenance fields
        assert "request_id" in prov
        assert "timestamp" in prov
        assert "model_name" in prov
        assert "model_version" in prov
        assert "git_sha" in prov
        assert "data_snapshot_id" in prov
        assert "latency_ms" in prov

        # Verify types
        assert isinstance(prov["request_id"], str)
        assert isinstance(prov["timestamp"], int)
        assert isinstance(prov["latency_ms"], int)

    def test_recommend_response_has_request_id_header(self, client):
        """Test that responses include X-Request-ID header."""
        response = client.get("/recommend/456?k=10")

        assert response.status_code == 200
        assert "x-request-id" in response.headers
        request_id = response.headers["x-request-id"]
        assert len(request_id) > 0

        # Verify request_id in response body matches header
        data = response.json()
        assert data["provenance"]["request_id"] == request_id

    def test_trace_endpoint_retrieves_stored_trace(self, client):
        """Test that /trace endpoint returns stored trace data."""
        # First, make a recommendation request
        rec_response = client.get("/recommend/789?k=5")
        assert rec_response.status_code == 200

        # Extract request_id
        data = rec_response.json()
        request_id = data["provenance"]["request_id"]

        # Now retrieve the trace
        trace_response = client.get(f"/trace/{request_id}")
        assert trace_response.status_code == 200

        trace_data = trace_response.json()
        assert trace_data["request_id"] == request_id
        assert "trace" in trace_data

        trace = trace_data["trace"]
        assert "model_version" in trace
        assert "git_sha" in trace
        assert "data_snapshot_id" in trace
        assert "user_id" in trace
        assert trace["user_id"] == 789

    def test_trace_endpoint_404_for_nonexistent_id(self, client):
        """Test that /trace returns 404 for unknown request_id."""
        fake_id = str(uuid.uuid4())
        response = client.get(f"/trace/{fake_id}")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_provenance_includes_container_digest(self, client):
        """Test that container_image_digest is included if available."""
        # Set environment variable
        import os
        os.environ["CONTAINER_IMAGE_DIGEST"] = "sha256:abcdef123456"

        response = client.get("/recommend/100?k=3")
        assert response.status_code == 200

        data = response.json()
        prov = data["provenance"]

        # Should include container digest from environment or metadata
        assert "container_image_digest" in prov

        # Clean up
        del os.environ["CONTAINER_IMAGE_DIGEST"]

    def test_custom_request_id_header_preserved(self, client):
        """Test that custom X-Request-ID headers are preserved."""
        custom_id = "custom-request-12345"

        response = client.get(
            "/recommend/111?k=5",
            headers={"X-Request-ID": custom_id}
        )

        assert response.status_code == 200

        # Response should use the custom request ID
        assert response.headers["x-request-id"] == custom_id

        data = response.json()
        assert data["provenance"]["request_id"] == custom_id


class TestAvroSchemaCompliance:
    """Tests for Avro schema compliance (structure validation)."""

    def test_provenance_fields_match_avro_schema(self):
        """Verify response structure matches updated Avro schema."""
        # Import here to avoid issues
        from service.app import app
        client = TestClient(app)

        response = client.get("/recommend/555?k=10")
        assert response.status_code == 200

        data = response.json()
        prov = data["provenance"]

        # Fields defined in reco_response.avsc
        required_fields = [
            "request_id",       # string
            "timestamp",        # long (we use int milliseconds)
            "model_name",       # string
            "model_version",    # string
            "git_sha",          # string
            "data_snapshot_id", # string
            "container_image_digest",  # nullable string
            "latency_ms"        # int
        ]

        for field in required_fields:
            assert field in prov, f"Missing required field: {field}"

        # Type checks
        assert isinstance(prov["request_id"], str)
        assert isinstance(prov["timestamp"], int)
        assert isinstance(prov["model_name"], str)
        assert isinstance(prov["model_version"], str)
        assert isinstance(prov["git_sha"], str)
        assert isinstance(prov["data_snapshot_id"], str)
        assert isinstance(prov["latency_ms"], int)
        # container_image_digest can be None or str
        assert prov["container_image_digest"] is None or isinstance(prov["container_image_digest"], str)
