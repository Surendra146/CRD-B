from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.routers.platform import AssignmentPayload, RenewalPayload, CancellationPayload
from app.services.billing import effective_status, number_limit, require_paid_subscription

NOW = datetime(2026, 10, 10, tzinfo=UTC)


@pytest.mark.parametrize("status,start,end,expected", [
    ("active", NOW, NOW + timedelta(days=1), "active"),
    ("active", NOW + timedelta(seconds=1), NOW + timedelta(days=1), "scheduled"),
    ("active", NOW - timedelta(days=1), NOW, "expired"),
    ("active", None, NOW + timedelta(days=1), "expired"),
    ("active", NOW, None, "expired"),
    ("cancelled", NOW, NOW + timedelta(days=1), "cancelled"),
])
def test_effective_subscription_boundaries(status, start, end, expected):
    assert effective_status(SimpleNamespace(status=status, current_start=start, current_end=end), NOW) == expected


def test_legacy_naive_timestamps_are_interpreted_as_utc():
    row = SimpleNamespace(status="active", current_start=NOW.replace(tzinfo=None),
        current_end=(NOW + timedelta(days=1)).replace(tzinfo=None))
    assert effective_status(row, NOW) == "active"


@pytest.mark.parametrize("value", [None, 0, -1, True, "2"])
def test_number_entitlements_fail_closed(value):
    now = datetime.now(UTC)
    row = SimpleNamespace(status="active", current_start=now - timedelta(days=1),
        current_end=now + timedelta(days=1), plan_id="plan")
    db = Mock()
    db.scalar.return_value = row
    db.get.return_value = SimpleNamespace(entitlements={"whatsapp_numbers": value})
    with pytest.raises(HTTPException) as error:
        number_limit(db, SimpleNamespace(tenant_id=1, organization_id=11))
    assert error.value.status_code == 403


def test_future_assignment_cannot_access_paid_features():
    now = datetime.now(UTC)
    db = Mock()
    db.scalar.return_value = SimpleNamespace(status="active", current_start=now + timedelta(days=1),
        current_end=now + timedelta(days=2))
    with pytest.raises(HTTPException) as error:
        require_paid_subscription(db, SimpleNamespace(tenant_id=1, organization_id=11))
    assert error.value.status_code == 402


@pytest.mark.parametrize("changes", [
    {"current_start": "2026-10-10T10:00:00"},
    {"current_end": "2026-10-10T00:00:00Z"},
    {"reason": " "}, {"status": "active"},
])
def test_manual_assignment_rejects_invalid_or_extra_fields(changes):
    values = dict(request_id="00000000-0000-4000-8000-000000000001", reason="Approved",
        plan_id="standard", current_start="2026-10-10T00:00:00Z", current_end="2026-11-10T00:00:00Z")
    with pytest.raises(ValidationError):
        AssignmentPayload(**{**values, **changes})


@pytest.mark.parametrize("days", [True, "30", 0, 3661])
def test_renewal_days_are_strict_and_bounded(days):
    with pytest.raises(ValidationError):
        RenewalPayload(request_id="00000000-0000-4000-8000-000000000001", reason="Approved", days=days)


def test_cancellation_boolean_is_strict():
    with pytest.raises(ValidationError):
        CancellationPayload(request_id="00000000-0000-4000-8000-000000000001", reason="Approved", at_period_end="false")
