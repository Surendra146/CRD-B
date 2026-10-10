"""Shared fixed-window Redis rate limits; fail closed when enabled."""
import hashlib
import time

from redis.asyncio import Redis
from starlette.responses import JSONResponse

from app.config.settings import get_settings
from app.services.security import decode_token

SCRIPT = """local count = redis.call('INCR', KEYS[1]); if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end; return count"""


class DistributedRateLimitMiddleware:
    def __init__(self, app):
        self.app = app
        self.redis = None

    async def __call__(self, scope, receive, send):
        settings = get_settings()
        if scope["type"] != "http" or not settings.enable_distributed_limits or not scope.get("path", "").startswith("/api/"):
            return await self.app(scope, receive, send)
        # Signed provider callbacks have their own verification and must not share
        # a tenant's interactive quota; ingress limits are configured on Render.
        if scope["path"].startswith("/api/webhooks/"):
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        authorization = headers.get(b"authorization", b"").decode()
        identity = ((scope.get("client") or ("unknown",))[0])
        if authorization.startswith("Bearer "):
            token = decode_token(authorization[7:])
            if token and token.get("tenantId"):
                identity = f"tenant:{token['tenantId']}"
        key = "hanu:rate:" + hashlib.sha256(identity.encode()).hexdigest() + ":" + str(int(time.time() // 60))
        try:
            if self.redis is None:
                self.redis = Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
            count = await self.redis.eval(SCRIPT, 1, key, 65)
        except Exception:
            return await JSONResponse({"detail": "Request limiting is temporarily unavailable"}, status_code=503)(scope, receive, send)
        if count > settings.tenant_requests_per_minute:
            return await JSONResponse({"detail": "Business request limit reached"}, status_code=429, headers={"Retry-After": "60"})(scope, receive, send)
        return await self.app(scope, receive, send)
