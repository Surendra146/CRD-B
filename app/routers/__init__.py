from fastapi import APIRouter, FastAPI, Depends
from app.services.security import require_module

from app.routers import (
    analytics,
    auth,
    campaigns,
    communications,
    customers,
    excel,
    marketing_tools,
    notifications,
    segments,
    system,
    templates,
    uploads,
    webhooks,
    whatsapp_connections,
)

ROUTERS = (
    (auth.router, "/api/auth", ["auth"]),
    (customers.router, "/api/customers", ["customers"]),
    (campaigns.router, "/api/campaigns", ["campaigns"]),
    (communications.router, "/api/communications", ["communications"]),
    (communications.configuration_router, "/api/communications", ["communications"]),
    (whatsapp_connections.router, "/api/whatsapp-connection", ["whatsapp"]),
    (marketing_tools.router, "/api/marketing", ["marketing"]),
    (notifications.router, "/api/notifications", ["notifications"]),
    (templates.router, "/api/templates", ["templates"]),
    (segments.router, "/api/segments", ["segments"]),
    (webhooks.router, "/api/webhooks", ["webhooks"]),
    (excel.router, "/api/excel", ["excel"]),
    (analytics.router, "/api/analytics", ["analytics"]),
    (uploads.router, "/api/uploads", ["uploads"]),
    (system.router, "/api", ["system"]),
)



def register_routers(app: FastAPI) -> None:
    for router, prefix, tags in ROUTERS:
        permissions = {
            "customers": ("customers",), "campaigns": ("campaigns",),
            "marketing": ("whatsapp",), "templates": ("templates", "whatsapp"),
            "segments": ("segments", "campaigns"), "analytics": ("analytics", "dashboards", "custom-dashboards"),
            "excel": ("excel", "import", "custom-dashboards"),
            "uploads": ("uploads", "import", "reports"), "notifications": ("notifications",),
        }
        modules = permissions.get(tags[0])
        dependencies = [Depends(require_module(*modules))] if modules else []
        app.include_router(router, prefix=prefix, tags=tags, dependencies=dependencies)


