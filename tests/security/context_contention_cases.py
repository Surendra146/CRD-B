"""Lock regressions for the disposable, restricted-login authorization sandbox."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import time
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session


def seed_expired(operator):
    marker = str(uuid4())
    with operator.begin() as connection:
        connection.execute(text('SET LOCAL ROLE hanuram_identity_owner'))
        connection.execute(text("""
            INSERT INTO hanuram_auth.contexts VALUES
            (-1,:marker,'hanuram_control','{}',clock_timestamp()-interval '10 minutes')
        """), {'marker': marker})
    return marker


def count_marker(operator, marker):
    with operator.begin() as connection:
        connection.execute(text('SET LOCAL ROLE hanuram_identity_owner'))
        return connection.scalar(text('SELECT count(*) FROM hanuram_auth.contexts WHERE xid=:marker'), {'marker': marker})


def reproduce_before_fix(operator, control, runtime):
    """A bounded reproduction: runtime blocks until control rolls back."""
    from app.database.authorization import authorize
    marker = seed_expired(operator)
    with Session(control) as identity, Session(runtime) as tenant:
        authorize(identity, 'identity.email', email='nobody@sandbox.invalid')
        tenant.execute(text("SET LOCAL lock_timeout='500ms'"))
        try:
            authorize(tenant, 'tenant', sub=1, tenant=1, org=1, iat=time.time())
        except DBAPIError as error:
            assert getattr(error.orig, 'sqlstate', None) == '55P03', error
            tenant.rollback()
        else:
            raise AssertionError('Expected old cleanup to block runtime authorization')
        identity.rollback()
    assert count_marker(operator, marker) == 1
    print('Confirmed pre-fix self-blocking: control cleanup holds row; runtime authorization hits lock timeout.', flush=True)


class ContextContentionCases:
    # The sandbox test host supplies these fixtures and unittest helpers.
    if TYPE_CHECKING:
        actor: Any
        assertEqual: Any
        assertIn: Any
        assertRaises: Any
        control: Any
        first: Any
        operator: Any
        runtime: Any
        second: Any
        tenant: Any

    def test_27_overlapping_authorization_does_not_prune_or_wait(self):
        from app.database.authorization import authorize
        marker = seed_expired(self.operator)
        # Simulate another transaction already deleting this row, including
        # an in-flight request from the old release or retention maintenance.
        with self.operator.connect() as locker:
            locker.execute(text('SET LOCAL ROLE hanuram_identity_owner'))
            locker.execute(text('DELETE FROM hanuram_auth.contexts WHERE xid=:marker'), {'marker': marker})
            with Session(self.control) as identity, Session(self.runtime) as tenant:
                identity.execute(text("SET LOCAL lock_timeout='500ms'"))
                tenant.execute(text("SET LOCAL lock_timeout='500ms'"))
                self.actor(identity, self.first)
                self.tenant(tenant, self.first)
                self.assertEqual(tenant.scalar(text('SELECT id FROM tenants')), self.first['tenant_id'])
            locker.rollback()
        self.assertEqual(count_marker(self.operator, marker), 1)

    def test_28_concurrent_control_runtime_authorization(self):
        marker = seed_expired(self.operator)
        barrier = Barrier(4)

        def work(index):
            account = self.first if index % 2 == 0 else self.second
            with Session(self.control) as identity, Session(self.runtime) as tenant:
                identity.execute(text("SET LOCAL lock_timeout='2s'"))
                tenant.execute(text("SET LOCAL lock_timeout='2s'"))
                self.actor(identity, account)
                barrier.wait(timeout=10)
                self.tenant(tenant, account)
                self.assertEqual(tenant.scalar(text('SELECT id FROM tenants')), account['tenant_id'])
                tenant.commit()
                # after_begin must establish authority again after commit.
                self.assertEqual(tenant.scalar(text('SELECT id FROM tenants')), account['tenant_id'])
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(work, range(4)))
        self.assertEqual(count_marker(self.operator, marker), 1)
        self.assertEqual(self.control.pool.checkedout(), 0)
        self.assertEqual(self.runtime.pool.checkedout(), 0)

    def test_29_customer_segment_http_and_isolation_after_expired_context(self):
        from fastapi.testclient import TestClient
        from app.main import create_app
        from app.services.security import create_token
        marker = seed_expired(self.operator)
        headers = {'Authorization': 'Bearer ' + create_token({'userId': self.first['id'], 'tenantId': self.first['tenant_id']})}
        stranger = {'Authorization': 'Bearer ' + create_token({'userId': self.second['id'], 'tenantId': self.second['tenant_id']})}
        code = 'lock-regression-' + str(uuid4())
        payload = {'externalId': code, 'name': code, 'phone': '9876543210',
                   'address': 'Sandbox address', 'customerCreatedDate': '2026-01-01'}
        with TestClient(create_app()) as client:
            created = client.post('/api/customers/', headers=headers, json=payload)
            self.assertEqual(created.status_code, 200, created.text)
            customer_id = created.json()['data']['id']
            for _ in range(2):
                segment = client.post('/api/segments/', headers=headers, json={'name': str(uuid4())})
                self.assertEqual(segment.status_code, 200, segment.text)
                segment_id = segment.json()['data']['id']
                denied = client.put(f'/api/segments/{segment_id}', headers=stranger, json={'name': 'stolen'})
                self.assertEqual(denied.status_code, 404, denied.text)
            self.assertEqual(client.get(f'/api/customers/{customer_id}', headers=stranger).status_code, 404)
            self.assertEqual(client.put(f'/api/customers/{customer_id}', headers=stranger, json={'name': 'stolen'}).status_code, 404)
            # Error paths must release sessions, and later mutations must work.
            self.assertEqual(client.post('/api/customers/', headers=headers, json=payload).status_code, 409)
            self.assertEqual(client.post('/api/customers/', headers=headers, json={}).status_code, 422)
            self.assertEqual(client.get('/api/segments/', headers=headers).status_code, 200)
        self.assertEqual(count_marker(self.operator, marker), 1)
        self.assertEqual(self.control.pool.checkedout(), 0)
        self.assertEqual(self.runtime.pool.checkedout(), 0)

    def test_32_concurrent_customer_and_segment_creation(self):
        from fastapi.testclient import TestClient
        from app.main import create_app
        from app.services.security import create_token
        seed_expired(self.operator)
        barrier = Barrier(4)
        with TestClient(create_app()) as client:
            def work(index):
                account = self.first if index % 2 == 0 else self.second
                headers = {'Authorization': 'Bearer ' + create_token({'userId': account['id'], 'tenantId': account['tenant_id']})}
                code = str(uuid4())
                barrier.wait(timeout=10)
                customer = client.post('/api/customers/', headers=headers, json={
                    'externalId': code, 'name': code, 'phone': '9876543210',
                    'address': 'Concurrent sandbox', 'customerCreatedDate': '2026-01-02'})
                self.assertEqual(customer.status_code, 200, customer.text)
                segment = client.post('/api/segments/', headers=headers, json={'name': code})
                self.assertEqual(segment.status_code, 200, segment.text)
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(work, range(4)))
        self.assertEqual(self.control.pool.checkedout(), 0)
        self.assertEqual(self.runtime.pool.checkedout(), 0)

    def test_33_dependencies_rollback_uncommitted_and_failed_transactions(self):
        from app.database.connection import get_db, get_control_db
        from app.models import Segment
        code = str(uuid4())
        dependency = get_db()
        db = next(dependency)
        try:
            self.tenant(db, self.first)
            db.add(Segment(name=code, code=code, tenant_id=self.first['tenant_id'],
                           organization_id=self.first['organization_id'], created_by=self.first['id']))
            db.flush()
        finally:
            dependency.close()
        with Session(self.runtime) as check:
            self.tenant(check, self.first)
            self.assertEqual(check.scalar(text('SELECT count(*) FROM segments WHERE code=:code'), {'code': code}), 0)
        for factory in (get_db, get_control_db):
            dependency = factory()
            db = next(dependency)
            try:
                with self.assertRaises(DBAPIError):
                    db.execute(text('SELECT 1/0'))
            finally:
                dependency.close()
        self.assertEqual(self.control.pool.checkedout(), 0)
        self.assertEqual(self.runtime.pool.checkedout(), 0)

    def test_30_expired_context_denies_access_without_deletion(self):
        from app.database.authorization import authorize
        with Session(self.runtime) as tenant:
            self.tenant(tenant, self.first)
            identity = tenant.execute(text('SELECT pg_backend_pid(),txid_current()::text')).one()
            tenant.commit()
        # Make a committed historical context expired; retaining it must not
        # give a later transaction on the same pooled connection authority.
        with self.operator.begin() as connection:
            connection.execute(text('SET LOCAL ROLE hanuram_identity_owner'))
            connection.execute(text("UPDATE hanuram_auth.contexts SET expires=clock_timestamp()-interval '10 minutes' WHERE pid=:pid AND xid=:xid"),
                               {'pid': identity[0], 'xid': identity[1]})
        with Session(self.runtime) as tenant:
            self.assertEqual(tenant.scalar(text('SELECT count(*) FROM customers')), 0)
            self.assertEqual(tenant.scalar(text('SELECT hanuram_auth.context()')), {})
        # Expiration inside an open transaction is independently enforced.
        with Session(self.runtime) as tenant:
            authorize(tenant, 'tenant', sub=self.first['id'], tenant=self.first['tenant_id'],
                      org=self.first['organization_id'], iat=time.time(), deadline=time.time()+0.2)
            self.assertEqual(tenant.scalar(text('SELECT id FROM tenants')), self.first['tenant_id'])
            tenant.execute(text('SELECT pg_sleep(0.3)'))
            self.assertEqual(tenant.scalar(text('SELECT hanuram_auth.context()')), {})
            self.assertEqual(tenant.scalar(text('SELECT count(*) FROM tenants')), 0)

    def test_31_maintenance_bounded_skips_locks_and_is_operator_only(self):
        marker = seed_expired(self.operator)
        with self.operator.connect() as locker:
            locker.execute(text('SET LOCAL ROLE hanuram_identity_owner'))
            locker.execute(text('SELECT pid FROM hanuram_auth.contexts WHERE xid=:marker FOR UPDATE'), {'marker': marker})
            with self.operator.begin() as connection:
                connection.execute(text("SET LOCAL lock_timeout='500ms'"))
                removed = connection.scalar(text('SELECT hanuram_auth.prune_contexts(1)'))
                self.assertIn(removed, (0, 1))
            self.assertEqual(count_marker(self.operator, marker), 1)
            locker.rollback()
        with self.operator.begin() as connection:
            # Drain multiple bounded batches; normal live context rows remain.
            while connection.scalar(text('SELECT hanuram_auth.prune_contexts(1000)')):
                pass
        self.assertEqual(count_marker(self.operator, marker), 0)
        for engine in (self.runtime, self.control):
            with Session(engine) as db, self.assertRaises(DBAPIError):
                db.execute(text('SELECT hanuram_auth.prune_contexts(1)'))
        for size in (0, 10001, None):
            with self.operator.begin() as connection, self.assertRaises(DBAPIError):
                connection.scalar(text('SELECT hanuram_auth.prune_contexts(:size)'), {'size': size})


if __name__ == '__main__':
    from test_authorization_roles import assert_sandbox
    from app.database.connection import engine, control_engine
    operator = assert_sandbox()
    try:
        reproduce_before_fix(operator, control_engine, engine)
    finally:
        engine.dispose()
        control_engine.dispose()
        operator.dispose()
