import pytest

pytestmark = pytest.mark.integration


def test_customer_ownership_is_immutable(client, account, account_factory, customer_payload):
    other = account_factory()
    created = client.post('/api/customers/', headers=account['headers'], json=customer_payload).json()['data']
    changed = client.put(f"/api/customers/{created['id']}", headers=account['headers'], json={
        'organization_id': other['user']['organization_id'], 'tenant_id': other['user']['tenant_id'], 'name': 'Hijacked',
    })
    assert changed.status_code == 400
    current = client.get(f"/api/customers/{created['id']}", headers=account['headers']).json()['data']
    assert current['name'] == customer_payload['name']
    assert current['organization_id'] == account['user']['organization_id']


def test_member_cannot_grant_self_permissions(client, account):
    created = client.post('/api/auth/members', headers=account['headers'], json={
        'email': 'member-audit@example.com', 'password': 'Member-password-123!', 'name': 'Member', 'role': 'member',
    })
    assert created.status_code == 200, created.text
    member = created.json()['data']
    login = client.post('/api/auth/login', json={'email': member['email'], 'password': 'Member-password-123!'})
    assert login.status_code == 200
    headers = {'Authorization': 'Bearer ' + login.json()['token']}
    response = client.patch(f"/api/auth/members/{member['id']}/role", headers=headers, json={'role': 'owner'})
    assert response.status_code == 403
    assert client.get('/api/customers/', headers=headers).status_code == 403
    assert client.post('/api/communications/whatsapp', headers=headers, json={'phone': '9000000000', 'message': 'Hello'}).status_code == 403


def test_inactive_account_cannot_login(client, account, db_session):
    from app.models import User
    user = db_session.get(User, account['user']['id'])
    user.is_active = False
    db_session.commit()
    response = client.post('/api/auth/login', json={'email': account['payload']['email'], 'password': account['payload']['password']})
    assert response.status_code == 401
