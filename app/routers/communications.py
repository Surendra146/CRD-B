from fastapi import APIRouter, Depends

from app.schemas.communication import CommunicationRequest
from app.services.security import require_organization


def communication_payload(payload: CommunicationRequest) -> dict:
    return payload.to_payload()


def send_whatsapp(payload: CommunicationRequest):
    payload = communication_payload(payload)
    return {"success": True, "message": "WhatsApp send queued", "data": payload}


def send_whatsapp_message(payload: CommunicationRequest):
    payload = communication_payload(payload)
    return {"success": True, "message": "WhatsApp send queued", "data": payload}


def send_communication(payload: CommunicationRequest):
    payload = communication_payload(payload)
    return {"success": True, "message": "Communication queued", "data": payload}


router = APIRouter(dependencies=[Depends(require_organization)])

router.post("/whatsapp")(send_whatsapp)
router.post("/whatsapp/send")(send_whatsapp_message)
router.post("/")(send_communication)




