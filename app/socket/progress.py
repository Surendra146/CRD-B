from app.redis.connection import set_progress_cache
from app.socket.connection import get_socket_manager


async def emit_upload_progress(upload_id: int, payload: dict) -> None:
    set_progress_cache(upload_id, payload)
    socket_manager = get_socket_manager()
    if socket_manager is None:
        return
    await socket_manager.emit("upload:progress", payload, room=f"upload:{upload_id}")
