import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any, cast

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import get_settings
from app.database.connection import SessionLocal, create_all
from app.routers import register_routers
from app.services.permissions import backfill_owner_modules
from app.socket.connection import set_socket_manager


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if settings.auto_create_tables:
        create_all()
    db = SessionLocal()
    try:
        backfill_owner_modules(db)
    finally:
        db.close()
    yield


def create_socket_app(fastapi_app: FastAPI, settings):
    if not settings.enable_socket_progress:
        set_socket_manager(None)
        return fastapi_app

    try:
        import socketio
    except ImportError:
        set_socket_manager(None)
        return fastapi_app

    socket_manager = socketio.AsyncServer(
        async_mode="asgi",
        cors_allowed_origins=settings.cors_origins,
    )
    socket_on = getattr(socket_manager, "on", None)
    if not callable(socket_on):
        set_socket_manager(None)
        return fastapi_app
    socket_on = cast(Callable[[str], Callable[[Callable[..., Any]], Callable[..., Any]]], socket_on)

    set_socket_manager(socket_manager)

    @socket_manager.event
    async def connect(sid, environ, auth):  # noqa: ARG001
        return True

    @socket_on("upload:subscribe")
    async def upload_subscribe(sid, payload):
        upload_id = (payload or {}).get("uploadId")
        if not upload_id:
            await socket_manager.emit("upload:error", {"message": "uploadId is required"}, to=sid)
            return
        await socket_manager.enter_room(sid, f"upload:{upload_id}")
        await socket_manager.emit("upload:subscribed", {"uploadId": upload_id}, to=sid)

    return socketio.ASGIApp(socket_manager, other_asgi_app=fastapi_app)


def create_app():
    settings = get_settings()
    fastapi_app = FastAPI(title="CBDP Python PostgreSQL API", lifespan=lifespan)

    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @fastapi_app.get("/health")
    def health() -> dict:
        return {"success": True, "status": "ok"}

    register_routers(fastapi_app)
    return create_socket_app(fastapi_app, settings)


app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=True,
    )
