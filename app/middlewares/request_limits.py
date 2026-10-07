"""Bound request bodies before parsers or database handlers consume them."""
from starlette.responses import JSONResponse


class RequestLimitMiddleware:
    def __init__(self, app, max_bytes=10 * 1024 * 1024):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = 1024 * 1024 if scope["path"] == "/api/webhooks/whatsapp" else self.max_bytes
        parts = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body = message.get("body", b"")
            size += len(body)
            if size > limit:
                response = JSONResponse({"detail": "Request body exceeds the allowed size"}, status_code=413)
                return await response(scope, receive, send)
            parts.append(body)
            if not message.get("more_body", False):
                break
        consumed = False

        async def bounded_receive():
            nonlocal consumed
            if not consumed:
                consumed = True
                return {"type": "http.request", "body": b"".join(parts), "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)
