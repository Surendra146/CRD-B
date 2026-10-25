"""Storage keys are server-derived identifiers, never arbitrary paths."""
import re

MAX_MEDIA_BYTES = 100 * 1024**2
KEY_PATTERN = re.compile(r"[0-9]+/[0-9]+/[0-9]+/[a-f0-9]{32}\Z", re.ASCII)


def validate_key(key: str) -> str:
    if not isinstance(key, str) or not KEY_PATTERN.fullmatch(key):
        raise ValueError("Invalid media storage key")
    return key
