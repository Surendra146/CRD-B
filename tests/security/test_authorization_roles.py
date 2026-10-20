"""Real LOGIN-role tests. Run ONLY through run_authorization_sandbox.py.

Deliberately uses unittest, avoiding the legacy pytest fixtures which replace
database roles and disable RLS. Every application call uses restricted logins.
"""
import json
import os
from pathlib import Path
import sys
import time
import unittest
from uuid import uuid4
from datetime import UTC, datetime, timedelta

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from sqlalchemy import create_engine, text, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from context_contention_cases import ContextContentionCases


def assert_sandbox():
    raw=os.environ.get('AUTHORIZATION_SANDBOX_URL','')
    marker=os.environ.get('AUTHORIZATION_SANDBOX_MARKER','')
    if not raw or not marker:
        raise RuntimeError('Run through scripts/run_authorization_sandbox.py; no existing database is permitted')
    url=make_url(raw)
    if url.host!='127.0.0.1' or url.database != 'hanuram_production_ii23':
        raise RuntimeError('Disposable loopback database required')
    operator=create_engine(url,hide_parameters=True)
    with operator.connect() as connection:
        if connection.scalar(text('SELECT value FROM sandbox_guard.identity'))!=marker:
            raise RuntimeError('Sandbox identity mismatch')
    return operator


