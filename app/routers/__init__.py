from fastapi import APIRouter, FastAPI

from app.routers import (
    analytics,
    auth,
    campaigns,
    communications,
    customers,
    dashboards,
    excel,
    marketing_tools,
    notifications,
    segments,
    system,
    templates,
    uploads,
    webhooks,
)

ROUTERS = (
    (auth.router, "/api/auth", ["auth"]),
    (customers.router, "/api/customers", ["customers"]),
    (campaigns.router, "/api/campaigns", ["campaigns"]),
    (communications.router, "/api/communications", ["communications"]),
    (marketing_tools.router, "/api/marketing", ["marketing"]),
    (notifications.router, "/api/notifications", ["notifications"]),
    (templates.router, "/api/templates", ["templates"]),
    (segments.router, "/api/segments", ["segments"]),
    (webhooks.router, "/api/webhooks", ["webhooks"]),
    (dashboards.router, "/api/dashboards", ["dashboards"]),
    (excel.router, "/api/excel", ["excel"]),
    (analytics.router, "/api/analytics", ["analytics"]),
    (uploads.router, "/api/uploads", ["uploads"]),
    (system.router, "/api", ["system"]),
)


def register_routers(app: FastAPI) -> None:
    for router, prefix, tags in ROUTERS:
        app.include_router(router, prefix=prefix, tags=tags)


