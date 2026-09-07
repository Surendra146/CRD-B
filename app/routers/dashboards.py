from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.utils.helpers import model_to_dict
from app.models import Dashboard, DashboardConfig, User
from app.schemas.dashboard import DashboardCreateRequest, DashboardUpdateRequest
from app.services.security import get_current_user



def create_dashboard(payload: DashboardCreateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    payload = payload.to_payload()
    source_names = payload.get("sourceNames") or []
    count = int(payload.get("excelSourcesCount") or len(source_names))
    if len(source_names) != count:
        raise HTTPException(400, "Source names count must match excelSourcesCount")
    dashboard = Dashboard(
        name=payload.get("name"),
        description=payload.get("description"),
        tenant_id=user.tenant_id or user.organization_id,
        tenant_code=user.tenant_code,
        created_by=user.id,
        excel_sources_config=[{"name": name, "requiredColumns": [], "status": "pending"} for name in source_names],
        layout=payload.get("layout") or {"widgets": [], "filters": [], "charts": []},
    )
    db.add(dashboard)
    db.flush()
    db.add(DashboardConfig(tenant_id=dashboard.tenant_id, tenant_code=user.tenant_code, dashboard_id=dashboard.id, layout=dashboard.layout, widgets=dashboard.layout.get("widgets", []), filters=dashboard.layout.get("filters", []), created_by=user.id))
    db.commit()
    db.refresh(dashboard)
    return model_to_dict(dashboard)


def get_dashboards(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    tenant_id = user.tenant_id or user.organization_id
    rows = db.scalars(select(Dashboard).where(Dashboard.tenant_id == tenant_id, Dashboard.is_active == True).order_by(Dashboard.created_at.desc())).all()
    return [model_to_dict(row) for row in rows]


def get_dashboard(dashboard_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    dashboard = db.get(Dashboard, dashboard_id)
    if not dashboard or dashboard.tenant_id != (user.tenant_id or user.organization_id):
        raise HTTPException(404, "Dashboard not found")
    return model_to_dict(dashboard)


def update_dashboard(dashboard_id: int, payload: DashboardUpdateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    payload = payload.to_payload()
    dashboard = db.get(Dashboard, dashboard_id)
    if not dashboard or dashboard.tenant_id != (user.tenant_id or user.organization_id):
        raise HTTPException(404, "Dashboard not found")
    for key in ("name", "description", "layout"):
        if key in payload:
            setattr(dashboard, key, payload[key])
    if "layout" in payload:
        config = db.scalar(select(DashboardConfig).where(DashboardConfig.dashboard_id == dashboard.id))
        if config:
            config.layout = payload["layout"]
            config.widgets = payload["layout"].get("widgets", [])
            config.filters = payload["layout"].get("filters", [])
    db.commit()
    return model_to_dict(dashboard)


def delete_dashboard(dashboard_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    dashboard = db.get(Dashboard, dashboard_id)
    if not dashboard or dashboard.tenant_id != (user.tenant_id or user.organization_id):
        raise HTTPException(404, "Dashboard not found")
    dashboard.is_active = False
    db.commit()
    return {"message": "Dashboard deleted successfully"}


router = APIRouter(dependencies=[Depends(get_current_user)])

router.post("/")(create_dashboard)
router.get("/")(get_dashboards)
router.get("/{dashboard_id}")(get_dashboard)
router.put("/{dashboard_id}")(update_dashboard)
router.delete("/{dashboard_id}")(delete_dashboard)




