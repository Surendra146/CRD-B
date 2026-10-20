from pathlib import Path
import asyncio
import importlib.util
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import OperationalError

from app.routers import webhooks


def test_only_delivery_details_allowlist_changes():
    root = Path(__file__).resolve().parents[2] / 'alembic/authorization'
    previous = (root / 'f91c320ab007.sql').read_text()
    start = previous.index('CREATE FUNCTION hanuram_auth.guard_row()')
    end = previous.index('ALTER FUNCTION hanuram_auth.guard_row()', start)
    expected = previous[start:end].strip().replace('CREATE FUNCTION', 'CREATE OR REPLACE FUNCTION', 1)
    expected = expected.replace("ARRAY['status','status_timestamp','updated_at']",
                                "ARRAY['status','status_timestamp','delivery_details','updated_at']")
    assert (root / 'f91c320ab012.sql').read_text().strip() == expected


@pytest.mark.parametrize('upgrade', [False, True])
def test_migration_refuses_function_drift(monkeypatch, upgrade):
    path = Path(__file__).resolve().parents[2] / 'alembic/versions/f91c320ab012_webhook_delivery_authorization.py'
    spec = importlib.util.spec_from_file_location('webhook_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    operations = Mock()
    operations.get_bind.return_value.scalar.return_value = 'unexpected function body'
    monkeypatch.setattr(migration, 'op', operations)
    with pytest.raises(RuntimeError, match='authorization drift'):
        migration._replace(upgrade)
    operations.execute.assert_not_called()


@pytest.mark.parametrize('rollback_fails', [False, True])
def test_database_failure_logging_is_sanitized(monkeypatch, caplog, rollback_fails):
    secret = 'credential-phone-message-secret'
    original = Exception(secret)
    original.sqlstate = '42501'
    error = OperationalError(secret, {'token': secret}, original)
    async def fail(*args):
        raise error
    monkeypatch.setattr(webhooks, '_receive_whatsapp', fail)
    db = Mock()
    if rollback_fails:
        db.rollback.side_effect = error
    with pytest.raises(HTTPException) as caught:
        asyncio.run(webhooks.receive_whatsapp(Mock(), db))
    assert caught.value.status_code == 503
    db.rollback.assert_called_once()
    assert secret not in caplog.text
    assert 'sqlstate=42501' in caplog.text
    assert 'OperationalError' in caplog.text
    assert 'test_database_failure_logging_is_sanitized' not in caplog.text
    assert 'fail' in caplog.text
