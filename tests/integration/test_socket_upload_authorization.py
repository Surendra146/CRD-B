import pytest
from fastapi import HTTPException

from app.models import DataUpload, User
from app.services import socket_security

pytestmark = pytest.mark.integration


def test_socket_upload_subscription_requires_identity_and_ownership(account_factory, db_session, session_factory, monkeypatch):
    owner, other = account_factory(), account_factory()
    user = db_session.get(User, owner["user"]["id"])
    upload = DataUpload(tenant_id=user.tenant_id, organization_id=user.organization_id, uploaded_by=user.id, type="customer_details")
    db_session.add(upload)
    db_session.commit()
    monkeypatch.setattr(socket_security, "ControlSessionLocal", session_factory)
    monkeypatch.setattr(socket_security, "SessionLocal", session_factory)
    token = owner["headers"]["Authorization"].split()[1]
    assert socket_security.authorize_upload_socket(token, str(upload.id)) == upload.id
    for untrusted in [None, "expired"]:
        with pytest.raises(HTTPException) as error:
            socket_security.authorize_upload_socket(untrusted, upload.id)
        assert error.value.status_code == 401
    with pytest.raises(HTTPException) as error:
        socket_security.authorize_upload_socket(other["headers"]["Authorization"].split()[1], upload.id)
    assert error.value.status_code == 404
