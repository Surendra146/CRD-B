"""Server-owned delivery permission; unrelated Meta operations remain available."""
from fastapi import HTTPException
from app.config.settings import get_settings


class WhatsAppSendingDisabled(HTTPException):
    def __init__(self):
        super().__init__(503, 'WhatsApp sending is disabled by the server. Retry after sending is explicitly enabled.')


def sending_enabled():
    return get_settings().whatsapp_sending_enabled is True


def require_sending_enabled():
    if not sending_enabled():
        raise WhatsAppSendingDisabled()
