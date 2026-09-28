"""Rate limiting em memória para as rotas REST (janela deslizante simples)."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class RateLimiter:
    """Limita ``max_requests`` por ``window_seconds`` por chave (IP)."""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window = window_seconds
        self._hits: dict[str, Deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self._hits[key]
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) >= self.max_requests:
            return False
        bucket.append(now)
        return True

    def reset(self) -> None:
        self._hits.clear()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Aplica rate limiting apenas às rotas ``/api/``."""

    def __init__(self, app, limiter: RateLimiter) -> None:  # noqa: ANN001
        super().__init__(app)
        self.limiter = limiter

    async def dispatch(self, request: Request, call_next):  # noqa: ANN001
        if request.url.path.startswith("/api/"):
            client = request.client.host if request.client else "unknown"
            if not self.limiter.allow(client):
                return JSONResponse(
                    {"detail": "Limite de requisições excedido. Aguarde um instante."},
                    status_code=429,
                )
        return await call_next(request)
