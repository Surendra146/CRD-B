from fastapi import APIRouter, Request



def verify_whatsapp():
    return {"success": True, "message": "Webhook verified"}


async def receive_whatsapp(request: Request):
    return {"success": True, "data": await request.json()}


router = APIRouter()

router.get("/whatsapp")(verify_whatsapp)




