"""
Rate limiting middleware for Simposter API endpoints.

Implements sliding window rate limiting to prevent abuse and ensure
fair resource allocation across API requests.
"""

import time
from collections import defaultdict, deque
from typing import Dict, Deque, Tuple
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
import logging

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding window rate limiter middleware.

    Tracks requests per client IP and enforces configurable rate limits
    for different endpoint categories.
    """

    def __init__(self, app, default_limit: int = 60, window_seconds: int = 60):
        """
        Initialize rate limiter.

        Args:
            app: FastAPI application
            default_limit: Default requests allowed per window
            window_seconds: Time window in seconds
        """
        super().__init__(app)
        self.default_limit = default_limit
        self.window_seconds = window_seconds

        # Store request timestamps per client IP and endpoint
        # Format: {(client_ip, endpoint_pattern): deque([timestamp1, timestamp2, ...])}
        self.request_history: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)

        # Endpoint-specific limits (requests per window)
        self.endpoint_limits = {
            # Expensive rendering operations
            "/api/preview": 30,
            "/api/save": 20,
            "/api/plexsend": 20,
            "/api/batch": 5,  # Very expensive

            # Library operations
            "/api/scan-library": 5,
            "/api/movies": 100,
            "/api/tv-shows": 100,

            # Moderate operations
            "/api/tmdb": 40,  # Match TMDB's own limit
            "/api/tvdb": 20,  # Match TVDB's limit
            "/api/presets": 50,
            "/api/templates": 50,

            # Webhook (external trigger)
            "/api/webhook": 10,

            # Settings and metadata
            "/api/ui-settings": 30,
            "/api/logs": 20,
            "/api/history": 30,
        }

    def _get_endpoint_pattern(self, path: str) -> str:
        """
        Extract endpoint pattern from request path.

        Converts paths like /api/movie/123/tmdb to /api/movie for matching.

        Args:
            path: Request path

        Returns:
            Endpoint pattern for rate limit matching
        """
        # Remove trailing slash
        path = path.rstrip('/')

        # Extract base API path (first 2-3 segments)
        parts = path.split('/')

        if len(parts) >= 3 and parts[1] == 'api':
            # For /api/movie/123/tmdb -> /api/movie
            # For /api/preview -> /api/preview
            if len(parts) >= 4 and parts[3].isdigit():
                return f"/{parts[1]}/{parts[2]}"
            elif len(parts) >= 3:
                return f"/{parts[1]}/{parts[2]}"

        return path

    def _get_limit_for_endpoint(self, endpoint: str) -> int:
        """
        Get rate limit for specific endpoint.

        Args:
            endpoint: Endpoint pattern

        Returns:
            Requests allowed per window
        """
        # Check for exact match
        if endpoint in self.endpoint_limits:
            return self.endpoint_limits[endpoint]

        # Check for prefix match
        for pattern, limit in self.endpoint_limits.items():
            if endpoint.startswith(pattern):
                return limit

        return self.default_limit

    def _clean_old_requests(self, timestamps: Deque[float], current_time: float):
        """
        Remove timestamps outside the current window.

        Args:
            timestamps: Deque of request timestamps
            current_time: Current timestamp
        """
        cutoff = current_time - self.window_seconds

        # Remove old timestamps from the left (oldest)
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()

    def _get_client_ip(self, request: Request) -> str:
        """
        Extract client IP from request, handling proxies.

        Args:
            request: FastAPI request

        Returns:
            Client IP address
        """
        # Check X-Forwarded-For header (proxy/load balancer)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take first IP in chain (original client)
            return forwarded_for.split(",")[0].strip()

        # Check X-Real-IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

        # Fall back to direct connection IP
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next):
        """
        Process request and enforce rate limits.

        Args:
            request: Incoming request
            call_next: Next middleware in chain

        Returns:
            Response from next middleware or rate limit error
        """
        # Skip rate limiting for non-API routes
        if not request.url.path.startswith("/api"):
            return await call_next(request)

        # Get client identifier and endpoint
        client_ip = self._get_client_ip(request)
        endpoint = self._get_endpoint_pattern(request.url.path)
        limit = self._get_limit_for_endpoint(endpoint)

        # Get or create request history for this client/endpoint
        key = (client_ip, endpoint)
        timestamps = self.request_history[key]

        # Clean old requests outside window
        current_time = time.time()
        self._clean_old_requests(timestamps, current_time)

        # Check if limit exceeded
        if len(timestamps) >= limit:
            # Calculate retry-after time
            oldest_in_window = timestamps[0]
            retry_after = int(self.window_seconds - (current_time - oldest_in_window)) + 1

            logger.warning(
                f"Rate limit exceeded for {client_ip} on {endpoint} "
                f"({len(timestamps)}/{limit} requests in {self.window_seconds}s)"
            )

            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "Rate limit exceeded",
                    "limit": limit,
                    "window_seconds": self.window_seconds,
                    "retry_after": retry_after
                },
                headers={"Retry-After": str(retry_after)}
            )

        # Record this request
        timestamps.append(current_time)

        # Add rate limit headers to response
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(limit - len(timestamps))
        response.headers["X-RateLimit-Reset"] = str(int(timestamps[0] + self.window_seconds)) if timestamps else str(int(current_time + self.window_seconds))

        return response


def create_rate_limiter(
    default_limit: int = 60,
    window_seconds: int = 60
) -> RateLimitMiddleware:
    """
    Factory function to create rate limiter with custom settings.

    Args:
        default_limit: Default requests per window
        window_seconds: Time window in seconds

    Returns:
        Configured RateLimitMiddleware instance
    """
    return lambda app: RateLimitMiddleware(app, default_limit, window_seconds)
