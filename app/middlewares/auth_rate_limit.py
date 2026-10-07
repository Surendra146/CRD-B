"""Bound authentication attempts per client and worker."""
from collections import OrderedDict, deque
from time import monotonic

from starlette.responses import JSONResponse


class AuthRateLimitMiddleware:
    def __init__(self, app):
        self.app = app
        self.attempts = OrderedDict()

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "").rstrip("/")
        limits = {"/api/auth/login": 30, "/api/auth/register": 10, "/api/auth/forgot-password": 10, "/api/auth/reset-password": 10}
        if scope["type"] == "http" and scope.get("method") == "POST" and path in limits:
            now = monotonic()
            key = ((scope.get("client") or ("unknown",))[0], path)
            attempts = self.attempts.setdefault(key, deque())
            self.attempts.move_to_end(key)
            while attempts and attempts[0] <= now - 60:
                attempts.popleft()
            if len(attempts) >= limits[path]:
                response = JSONResponse({"detail": "Too many authentication attempts. Try again in a minute"}, status_code=429, headers={"Retry-After": "60"})
                return await response(scope, receive, send)
            attempts.append(now)
            while len(self.attempts) > 5000:
                self.attempts.popitem(last=False)
        await self.app(scope, receive, send)
