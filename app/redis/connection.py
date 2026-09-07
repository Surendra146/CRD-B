import json
from typing import Any

from app.config.settings import get_settings


_redis_client: Any | None | bool = None
_memory_cache: dict[str, dict] = {}


def get_redis_client() -> Any | None:
    global _redis_client
    if _redis_client is False:
        return None
    if _redis_client is not None:
        return _redis_client

    settings = get_settings()
    if not settings.enable_redis_progress:
        _redis_client = False
        return None

    try:
        from redis import Redis

        client = Redis.from_url(settings.redis_url, decode_responses=True)
        client.ping()
        _redis_client = client
        return client
    except Exception:
        _redis_client = False
        return None


def set_progress_cache(upload_id: int, payload: dict, ttl_seconds: int = 86400) -> None:
    key = f"upload:progress:{upload_id}"
    client = get_redis_client()
    if client is None:
        _memory_cache[key] = payload
        return
    client.setex(key, ttl_seconds, json.dumps(payload, default=str))


def get_progress_cache(upload_id: int) -> dict | None:
    key = f"upload:progress:{upload_id}"
    client = get_redis_client()
    if client is None:
        return _memory_cache.get(key)
    value = client.get(key)
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None
    return _redis_client
