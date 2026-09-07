


from fastapi import APIRouter


def system_fields():
    return {
        "success": True,
        "data": {
            "customer": ["externalId", "name", "email", "phone", "address", "customerCreatedDate"],
            "purchase": ["orderId", "date", "amount", "items", "channel", "paymentMethod", "status"],
        },
    }


def fields():
    return system_fields()


router = APIRouter()

router.get("/system-fields")(system_fields)
router.get("/fields")(fields)




