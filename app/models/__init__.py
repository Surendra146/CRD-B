from .tables import (
    Campaign,
    Customer,
    Dashboard,
    DashboardConfig,
    DataUpload,
    DataUploadRow,
    GenericJsonRecord,
    Organization,
    Segment,
    Tenant,
    TimestampMixin,
    User,
    WhatsAppTemplate,
)
from .registry import create_tables

__all__ = (
    "Campaign",
    "Customer",
    "Dashboard",
    "DashboardConfig",
    "DataUpload",
    "DataUploadRow",
    "GenericJsonRecord",
    "Organization",
    "Segment",
    "Tenant",
    "TimestampMixin",
    "User",
    "WhatsAppTemplate",
    "create_tables",
)
