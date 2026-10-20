"""Allow delivery diagnostics under the existing webhook authority."""
from pathlib import Path

from alembic import op
import sqlalchemy as sa

revision = 'f91c320ab012'
down_revision = 'f91c320ab011'
branch_labels = None
depends_on = None


def _replace(upgrade):
    patched = (Path(__file__).parents[1] / 'authorization' / 'f91c320ab012.sql').read_text()
    previous = patched.replace(
        "ARRAY['status','status_timestamp','delivery_details','updated_at']",
        "ARRAY['status','status_timestamp','updated_at']")
    expected, replacement = (previous, patched) if upgrade else (patched, previous)
    # Fail closed on unexpected live function changes instead of overwriting them.
    current = op.get_bind().scalar(sa.text(
        "SELECT prosrc FROM pg_proc WHERE oid='hanuram_auth.guard_row()'::regprocedure"))
    if current.strip() != expected.split('$$')[1].strip():
        raise RuntimeError('Unexpected guard_row definition; review database authorization drift')
    # CREATE OR REPLACE preserves function ownership, ACLs and trigger attachments.
    op.execute(sa.text(replacement))


def upgrade():
    _replace(True)


def downgrade():
    _replace(False)
