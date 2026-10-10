"""Persist the global payment toggle without changing business records."""
from alembic import op
import sqlalchemy as sa

revision = "f91c320ab004"
down_revision = "f91c320ab003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("payment_gateway_settings",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("id = 'default'"))
    # Only the trusted control role can read or mutate global payment policy.
    op.execute("REVOKE ALL ON TABLE payment_gateway_settings FROM PUBLIC")
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'hanuram_control') THEN
            GRANT SELECT, INSERT, UPDATE ON payment_gateway_settings TO hanuram_control;
        END IF;
    END $$""")


def downgrade():
    op.drop_table("payment_gateway_settings")
