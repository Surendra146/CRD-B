from fastapi import APIRouter, Depends

from app.services.security import require_organization



def get_notifications():
    return {"success": True, "data": []}


router = APIRouter(dependencies=[Depends(require_organization)])

router.get("/")(get_notifications)




