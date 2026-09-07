from datetime import date, datetime, time
from decimal import Decimal
from re import sub
from typing import Any


def slugify(value: str) -> str:
    slug = sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return slug or "organization"


def normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def normalize_phone(value: Any) -> str:
    return sub(r"\D+", "", str(value or ""))


def day_bounds(value: Any) -> tuple[datetime, datetime] | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None
    start = datetime.combine(parsed.date(), time.min)
    end = datetime.combine(date.fromordinal(parsed.date().toordinal() + 1), time.min)
    return start, end


def json_ready(value: Any) -> Any:
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def model_to_dict(model: Any) -> dict[str, Any]:
    data = {
        column.name: json_ready(getattr(model, column.name))
        for column in model.__table__.columns
    }
    data["_id"] = str(data["id"])
    for key, value in list(data.items()):
        if "_" in key:
            parts = key.split("_")
            data[parts[0] + "".join(part.title() for part in parts[1:])] = value
    return data


def apply_customer_purchase_metrics(customer: Any) -> None:
    purchases = customer.purchases or []
    completed = [purchase for purchase in purchases if purchase.get("status", "completed") == "completed"]
    lifecycle = customer.lifecycle or {}
    lifecycle["totalPurchases"] = len(completed)
    lifecycle["totalSpent"] = sum(float(purchase.get("amount") or 0) for purchase in completed)
    lifecycle["averageOrderValue"] = lifecycle["totalSpent"] / len(completed) if completed else 0
    dated = sorted(
        [purchase for purchase in completed if purchase.get("date")],
        key=lambda purchase: str(purchase.get("date")),
    )
    if dated:
        lifecycle["firstPurchaseDate"] = dated[0].get("date")
        lifecycle["lastPurchaseDate"] = dated[-1].get("date")
        try:
            last_date = datetime.fromisoformat(str(dated[-1].get("date")).replace("Z", "+00:00")).replace(tzinfo=None)
            lifecycle["daysSinceLastPurchase"] = (datetime.utcnow() - last_date).days
        except ValueError:
            pass
    customer.lifecycle = lifecycle

