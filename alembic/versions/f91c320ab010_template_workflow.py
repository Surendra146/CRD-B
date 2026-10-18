"""Add template snapshots without changing existing tenant RLS policies."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'f91c320ab010'
down_revision = 'f91c320ab009'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('whatsapp_templates', sa.Column('workflow', JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))


def downgrade():
    op.drop_column('whatsapp_templates', 'workflow')
