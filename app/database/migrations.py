"""Read-only, strict schema compatibility using the deployed Alembic graph."""
import logging
from pathlib import Path
import re

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class SchemaCompatibilityError(RuntimeError):
    """Sanitized failure suitable for startup and readiness diagnostics."""


def migration_heads():
    """Load metadata only: never execute env.py or use migration credentials."""
    try:
        config_path = PROJECT_ROOT / "alembic.ini"
        if not config_path.is_file():
            raise ValueError("missing configuration")
        config = Config(str(config_path))
        location = config.get_main_option("script_location")
        if not location:
            raise ValueError("missing script location")
        # Relative ini paths belong to the backend, not the process working directory.
        if not Path(location).is_absolute() and ":" not in location:
            config.set_main_option("script_location", str(PROJECT_ROOT / location).replace("%", "%%"))
        heads = frozenset(ScriptDirectory.from_config(config).get_heads())
        if not heads or not all(_valid_revision(value) for value in heads):
            raise ValueError("invalid migration heads")
        return heads
    except Exception:
        logger.error("Schema compatibility: deployed migration metadata unavailable")
        raise SchemaCompatibilityError("Deployed migration metadata unavailable") from None


def _valid_revision(value):
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,32}", value) is not None


def validate_schema_compatibility(connection):
    """Borrow the caller's connection; perform SELECTs only, with no commit."""
    expected = migration_heads()
    try:
        rows = list(connection.execute(text("SELECT version_num FROM public.alembic_version")).scalars())
    except Exception:
        logger.error("Schema compatibility: expected=%s actual=<unavailable>", sorted(expected))
        raise SchemaCompatibilityError("Cannot read database migration revisions") from None
    # Do not print arbitrary database values (URLs, secrets, or control characters).
    if not rows or not all(_valid_revision(value) for value in rows) or len(set(rows)) != len(rows):
        logger.error("Schema compatibility: expected=%s actual=<empty-or-invalid>", sorted(expected))
        raise SchemaCompatibilityError("Database migration revisions are empty or invalid") from None
    actual = frozenset(rows)
    if actual != expected:
        logger.error("Schema compatibility mismatch: expected=%s actual=%s", sorted(expected), sorted(actual))
        raise SchemaCompatibilityError(
            f"Database migration revisions mismatch: expected={sorted(expected)} actual={sorted(actual)}"
        ) from None
    logger.debug("Schema compatibility verified: expected=%s actual=%s", sorted(expected), sorted(actual))
