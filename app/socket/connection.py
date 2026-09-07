from typing import Any

_socket_manager: Any | None = None


def set_socket_manager(socket_manager: Any | None) -> None:
    global _socket_manager
    _socket_manager = socket_manager


def get_socket_manager() -> Any | None:
    return _socket_manager
