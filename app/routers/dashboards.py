from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.utils.helpers import model_to_dict
from app.models import Dashboard, DashboardConfig, User
from app.schemas.dashboard import DashboardCreateRequest, DashboardUpdateRequest
from app.services.security import ensure_tenant_access, require_organization, tenant_id_for_user



def create_dashboard(payload: DashboardCreateRequest, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    payload_data = payload.to_payload()
    source_names = payload_data.get("sourceNames") or []
    count = int(payload_data.get("excelSourcesCount") or len(source_names))
    if len(source_names) != count:
        raise HTTPException(400, "Source names count must match excelSourcesCount")
    dashboard = Dashboard(
        name=payload_data.get("name"),
        description=payload_data.get("description"),
        tenant_id=tenant_id_for_user(user),
        tenant_code=user.tenant_code,
        created_by=user.id,
        excel_sources_config=[{"name": name, "requiredColumns": [], "status": "pending"} for name in source_names],
        layout=payload_data.get("layout") or {"widgets": [], "filters": [], "charts": []},
    )
    db.add(dashboard)
    db.flush()
    db.add(DashboardConfig(tenant_id=dashboard.tenant_id, tenant_code=user.tenant_code, dashboard_id=dashboard.id, layout=dashboard.layout, widgets=dashboard.layout.get("widgets", []), filters=dashboard.layout.get("filters", []), created_by=user.id))
    db.commit()
    db.refresh(dashboard)
    return model_to_dict(dashboard)


def get_dashboards(user: User = Depends(require_organization), db: Session = Depends(get_db)):
    tenant_id = tenant_id_for_user(user)
    rows = db.scalars(select(Dashboard).where(Dashboard.tenant_id == tenant_id, Dashboard.is_active == True).order_by(Dashboard.created_at.desc())).all()
    return [model_to_dict(row) for row in rows]


def get_dashboard(dashboard_id: int, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    dashboard = db.get(Dashboard, dashboard_id)
    ensure_tenant_access(dashboard, user, "Dashboard")
    return model_to_dict(dashboard)


def update_dashboard(dashboard_id: int, payload: DashboardUpdateRequest, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    payload_data = payload.to_payload()
    dashboard = db.get(Dashboard, dashboard_id)
    ensure_tenant_access(dashboard, user, "Dashboard")
    for key in ("name", "description", "layout"):
        if key in payload_data:
            setattr(dashboard, key, payload_data[key])
    if "layout" in payload_data:
        config = db.scalar(
            select(DashboardConfig).where(
                DashboardConfig.dashboard_id == dashboard.id,
                DashboardConfig.tenant_id == tenant_id_for_user(user),
            )
        )
        if config:
            config.layout = payload_data["layout"]
            config.widgets = payload_data["layout"].get("widgets", [])
            config.filters = payload_data["layout"].get("filters", [])
    db.commit()
    return model_to_dict(dashboard)


def delete_dashboard(dashboard_id: int, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    dashboard = db.get(Dashboard, dashboard_id)
    ensure_tenant_access(dashboard, user, "Dashboard")
    dashboard.is_active = False
    db.commit()
    return {"message": "Dashboard deleted successfully"}


router = APIRouter(dependencies=[Depends(require_organization)])

router.post("/")(create_dashboard)
router.get("/")(get_dashboards)
router.get("/{dashboard_id}")(get_dashboard)
router.put("/{dashboard_id}")(update_dashboard)
router.delete("/{dashboard_id}")(delete_dashboard)




