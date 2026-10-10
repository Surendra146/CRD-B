"""Remove online payment integration while preserving SaaS and invoice records.

Provider metadata and webhook inbox rows are intentionally removed. Review a
backup first; rollback cannot recreate their contents. No tenant/RLS changes.
"""
from alembic import op
import sqlalchemy as sa

revision = "f91c320ab005"
down_revision = "f91c320ab004"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table("payment_gateway_settings")
    op.drop_table("billing_events")
    op.drop_column("subscription_plans", "provider_plan_id")
    op.drop_column("subscriptions", "provider_subscription_id")
    op.drop_column("subscriptions", "provider_updated_at")
    # Rename in place: retain invoice identities, payment references and history.
    op.alter_column("saas_invoices", "provider_payment_id", new_column_name="payment_reference",
                    existing_type=sa.String(120), nullable=True)
    op.alter_column("saas_invoices", "provider_invoice_id", new_column_name="invoice_reference",
                    existing_type=sa.String(120), existing_nullable=True)
    # Retire checkout's runtime write privilege; preserve tenant SELECT and RLS.
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'hanuram_runtime') THEN
            REVOKE INSERT, UPDATE, DELETE ON subscriptions FROM hanuram_runtime;
        END IF;
    END $$""")


def downgrade():
    raise RuntimeError("Provider metadata was removed; restore a reviewed backup for rollback")
