"""Server-owned Meta Cloud API sending and verified delivery-state updates."""
import json
import re
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, HTTPRedirectHandler, build_opener
from urllib.parse import urlparse
import ipaddress

from fastapi import HTTPException

from app.config.settings import get_settings


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# Never forward Meta bearer credentials to a redirected destination.
urlopen = build_opener(NoRedirect()).open


def require_configuration(connection=None):
    if connection is None:
        raise HTTPException(409, "Connect your organization's WhatsApp Business account in Settings first")
    settings = connection
    if settings.whatsapp_provider != "meta_cloud":
        raise HTTPException(503, "Only the meta_cloud WhatsApp provider is supported")
    if not settings.whatsapp_phone_number_id or not settings.whatsapp_access_token:
        raise HTTPException(409, "Your organization's WhatsApp connection is incomplete. Reconnect in Settings")
    if not re.fullmatch(r"\d+", settings.whatsapp_phone_number_id) or not re.fullmatch(r"v\d+\.\d+", settings.whatsapp_graph_version):
        raise HTTPException(503, "Invalid backend Meta phone number ID or Graph API version")
    return settings


def normalize_phone(phone):
    raw = str(phone or "").strip()
    if re.search(r"[^\d\s+().-]", raw):
        raise HTTPException(400, "Invalid recipient phone number")
    digits = re.sub(r"\D", "", raw)
    if raw.startswith("00"):
        digits = digits[2:]
    elif not raw.startswith("+") and len(digits) == 10:
        digits = "91" + digits
    if not 8 <= len(digits) <= 15 or digits.startswith("0"):
        raise HTTPException(400, "Use a valid recipient phone number including country code")
    return digits


def build_message(phone, message, *, template=None, buttons=None, media_files=None):
    payload = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": normalize_phone(phone)}
    if template:
        if not isinstance(template, dict) or not template.get("name") or not template.get("language", {}).get("code"):
            raise HTTPException(400, "An approved Meta template requires a name and language.code")
        payload.update(type="template", template=template)
    elif media_files:
        if len(media_files) != 1 or buttons:
            raise HTTPException(400, "Send one public media URL per message, without buttons")
        media = media_files[0]
        kind = media.get("type")
        link = media.get("url") or ""
        parsed = urlparse(link)
        if kind not in {"image", "video", "document"} or parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise HTTPException(400, "Use a public HTTPS image, video or document URL; local uploads and blob URLs are not supported")
        if parsed.hostname == "localhost" or parsed.hostname.endswith((".localhost", ".local")):
            raise HTTPException(400, "Media URLs must be publicly accessible")
        try:
            if not ipaddress.ip_address(parsed.hostname).is_global:
                raise HTTPException(400, "Media URLs must be publicly accessible")
        except ValueError:
            pass
        content = {"link": link}
        if message:
            if len(message) > 1024:
                raise HTTPException(400, "Media captions are limited to 1024 characters")
            content["caption"] = message
        if kind == "document" and media.get("name"):
            content["filename"] = str(media["name"])[:255]
        payload.update(type=kind, **{kind: content})
    elif buttons:
        if not str(message or "").strip() or len(message) > 1024:
            raise HTTPException(400, "Interactive message text must contain 1 to 1024 characters")
        if len(buttons) > 3 or any(b.get("type") != "quick_reply" for b in buttons):
            raise HTTPException(400, "Free-form messages support up to three quick-reply buttons; URL and phone buttons require an approved Meta template")
        replies = [{"type": "reply", "reply": {"id": str(b.get("id") or i), "title": str(b.get("text") or "")}} for i, b in enumerate(buttons)]
        if any(not b["reply"]["title"] or len(b["reply"]["title"]) > 20 for b in replies):
            raise HTTPException(400, "Quick-reply button labels must contain 1 to 20 characters")
        payload.update(type="interactive", interactive={"type": "button", "body": {"text": message}, "action": {"buttons": replies}})
    else:
        if not str(message or "").strip() or len(message) > 4096:
            raise HTTPException(400, "WhatsApp text must contain 1 to 4096 characters")
        payload.update(type="text", text={"body": message, "preview_url": False})
    return payload


def send_message(phone, message, *, connection=None, **options):
    settings = require_configuration(connection)
    payload = build_message(phone, message, **options)
    request = Request(
        f"https://graph.facebook.com/{settings.whatsapp_graph_version}/{settings.whatsapp_phone_number_id}/messages",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {settings.whatsapp_access_token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            result = json.load(response)
    except HTTPError as error:
        try:
            details = json.loads(error.read()).get("error", {})
        except (ValueError, AttributeError):
            details = {}
        # Never return the request, authorization headers, or raw provider body.
        code = details.get("code")
        raise HTTPException(502, {"message": "Meta rejected the WhatsApp message", "code": code, "provider_message": str(details.get("message") or "Check Meta credentials and messaging permissions").replace(settings.whatsapp_access_token, "[redacted]")}) from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise HTTPException(502, "Meta could not confirm acceptance. Check delivery before retrying to avoid duplicates") from None
    messages = result.get("messages") if isinstance(result, dict) else None
    if not isinstance(messages, list) or not messages or not isinstance(messages[0], dict) or not messages[0].get("id"):
        raise HTTPException(502, "Meta did not return a message ID; delivery is unconfirmed")
    return {"message_id": messages[0]["id"], "status": "accepted", "phone": payload["to"]}


def update_stats(job):
    recipients = job.recipients_summary or []
    statuses = [r.get("status") for r in recipients]
    job.stats = {
        "total": len(recipients),
        "sent": sum(s in {"accepted", "sent", "delivered", "read"} for s in statuses),
        "delivered": sum(s in {"delivered", "read"} for s in statuses),
        "failed": statuses.count("failed"),
        "pending": sum(s in {"queued", "accepted", "sent", "unknown"} for s in statuses),
    }
    if recipients and all(s in {"failed", "delivered", "read"} for s in statuses):
        job.status = "failed" if all(s == "failed" for s in statuses) else "completed"


def apply_status(recipient, status):
    """Ignore duplicate and older callbacks without regressing delivery state."""
    state = status.get("status")
    if state not in {"sent", "delivered", "read", "failed"}:
        return recipient
    try:
        timestamp = int(status.get("timestamp") or 0)
        status_time = datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
    except (ValueError, TypeError, OSError, OverflowError):
        return recipient
    if timestamp < int(recipient.get("status_timestamp") or 0):
        return recipient
    rank = {"queued": 0, "accepted": 1, "sent": 2, "failed": 3, "delivered": 4, "read": 5}
    if rank.get(state, 0) < rank.get(recipient.get("status"), 0):
        return recipient
    result = {**recipient, "status": state, "status_timestamp": timestamp}
    if state in {"delivered", "read"}:
        result["delivered_at"] = recipient.get("delivered_at") or status_time
        result.pop("error", None)
    if state == "failed":
        result["error"] = status.get("errors") or [{"message": "Meta reported delivery failure"}]
    return result
