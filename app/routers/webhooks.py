import secrets

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from app.config.settings import get_settings

router = APIRouter()


@router.get("/whatsapp", response_class=PlainTextResponse)
def verify_whatsapp(request: Request):
    expected_token = get_settings().whatsapp_verify_token
    if not expected_token:
        raise HTTPException(status_code=503, detail="WhatsApp verify token is not configured")

    mode = request.query_params.get("hub.mode")
    supplied_token = request.query_params.get("hub.verify_token", "")
    challenge = request.query_params.get("hub.challenge")
    if mode != "subscribe" or not secrets.compare_digest(
        supplied_token.encode("utf-8"), expected_token.encode("utf-8")
    ):
        raise HTTPException(status_code=403, detail="Webhook verification failed")
    if challenge is None or challenge == "":
        raise HTTPException(status_code=400, detail="Missing hub.challenge")
    return PlainTextResponse(challenge)


async def receive_whatsapp(request: Request):
    return {"success": True, "data": await request.json()}
