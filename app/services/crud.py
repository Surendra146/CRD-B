from typing import Any

from fastapi import HTTPException
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.utils.helpers import model_to_dict


def paginate(db: Session, statement: Select, page: int, limit: int) -> dict[str, Any]:
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.scalars(statement.offset((page - 1) * limit).limit(limit)).all()
    return {
        "success": True,
        "data": [model_to_dict(row) for row in rows],
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": (total + limit - 1) // limit if limit else 0,
        },
    }


def get_owned(db: Session, model: Any, record_id: int, organization_id: int):
    record = db.get(model, record_id)
    if not record or getattr(record, "organization_id", None) != organization_id:
        raise HTTPException(404, f"{model.__name__} not found")
    return record


def apply_payload(record: Any, payload: dict[str, Any], field_map: dict[str, str] | None = None) -> None:
    field_map = field_map or {}
    for key, value in payload.items():
        target = field_map.get(key, key)
        if hasattr(record, target):
            setattr(record, target, value)


def search_like(statement: Select, model: Any, value: str, fields: list[str]) -> Select:
    if not value:
        return statement
    pattern = f"%{value}%"
    conditions = [getattr(model, field).like(pattern) for field in fields if hasattr(model, field)]
    return statement.where(or_(*conditions)) if conditions else statement

