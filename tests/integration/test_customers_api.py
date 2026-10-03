import pytest

pytestmark = pytest.mark.integration


def test_customer_crud_and_jsonb_roundtrip(client, account, customer_payload):
    headers = account["headers"]
    created = client.post("/api/customers/", headers=headers, json=customer_payload)
    assert created.status_code == 200, created.text
    customer_id = created.json()["data"]["id"]
    fetched = client.get(f"/api/customers/{customer_id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["data"]["tags"] == ["vip"]
    assert fetched.json()["data"]["demographics"] == {"city": "Pune"}
    updated = client.put(f"/api/customers/{customer_id}", headers=headers, json={"name": "Updated customer", "tags": ["returning"]})
    assert updated.status_code == 200
    assert updated.json()["data"]["name"] == "Updated customer"
    listed = client.get("/api/customers/", headers=headers).json()
    assert listed["pagination"]["total"] == 1
    assert client.delete(f"/api/customers/{customer_id}", headers=headers).status_code == 200
    assert client.get(f"/api/customers/{customer_id}", headers=headers).status_code == 404


def test_duplicate_customer_rejected(client, account, customer_payload):
    assert client.post("/api/customers/", headers=account["headers"], json=customer_payload).status_code == 200
    assert client.post("/api/customers/", headers=account["headers"], json=customer_payload).status_code == 409


def test_tenant_cannot_read_change_or_delete_another_tenants_customer(client, account_factory, customer_payload):
    owner, stranger = account_factory(), account_factory()
    created = client.post("/api/customers/", headers=owner["headers"], json=customer_payload)
    assert created.status_code == 200
    customer_id = created.json()["data"]["id"]
    headers = stranger["headers"]
    assert client.get(f"/api/customers/{customer_id}", headers=headers).status_code == 404
    assert client.put(f"/api/customers/{customer_id}", headers=headers, json={"name": "Stolen"}).status_code == 404
    assert client.delete(f"/api/customers/{customer_id}", headers=headers).status_code == 404
    assert client.get("/api/customers/", headers=headers).json()["data"] == []
    assert client.get(f"/api/customers/{customer_id}", headers=owner["headers"]).json()["data"]["name"] == customer_payload["name"]


def test_customer_payload_validation(client, account, customer_payload):
    assert client.post("/api/customers/", headers=account["headers"], json={}).status_code == 422
    assert client.post("/api/customers/", headers=account["headers"], json={**customer_payload, "customerCreatedDate": "invalid-date"}).status_code == 400


def test_customer_endpoints_require_authentication(client):
    assert client.get("/api/customers/").status_code == 401