@unittest.skipUnless(os.environ.get('AUTHORIZATION_SANDBOX_MARKER') and os.environ.get('REQUIRE_RLS')=='true', 'Use the disposable authorization sandbox runner')
class AuthorizationTests(ContextContentionCases, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.operator=assert_sandbox()
        cls.addClassCleanup(cls.operator.dispose)
        from app.database.connection import engine,control_engine
        from app.routers.auth import register
        from app.schemas.auth import RegisterRequest
        cls.runtime,cls.control=engine,control_engine
        cls.addClassCleanup(cls.runtime.dispose)
        cls.addClassCleanup(cls.control.dispose)
        cls.accounts=[]
        for name in ('staff','tenant_a','tenant_b'):
            with Session(cls.control) as db:
                account=register(RegisterRequest(email=name+'@sandbox.invalid',password='Test-only-password!',name=name),db)
                cls.accounts.append(account['data'])
        cls.staff,cls.first,cls.second=cls.accounts
        with cls.operator.begin() as connection:
            connection.scalar(text("SELECT hanuram_auth.operator_staff('staff@sandbox.invalid',CAST(:permissions AS jsonb),true)"),
                {'permissions':json.dumps(['subscriptions.read','subscriptions.manage','plans.manage','tenants.read','tenants.manage','onboarding.manage','usage.manage','audit.read'])})
        from app.database.authorization import authorize
        from app.models import User
        from app.routers.platform import create_plan,PlanPayload
        with Session(cls.control) as db:
            authorize(db,'identity.user',sub=cls.staff['id'],tenant=cls.staff['tenant_id'],iat=time.time())
            actor=db.get(User,cls.staff['id'])
            create_plan(PlanPayload(id='sandbox_monthly',name='Monthly',amount_minor=12000,interval='monthly',total_cycles=12,whatsapp_numbers=1),actor,db)

    def actor(self,db,account):
        from app.database.authorization import authorize,account_scope
        from app.models import User
        authorize(db,'identity.user',sub=account['id'],tenant=account['tenant_id'],iat=time.time())
        user=db.get(User,account['id'])
        account_scope(db,user)
        return user

    def tenant(self,db,account):
        from app.database.authorization import authorize
        authorize(db,'tenant',sub=account['id'],tenant=account['tenant_id'],org=account['organization_id'],iat=time.time())

    def test_01_roles_force_and_startup(self):
        from app.database.tenancy import verify_authorization_installation,verify_runtime_role
        for engine,name in ((self.runtime,'hanuram_runtime'),(self.control,'hanuram_control')):
            with engine.connect() as connection:
                verify_authorization_installation(connection,name)
                if name=='hanuram_runtime': verify_runtime_role(connection)

    def test_02_unscoped_and_forged_gucs(self):
        for engine in (self.runtime,self.control):
            with Session(engine) as db:
                db.execute(text("SELECT set_config('app.tenant_id',:tenant,true),set_config('app.organization_id',:org,true)"),
                           {'tenant':str(self.first['tenant_id']),'org':str(self.first['organization_id'])})
                self.assertEqual(db.scalar(text('SELECT count(*) FROM users')),0)

    def test_03_private_keys_and_set_role_denied(self):
        for engine in (self.runtime,self.control):
            for statement in ('SELECT * FROM hanuram_auth.signing_keys','SELECT * FROM hanuram_auth.contexts','SET ROLE hanuram_identity_owner','SELECT hanuram_auth.operator_staff(\'staff@sandbox.invalid\',\'["audit.read"]\',true)'):
                with Session(engine) as db, self.assertRaises(DBAPIError):
                    db.execute(text(statement))

    def test_04_tenant_isolation_and_pool_reuse(self):
        with Session(self.runtime) as db:
            self.tenant(db,self.first)
            self.assertEqual(db.scalar(text('SELECT id FROM tenants')),self.first['tenant_id'])
            self.assertIsNone(db.scalar(text('SELECT id FROM users WHERE id=:id'),{'id':self.second['id']}))
            db.commit()
            self.assertEqual(db.scalar(text('SELECT id FROM tenants')),self.first['tenant_id'])
        with Session(self.runtime) as db:
            self.assertEqual(db.scalar(text('SELECT count(*) FROM tenants')),0)

    def test_05_unauthorized_staff_even_with_signed_assertion(self):
        from app.database.authorization import staff_scope
        from fastapi import HTTPException
        with Session(self.control) as db:
            actor=self.actor(db,self.first)
            with self.assertRaises(HTTPException):
                staff_scope(db,actor,'subscriptions.read')

    def test_06_subscription_assignment_retry_and_expiry(self):
        from app.routers.platform import AssignmentPayload,RenewalPayload,CancellationPayload
        from app.services.manual_subscriptions import operate
        from app.services.billing import require_paid_subscription
        from fastapi import HTTPException
        request=uuid4()
        payload=AssignmentPayload(request_id=request,reason='Sandbox assignment',plan_id='sandbox_monthly',
            current_start=datetime.now(UTC)+timedelta(days=1),current_end=datetime.now(UTC)+timedelta(days=31))
        with Session(self.control) as db:
            actor=self.actor(db,self.staff)
            result=operate(db,actor,self.first['tenant_id'],self.first['organization_id'],'assign',payload)
            self.assertEqual(result['data']['effective_status'],'scheduled')
        with Session(self.control) as db:
            actor=self.actor(db,self.staff)
            result=operate(db,actor,self.first['tenant_id'],self.first['organization_id'],'assign',payload)
            self.assertTrue(result['duplicate'])
        with Session(self.runtime) as db:
            self.tenant(db,self.first)
            from app.models import User
            with self.assertRaises(HTTPException): require_paid_subscription(db,db.get(User,self.first['id']))
        with Session(self.control) as db:
            actor=self.actor(db,self.staff)
            result=operate(db,actor,self.first['tenant_id'],self.first['organization_id'],'renew',RenewalPayload(request_id=uuid4(),reason='Renew',days=30))
            self.assertEqual(result['data']['effective_status'],'scheduled')
        with Session(self.control) as db:
            actor=self.actor(db,self.staff)
            result=operate(db,actor,self.first['tenant_id'],self.first['organization_id'],'cancel',CancellationPayload(request_id=uuid4(),reason='Cancel',at_period_end=False))
            self.assertEqual(result['data']['effective_status'],'cancelled')

    def test_07_subscription_without_audit_rolls_back(self):
        from app.database.authorization import staff_scope
        with Session(self.control) as db:
            actor=self.actor(db,self.staff)
            staff_scope(db,actor,'subscriptions.manage',target_tenant=self.first['tenant_id'],target_org=self.first['organization_id'],
                resource='organization:'+str(self.first['organization_id']),action='platform.subscription.cancel',request_id=str(uuid4()),
                fingerprint='test-fingerprint',reason='Missing audit',operation='cancel',operation_payload={'at_period_end':False})
            db.execute(text("UPDATE subscriptions SET status='cancelled',cancel_at_period_end=false WHERE organization_id=:org"),{'org':self.first['organization_id']})
            with self.assertRaises(DBAPIError): db.commit()

    def test_08_identity_lookup_is_exact_email(self):
        from app.database.authorization import authorize
        with Session(self.control) as db:
            authorize(db,'identity.email',email='tenant_a@sandbox.invalid')
            self.assertEqual(db.execute(text('SELECT email FROM users')).scalars().all(),['tenant_a@sandbox.invalid'])

    def test_09_self_escalation_blocked(self):
        with Session(self.control) as db:
            self.actor(db,self.first)
            with self.assertRaises(DBAPIError):
                db.execute(text("UPDATE users SET allowed_modules='[\"platform_admin\"]' WHERE id=:id"),{'id':self.first['id']})

    def test_10_runtime_cannot_modify_subscriptions(self):
        with Session(self.runtime) as db:
            self.tenant(db,self.first)
            with self.assertRaises(DBAPIError):
                db.execute(text("UPDATE subscriptions SET status='active'"))

    def test_11_forged_signature_denied(self):
        with Session(self.control) as db,self.assertRaises(DBAPIError):
            db.execute(text("SELECT hanuram_auth.establish('{}','forged')"))

    def test_12_registration_duplicate_atomic(self):
        from app.routers.auth import register
        from app.schemas.auth import RegisterRequest
        from fastapi import HTTPException
        with Session(self.control) as db,self.assertRaises(HTTPException):
            register(RegisterRequest(email='tenant_a@sandbox.invalid',password='Test-only-password!',name='Duplicate'),db)
        from app.routers.platform import overview
        with Session(self.control) as db:
            result=overview(self.actor(db,self.staff),db)
            self.assertEqual(result['data']['tenants'],3)

    def test_13_login_and_authenticated_http(self):
        from fastapi.testclient import TestClient
        from app.main import create_app
        with TestClient(create_app()) as client:
            invalid=client.post('/api/auth/login',json={'email':'tenant_a@sandbox.invalid','password':'wrong'})
            self.assertEqual(invalid.status_code,401)
            login=client.post('/api/auth/login',json={'email':'tenant_a@sandbox.invalid','password':'Test-only-password!'})
            self.assertEqual(login.status_code,200,login.text)
            headers={'Authorization':'Bearer '+login.json()['token']}
            self.assertEqual(client.get('/api/auth/me',headers=headers).status_code,200)
            self.assertEqual(client.get('/api/platform/subscriptions',headers=headers).status_code,403)
            self.assertEqual(client.get('/api/platform/subscriptions').status_code,403)

    def test_14_upload_scope_validates_stored_owner_and_target(self):
        from app.models import DataUpload,DataUploadRow,Customer
        from app.database.authorization import upload_scope
        from fastapi import HTTPException
        with Session(self.runtime) as db:
            self.tenant(db,self.first)
            upload=DataUpload(tenant_id=self.first['tenant_id'],organization_id=self.first['organization_id'],uploaded_by=self.first['id'],type='customer_details')
            db.add(upload); db.flush(); identity=upload.id
            db.add(DataUploadRow(upload_id=identity,tenant_id=upload.tenant_id,organization_id=upload.organization_id,row_number=1,raw_data={'name':'Customer','phone':'919999999999'}))
            db.commit()
        with Session(self.runtime) as db:
            upload_scope(db,identity,self.first['id'],self.first['tenant_id'],self.first['organization_id'])
            self.assertEqual(db.scalar(text('SELECT id FROM data_uploads')),identity)
            self.assertEqual(db.scalar(text('SELECT count(*) FROM data_upload_rows')),1)
            db.commit()
            self.assertEqual(db.scalar(text('SELECT id FROM data_uploads')),identity)
        with Session(self.runtime) as db,self.assertRaises(HTTPException):
            upload_scope(db,identity,self.second['id'],self.second['tenant_id'],self.second['organization_id'])
        from app.routers.uploads import validate_upload_job
        validate_upload_job(identity,self.first['id'],self.first['tenant_id'],self.first['organization_id'])

    def test_15_campaign_claims_and_forged_broker_scope(self):
        from app.models import WhatsAppBulkJob
        from app.database.authorization import claim_campaign,campaign_scope
        from fastapi import HTTPException
        with Session(self.runtime) as db:
            self.tenant(db,self.first)
            job=WhatsAppBulkJob(tenant_id=self.first['tenant_id'],organization_id=self.first['organization_id'],created_by=self.first['id'],
                title='Scheduled',message_template='Hello',scheduled_at=datetime.now(UTC).replace(tzinfo=None)-timedelta(minutes=1),status='scheduled')
            db.add(job); db.commit(); identity=job.id
        with Session(self.control) as db:
            claim=claim_campaign(db,identity)
            self.assertEqual(claim['actor_id'],self.first['id'])
            self.assertIsNone(claim_campaign(db,identity))
        with Session(self.runtime) as db:
            campaign_scope(db,claim)
            self.assertEqual(db.scalar(text('SELECT id FROM whatsapp_bulk_jobs')),identity)
            self.assertEqual(db.scalar(text('SELECT count(*) FROM data_uploads')),0)
        with Session(self.runtime) as db,self.assertRaises(HTTPException):
            campaign_scope(db,{**claim,'tenant_id':self.second['tenant_id'],'organization_id':self.second['organization_id'],'actor_id':self.second['id']})
        with Session(self.runtime) as db,self.assertRaises(HTTPException):
            campaign_scope(db,{**claim,'lease':str(uuid4())})

    def test_16_webhook_mapping_is_exact_and_has_no_credentials(self):
        from app.models import WhatsAppConnection
        from app.models.saas import ContactConsent,MessageRecord
        from app.database.authorization import lookup_webhook,webhook_scope
        from app.routers.webhooks import apply_change
        from types import SimpleNamespace
        from fastapi import HTTPException
        with Session(self.runtime) as db:
            self.tenant(db,self.first)
            db.add(WhatsAppConnection(tenant_id=self.first['tenant_id'],organization_id=self.first['organization_id'],
                phone_number_id='sandbox_phone',waba_id='sandbox_waba',connected_by=self.first['id'],encrypted_access_token='test-only-encrypted-marker'))
            db.add(MessageRecord(tenant_id=self.first['tenant_id'],organization_id=self.first['organization_id'],sender_phone_id='sandbox_phone',
                recipient='919999999999',provider_message_id='sandbox_message',status='sent'))
            db.commit()
        with Session(self.control) as db:
            self.assertIsNone(lookup_webhook(db,'sandbox_phone','other_waba'))
            resolved=lookup_webhook(db,'sandbox_phone','sandbox_waba')
            self.assertNotIn('encrypted_access_token',resolved)
        with Session(self.runtime) as db:
            webhook_scope(db,resolved)
            apply_change(db,SimpleNamespace(**resolved),{'statuses':[{'id':'sandbox_message','status':'delivered','timestamp':str(int(time.time()))}],
                'messages':[{'id':'sandbox_inbound','from':'919999999999','timestamp':str(int(time.time())),'text':{'body':'STOP'}}]})
            db.commit()
            self.assertEqual(db.scalar(text("SELECT status FROM message_records WHERE provider_message_id='sandbox_message'")),'delivered')
            self.assertFalse(db.scalar(text('SELECT opted_in FROM contact_consents')))
            with self.assertRaises(DBAPIError):
                db.execute(text("UPDATE message_records SET recipient='918888888888'"))
        with Session(self.runtime) as db,self.assertRaises(HTTPException):
            webhook_scope(db,{**resolved,'tenant_id':self.second['tenant_id'],'organization_id':self.second['organization_id']})

    def test_34_delivery_guard_and_retry_regression(self):
        from types import SimpleNamespace
        from app.database.authorization import webhook_scope, lookup_webhook
        from app.routers.webhooks import apply_change
        from app.models.saas import MessageRecord
        frozen = (Path(__file__).resolve().parents[2] / 'alembic/authorization/f91c320ab012.sql').read_text()
        previous = frozen.replace("ARRAY['status','status_timestamp','delivery_details','updated_at']",
                                  "ARRAY['status','status_timestamp','updated_at']")
        with Session(self.control) as db:
            resolved = lookup_webhook(db, 'sandbox_phone', 'sandbox_waba')
        def event(state, stamp):
            return {'statuses': [{'id': 'sandbox_message', 'status': state, 'timestamp': str(stamp)}]}
        # Reproduce revision 011's actual trigger failure on restricted runtime SQL.
        with self.operator.begin() as connection:
            connection.execute(text(previous))
        try:
            with Session(self.runtime) as db:
                webhook_scope(db, resolved)
                with self.assertRaises(DBAPIError) as caught:
                    apply_change(db, SimpleNamespace(**resolved), event('read', 2000000000))
                    db.commit()
                self.assertEqual(caught.exception.orig.sqlstate, '42501')
                self.assertIn('Webhook cannot replace message identity', str(caught.exception.orig))
        finally:
            with self.operator.begin() as connection:
                connection.execute(text(frozen))
        # Authorized persistence, replay and older callbacks, across transactions.
        for state, stamp in [('read', 2000000000), ('read', 2000000000), ('sent', 1999999999)]:
            with Session(self.runtime) as db:
                webhook_scope(db, resolved)
                apply_change(db, SimpleNamespace(**resolved), event(state, stamp))
                db.commit()
                record = db.scalar(select(MessageRecord).where(MessageRecord.provider_message_id == 'sandbox_message'))
                self.assertEqual(record.status, 'read')
                self.assertEqual(record.status_timestamp, 2000000000)
                self.assertTrue(record.delivery_details['webhook_received_at'])
                self.assertTrue(record.delivery_details['read_at'])
        # Sender/message identity and ownership remain immutable.
        for column, value in [('recipient', '918888888888'), ('provider_message_id', 'forged'),
                              ('sender_phone_id', 'forged'), ('id', 'forged'),
                              ('tenant_id', self.second['tenant_id']),
                              ('organization_id', self.second['organization_id'])]:
            with Session(self.runtime) as db:
                webhook_scope(db, resolved)
                with self.assertRaises(DBAPIError) as caught:
                    db.execute(text(f"UPDATE message_records SET {column}=:value WHERE provider_message_id='sandbox_message'"), {'value': value})
                self.assertEqual(caught.exception.orig.sqlstate, '42501')
        with Session(self.runtime) as db:
            self.assertEqual(db.execute(text("UPDATE message_records SET delivery_details='{}'::jsonb")).rowcount, 0)
        with Session(self.runtime) as db:
            self.tenant(db, self.second)
            self.assertEqual(db.execute(text("UPDATE message_records SET delivery_details='{}'::jsonb WHERE provider_message_id='sandbox_message'")).rowcount, 0)

    def test_17_staff_read_is_not_mutation_authority(self):
        from app.database.authorization import staff_scope
        with Session(self.control) as db:
            actor=self.actor(db,self.staff)
            staff_scope(db,actor,'subscriptions.read')
            self.assertEqual(db.scalar(text('SELECT count(*) FROM subscriptions')),1)
            self.assertEqual(db.execute(text("UPDATE subscriptions SET status='active'")).rowcount,0)

    def test_18_concurrent_retry_and_conflicting_payload(self):
        from concurrent.futures import ThreadPoolExecutor
        from app.routers.platform import AssignmentPayload
        from app.services.manual_subscriptions import operate
        from fastapi import HTTPException
        payload=AssignmentPayload(request_id=uuid4(),reason='Concurrent retry',plan_id='sandbox_monthly',
            current_start=datetime.now(UTC)-timedelta(days=1),current_end=datetime.now(UTC)+timedelta(days=30))
        def work():
            with Session(self.control) as db:
                return operate(db,self.actor(db,self.staff),self.second['tenant_id'],self.second['organization_id'],'assign',payload)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:work(),range(2)))
        self.assertEqual(sum(bool(result.get('duplicate')) for result in results),1)
        with Session(self.control) as db,self.assertRaises(HTTPException) as caught:
            operate(db,self.actor(db,self.staff),self.second['tenant_id'],self.second['organization_id'],'assign',payload.model_copy(update={'reason':'Changed reason'}))
        self.assertEqual(caught.exception.status_code,409)

    def test_19_expiry_counts_and_period_end_cancellation(self):
        from app.routers.platform import AssignmentPayload,CancellationPayload,overview
        from app.services.manual_subscriptions import operate
        from app.services.billing import require_paid_subscription
        from fastapi import HTTPException
        from app.models import User
        payload=AssignmentPayload(request_id=uuid4(),reason='Expiry',plan_id='sandbox_monthly',
            current_start=datetime.now(UTC)-timedelta(days=1),current_end=datetime.now(UTC)+timedelta(seconds=3))
        with Session(self.control) as db:
            actor=self.actor(db,self.staff)
            operate(db,actor,self.first['tenant_id'],self.first['organization_id'],'assign',payload)
        with Session(self.control) as db:
            result=operate(db,self.actor(db,self.staff),self.first['tenant_id'],self.first['organization_id'],'cancel',
                CancellationPayload(request_id=uuid4(),reason='End of period',at_period_end=True))
            self.assertEqual(result['data']['effective_status'],'active')
        time.sleep(3.2)
        with Session(self.runtime) as db:
            self.tenant(db,self.first)
            with self.assertRaises(HTTPException): require_paid_subscription(db,db.get(User,self.first['id']))
            self.assertEqual(db.scalar(text('SELECT count(*) FROM audit_events')),0)
        with Session(self.control) as db:
            self.assertEqual(overview(self.actor(db,self.staff),db)['data']['active_subscriptions'],1)

    def test_20_invalid_webhook_signature_never_looks_up_database(self):
        from fastapi.testclient import TestClient
        from app.main import create_app
        from unittest.mock import patch
        with TestClient(create_app()) as client,patch('app.routers.webhooks.lookup_webhook') as lookup:
            response=client.post('/api/webhooks/whatsapp',json={'object':'whatsapp_business_account'})
            self.assertEqual(response.status_code,403)
            lookup.assert_not_called()


    def test_21_proofs_expiry_transaction_and_installation_binding(self):
        import hashlib,hmac
        from app.config.settings import get_settings
        for mutation in ({'exp':time.time()-1},{'xid':'0'},{'installation':str(uuid4())},{'pid':0}):
            with Session(self.runtime) as db:
                row=db.execute(text('SELECT pg_backend_pid(),txid_current()::text,session_user,hanuram_auth.installation_id()')).one()
                claims={'purpose':'tenant','sub':self.first['id'],'tenant':self.first['tenant_id'],
                    'org':self.first['organization_id'],'iat':time.time(),'exp':time.time()+60,
                    'aud':'hanuram-postgres-v1','key':'identity','pid':row[0],'xid':row[1],'login':row[2],
                    'installation':str(row[3]),**mutation}
                payload=json.dumps(claims)
                signature=hmac.new(get_settings().database_authorization_keys['identity'].encode(),payload.encode(),hashlib.sha256).hexdigest()
                with self.assertRaises(DBAPIError):
                    db.execute(text('SELECT hanuram_auth.establish(:payload,:signature)'),{'payload':payload,'signature':signature})

    def test_22_read_only_staff_cannot_manage_and_target_mismatch(self):
        from app.database.authorization import staff_scope
        from fastapi import HTTPException
        with self.operator.begin() as connection:
            connection.scalar(text("SELECT hanuram_auth.operator_staff('tenant_b@sandbox.invalid','[\"subscriptions.read\"]',true)"))
        with Session(self.control) as db:
            actor=self.actor(db,self.second)
            staff_scope(db,actor,'subscriptions.read')
            self.assertEqual(db.scalar(text('SELECT count(*) FROM subscriptions')),2)
            with self.assertRaises(HTTPException): staff_scope(db,actor,'subscriptions.manage')
        from app.routers.platform import AssignmentPayload
        from app.services.manual_subscriptions import operate
        with Session(self.control) as db,self.assertRaises(HTTPException) as caught:
            operate(db,self.actor(db,self.staff),self.first['tenant_id'],self.second['organization_id'],'assign',
                AssignmentPayload(request_id=uuid4(),reason='Invalid target',plan_id='sandbox_monthly',
                    current_start=datetime.now(UTC),current_end=datetime.now(UTC)+timedelta(days=30)))
        self.assertEqual(caught.exception.status_code,404)

    def test_23_cross_tenant_insert_denied(self):
        from app.models import Customer
        with Session(self.runtime) as db:
            self.tenant(db,self.first)
            db.add(Customer(name='Rejected',tenant_id=self.second['tenant_id'],organization_id=self.second['organization_id']))
            with self.assertRaises(DBAPIError): db.flush()

    def test_24_celery_outbox_claim_is_scoped_and_serializable(self):
        from app.models import WhatsAppBulkJob
        from app.models.saas import CampaignOutbox
        from app.database.authorization import claim_campaign,campaign_scope
        from app.config.settings import get_settings
        from unittest.mock import patch
        with Session(self.runtime) as db:
            self.tenant(db,self.first)
            job=WhatsAppBulkJob(tenant_id=self.first['tenant_id'],organization_id=self.first['organization_id'],created_by=self.first['id'],
                title='Outbox',message_template='Hello',scheduled_at=datetime.now(UTC).replace(tzinfo=None)-timedelta(minutes=1),status='scheduled')
            db.add(job);db.flush();identity=job.id
            db.add(CampaignOutbox(tenant_id=job.tenant_id,organization_id=job.organization_id,bulk_job_id=identity,status='pending'))
            db.commit()
        with patch.object(get_settings(),'campaign_transport','celery'),Session(self.control) as db:
            claim=claim_campaign(db,identity)
        self.assertIsNotNone(claim)
        json.dumps(claim)
        with Session(self.runtime) as db:
            campaign_scope(db,claim)
            self.assertEqual(db.scalar(text('SELECT status FROM campaign_outbox WHERE bulk_job_id=:job'),{'job':identity}),'published')


    def test_25_member_management_and_password_revocation(self):
        from app.routers.auth import create_member,update_member,change_password
        from app.schemas.auth import MemberCreateRequest,MemberUpdateRequest,ChangePasswordRequest
        from app.services.security import get_current_user,create_token
        from starlette.requests import Request
        from fastapi.security import HTTPAuthorizationCredentials
        from fastapi import HTTPException
        with Session(self.control) as db:
            member=create_member(MemberCreateRequest(email='member@sandbox.invalid',name='Member',password='Test-only-password!',role='member'),self.actor(db,self.first),db)['data']
        with Session(self.control) as db:
            update_member(member['id'],MemberUpdateRequest(name='Renamed'),self.actor(db,self.first),db)
        account={**member,'tenant_id':self.first['tenant_id']}
        old_token=create_token({'userId':member['id'],'tenantId':self.first['tenant_id']})
        with Session(self.control) as db:
            change_password(ChangePasswordRequest(currentPassword='Test-only-password!',newPassword='Changed-test-password!'),self.actor(db,account),db)
        request=Request({'type':'http','method':'GET','headers':[]})
        with Session(self.control) as db,Session(self.runtime) as tenant_db,self.assertRaises(HTTPException):
            get_current_user(request,HTTPAuthorizationCredentials(scheme='Bearer',credentials=old_token),db,tenant_db)

    def test_26_signed_meta_webhook_http_uses_restricted_roles(self):
        import hashlib,hmac
        from fastapi.testclient import TestClient
        from app.main import create_app
        from app.config.settings import get_settings
        payload={'object':'whatsapp_business_account','entry':[{'id':'sandbox_waba','changes':[{'value':{
            'metadata':{'phone_number_id':'sandbox_phone'},'statuses':[{'id':'sandbox_message','status':'read','timestamp':str(int(time.time())+1)}]}}]}]}
        body=json.dumps(payload).encode()
        signature='sha256='+hmac.new(get_settings().meta_app_secret.encode(),body,hashlib.sha256).hexdigest()
        with TestClient(create_app()) as client:
            response=client.post('/api/webhooks/whatsapp',content=body,headers={'content-type':'application/json','x-hub-signature-256':signature})
            self.assertEqual(response.status_code,200,response.text)
        with Session(self.runtime) as db:
            self.tenant(db,self.first)
            self.assertEqual(db.scalar(text("SELECT status FROM message_records WHERE provider_message_id='sandbox_message'")),'read')


    def test_27_managed_onboarding_subscription_gate_and_verified_activation(self):
        from concurrent.futures import ThreadPoolExecutor
        from unittest.mock import patch
        from types import SimpleNamespace
        from app.routers.auth import register
        from app.schemas.auth import RegisterRequest
        from app.routers.saas import request_onboarding, OnboardingPayload, verification_completed
        from app.routers.platform import update_onboarding, OnboardingUpdate, verify_onboarding, VerificationPayload, AssignmentPayload
        from app.services.manual_subscriptions import operate
        from app.services import onboarding
        from app.services.whatsapp_connections import encrypt_token, resolve_credentials
        from app.models import User, WhatsAppConnection
        from app.models.saas import OnboardingRequest, ContactConsent
        from app.config.settings import get_settings
        from fastapi import HTTPException
        with Session(self.control) as db:
            account = register(RegisterRequest(email='onboarding@sandbox.invalid', password='Test-only-password!', name='Onboarding'), db)['data']
        with Session(self.runtime) as db:
            self.tenant(db, account)
            row = request_onboarding(OnboardingPayload(phone='919000000002', business_name='Onboarding business'), db.get(User,account['id']), db)['data']
        def update(status, **values):
            with Session(self.control) as db:
                return update_onboarding(row['id'], OnboardingUpdate(status=status, **values), self.actor(db,self.staff), db)
        with self.assertRaises(HTTPException) as blocked:
            update('accepted')
        self.assertEqual(blocked.exception.detail['code'], 'SUBSCRIPTION_NOT_FOUND')
        with Session(self.runtime) as db:
            self.tenant(db,account)
            self.assertEqual(db.get(OnboardingRequest,row['id']).status,'requested')
            with self.assertRaises(HTTPException):
                request_onboarding(OnboardingPayload(phone='919000000002',business_name='Duplicate'),db.get(User,account['id']),db)
        with Session(self.control) as db:
            operate(db,self.actor(db,self.staff),account['tenant_id'],account['organization_id'],'assign',
                AssignmentPayload(request_id=uuid4(),reason='Onboarding test',plan_id='sandbox_monthly',
                    current_start=datetime.now(UTC)-timedelta(days=1),current_end=datetime.now(UTC)+timedelta(days=1)))
        def accept(_):
            try: update('accepted'); return 'accepted'
            except HTTPException as error: return error.detail['code']
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(accept,range(2)))
        self.assertCountEqual(results,['accepted','INVALID_TRANSITION'])
        update('setup_in_progress')
        update('action_required',customer_message='Authorize the approved business number',required_action='meta_authorization')
        with Session(self.runtime) as db:
            self.tenant(db,account)
            actor=db.get(User,account['id'])
            verification_completed(row['id'],actor,db)
            connection=WhatsAppConnection(tenant_id=account['tenant_id'],organization_id=account['organization_id'],
                waba_id='444555',phone_number_id='333555',display_phone_number='+919000000002',
                encrypted_access_token=encrypt_token('test-only-token',account['tenant_id'],account['organization_id']),
                connected_by=account['id'],is_default=True)
            db.add(connection)
            db.add(ContactConsent(tenant_id=account['tenant_id'],organization_id=account['organization_id'],phone='919000000003',opted_in=True))
            db.commit()
            with self.assertRaises(HTTPException): resolve_credentials(db,actor)
        update('setup_in_progress')
        def graph(path,*args,**kwargs):
            if path.endswith('/subscribed_apps'): return {'data':[{'whatsapp_business_api_data':{'id':'111'}}]}
            if path.endswith('/subscriptions'): return {'data':[{'object':'whatsapp_business_account','active':True,'fields':[{'name':'messages'}]}]}
            return {'messages':[{'id':'wamid.onboarding.test'}]}
        assets=[{'waba_id':'444555','phone_number_id':'333555','display_phone_number':'+919000000002'}]
        with patch.object(get_settings(),'meta_app_id','111'),patch.object(onboarding,'authorized_assets',return_value=(assets,None)),patch.object(onboarding,'graph',side_effect=graph):
            with Session(self.control) as db:
                verified=verify_onboarding(row['id'],VerificationPayload(test_phone='919000000003',template_name='approved_test',language='en_US'),self.actor(db,self.staff),db)
                self.assertEqual(verified['data']['verification']['test_result'],'accepted')
            with self.assertRaises(HTTPException) as waiting: update('connected')
            self.assertEqual(waiting.exception.detail['code'],'TEST_DELIVERY_REQUIRED')
            import hashlib,hmac
            from fastapi.testclient import TestClient
            from app.main import create_app
            body=json.dumps({'object':'whatsapp_business_account','entry':[{'id':'444555','changes':[{'value':{
                'metadata':{'phone_number_id':'333555'},'statuses':[{'id':'wamid.onboarding.test','status':'delivered','timestamp':str(int(time.time()))}]}}]}]}).encode()
            signature='sha256='+hmac.new(get_settings().meta_app_secret.encode(),body,hashlib.sha256).hexdigest()
            with TestClient(create_app()) as client:
                result=client.post('/api/webhooks/whatsapp',content=body,headers={'x-hub-signature-256':signature})
                self.assertEqual(result.status_code,200,result.text)
            self.assertEqual(update('connected')['data']['status'],'connected')
        with Session(self.runtime) as db:
            self.tenant(db,account)
            self.assertEqual(resolve_credentials(db,db.get(User,account['id'])).whatsapp_phone_number_id,'333555')
            self.assertEqual(len(db.get(OnboardingRequest,row['id']).history),8)
        from app.routers.platform import onboarding as queue
        with Session(self.control) as db:
            listed=queue(self.actor(db,self.staff),db)['data']
            item=next(item for item in listed if item['id']==row['id'])
            self.assertEqual(item['subscription_status'],'active')
            self.assertEqual(item['status'],'connected')
            self.assertIn('tenant_name',item)
            self.assertNotIn('encrypted_access_token',json.dumps(item))
        # Onboarding staff can read billing for their selected organization but cannot change it.
        from app.database.authorization import staff_scope
        with Session(self.control) as db:
            actor=self.actor(db,self.staff)
            staff_scope(db,actor,'onboarding.manage',target_tenant=account['tenant_id'],target_org=account['organization_id'],resource=row['id'],action='platform.onboarding.updated')
            self.assertEqual(db.execute(text("UPDATE subscriptions SET status='cancelled'")).rowcount,0)


if __name__=='__main__':
    unittest.main(verbosity=2)
