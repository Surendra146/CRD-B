"""Add encrypted per-organization WhatsApp connections and signup attempts."""
from alembic import op
from app.models.whatsapp_connection import WhatsAppConnection, WhatsAppSignupAttempt

revision = "d24bf074d970"
down_revision = "62942c9db687"
branch_labels = None
depends_on = None


def upgrade():
    WhatsAppConnection.__table__.create(op.get_bind(), checkfirst=True)
    WhatsAppSignupAttempt.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    WhatsAppSignupAttempt.__table__.drop(op.get_bind(), checkfirst=True)
    WhatsAppConnection.__table__.drop(op.get_bind(), checkfirst=True)
