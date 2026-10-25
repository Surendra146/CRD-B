from pathlib import Path
from app.services.media_storage.keys import MAX_MEDIA_BYTES, validate_key


class LocalMediaStorage:
    def __init__(self, root: str):
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        validate_key(key)
        parts = key.split("/")

        if any(
            part in {"", ".", ".."} or ":" in part
            for part in parts
        ):
            raise ValueError("Invalid media storage key")

        path = self.root.joinpath(*parts).resolve()

        if not path.is_relative_to(self.root):
            raise ValueError("Media path escapes storage root")

        return path

    def put(self, key: str, data: bytes) -> None:
        if len(data) > MAX_MEDIA_BYTES:
            raise ValueError("Media exceeds storage limit")
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation protects committed assets even on a UUID collision.
        with path.open('xb') as stream:
            stream.write(data)

    def get(self, key: str) -> bytes:
        with self._path(key).open('rb') as stream:
            data = stream.read(MAX_MEDIA_BYTES + 1)
        if len(data) > MAX_MEDIA_BYTES:
            raise ValueError("Stored media exceeds size limit")
        return data

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)
