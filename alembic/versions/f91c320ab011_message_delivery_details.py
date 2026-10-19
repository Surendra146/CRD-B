"""Retain message delivery diagnostics under existing message-record RLS."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'f91c320ab011'
down_revision = 'f91c320ab010'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('message_records', sa.Column('delivery_details', JSONB(),
        nullable=False, server_default=sa.text("'{}'::jsonb")))


def downgrade():
    op.drop_column('message_records', 'delivery_details')
