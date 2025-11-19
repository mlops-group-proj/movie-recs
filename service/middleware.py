"""FastAPI middleware for request tracking and provenance logging.

Provides:
- Request ID generation and injection
- Context-aware logging with request metadata
- Request/response logging with provenance fields
- In-memory trace storage (simple implementation)
"""

from __future__ import annotations

import time
import uuid
import logging
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Callable, Dict, Any, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# Context variable for storing request-level provenance data
_request_context: ContextVar[Dict[str, Any]] = ContextVar("request_context", default={})

# In-memory trace store (LRU with max 1000 entries)
# In production, use a distributed tracing system like Jaeger, Zipkin, etc.
_trace_store: OrderedDict[str, Dict[str, Any]] = OrderedDict()
MAX_TRACES = 1000

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware to inject request_id into every request and response."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate or extract request ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Store in request state for access in route handlers
        request.state.request_id = request_id

        # Set context for this request
        ctx = {
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "timestamp": time.time(),
        }
        _request_context.set(ctx)

        # Log incoming request
        logger.info(
            f"[{request_id}] {request.method} {request.url.path}",
            extra={"request_id": request_id, "path": request.url.path, "method": request.method}
        )

        # Process request
        start_time = time.time()
        response = await call_next(request)
        latency = time.time() - start_time

        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id

        # Log response
        logger.info(
            f"[{request_id}] {response.status_code} {latency*1000:.2f}ms",
            extra={
                "request_id": request_id,
                "status_code": response.status_code,
                "latency_ms": latency * 1000
            }
        )

        return response


def get_request_context() -> Dict[str, Any]:
    """Get the current request context (request_id, timestamp, etc.)."""
    return _request_context.get()


def get_request_id() -> Optional[str]:
    """Get the current request ID from context."""
    ctx = _request_context.get()
    return ctx.get("request_id") if ctx else None


@contextmanager
def log_context(**kwargs):
    """Context manager to temporarily add fields to logging context."""
    ctx = _request_context.get().copy()
    ctx.update(kwargs)
    token = _request_context.set(ctx)
    try:
        yield
    finally:
        _request_context.reset(token)


def store_trace(request_id: str, trace_data: Dict[str, Any]) -> None:
    """Store trace data for a request.

    Args:
        request_id: Unique request identifier
        trace_data: Dictionary containing trace/provenance information
    """
    global _trace_store

    # Add to store
    _trace_store[request_id] = {
        **trace_data,
        "stored_at": time.time()
    }

    # Maintain max size (LRU eviction)
    if len(_trace_store) > MAX_TRACES:
        _trace_store.popitem(last=False)  # Remove oldest


def get_trace(request_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve trace data for a request.

    Args:
        request_id: Unique request identifier

    Returns:
        Trace data dictionary if found, None otherwise
    """
    return _trace_store.get(request_id)
