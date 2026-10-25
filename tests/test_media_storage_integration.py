"""Real adapters and HTTP routing with injected DB; no external services."""
import copy
import io
import os
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError, ReadTimeoutError
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.exc import IntegrityError

from app.services import template_media as media
from app.services.media_storage.local import LocalMediaStorage
from app.services.media_storage.r2 import R2MediaStorage, StorageUnavailable

KEY = '1/2/3/' + 'a' * 32


def png():
    stream = io.BytesIO()
    Image.new('RGB', (5, 5)).save(stream, 'PNG')
    return stream.getvalue()


@pytest.fixture(params=['local', 'r2'])
def storage(request, tmp_path, monkeypatch):
    if request.param == 'local':
        result = LocalMediaStorage(str(tmp_path / 'objects'))
    else:
        objects = {}
        client = Mock()
        def put(**kw):
            if kw['Key'] in objects:
                raise ClientError({'Error': {'Code': 'PreconditionFailed'}}, 'PutObject')
            objects[kw['Key']] = kw['Body']
        def get(**kw):
            if kw['Key'] not in objects:
                raise ClientError({'Error': {'Code': 'NoSuchKey'}}, 'GetObject')
            return {'Body': io.BytesIO(objects[kw['Key']]), 'ContentLength': len(objects[kw['Key']])}
        client.put_object.side_effect = put
        client.get_object.side_effect = get
        client.delete_object.side_effect = lambda **kw: objects.pop(kw['Key'], None)
        result = R2MediaStorage('https://example.r2.cloudflarestorage.com', 'private', 'test', 'test', client)
    monkeypatch.setattr(media, 'get_media_storage', lambda: result)
    from app.services.media_storage import factory
    monkeypatch.setattr(factory, 'get_media_storage', lambda: result)
    return result


def test_roundtrip_and_exclusive_creation(storage):
    storage.put(KEY, b'original')
    with pytest.raises(FileExistsError):
        storage.put(KEY, b'replacement')
    assert storage.get(KEY) == b'original'
    storage.delete(KEY)
    with pytest.raises(FileNotFoundError):
        storage.get(KEY)


@pytest.mark.parametrize('key', ['../outside', '/1/2/3/' + 'a'*32, '1/2/3/invalid',
                                     '1/2/3/' + 'a'*32 + '/extra', '١/2/3/' + 'a'*32, None])
def test_key_validation(storage, key):
    for operation in (lambda: storage.put(key, b'x'), lambda: storage.get(key), lambda: storage.delete(key)):
        with pytest.raises(ValueError):
            operation()


def test_symlink_escape(tmp_path):
    root, outside = tmp_path / 'root', tmp_path / 'outside'
    root.mkdir(); outside.mkdir()
    try:
        (root / '1').symlink_to(outside, target_is_directory=True)
    except OSError:
        if os.name != 'nt':
            raise
        # Directory junctions do not require Windows Developer Mode.
        result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(root / '1'), str(outside)],
                                capture_output=True)
        assert result.returncode == 0, 'Could not create test junction'
    storage = LocalMediaStorage(str(root))
    for operation in (lambda: storage.put(KEY, b'x'), lambda: storage.get(KEY), lambda: storage.delete(KEY)):
        with pytest.raises(ValueError):
            operation()
    assert list(outside.iterdir()) == []


def test_asset_metadata_integrity_and_worker_upload(storage, monkeypatch):
    row = SimpleNamespace(id=3, tenant_id=1, organization_id=2, workflow={})
    entry = media.store_asset(row, png(), 'image/png', '../../safe.png')
    assert set(entry) == {'id', 'type', 'mime', 'size', 'name', 'sha256'}
    assert entry['name'] == 'safe.png'
    assert media.asset(row, entry['id'])[1] == png()
    other = copy.copy(row); other.organization_id = 999
    with pytest.raises(HTTPException) as error:
        media.asset(other, entry['id'])
    assert error.value.status_code == 409
    connection = SimpleNamespace(whatsapp_graph_version='v23.0', whatsapp_access_token='test', whatsapp_phone_number_id='333')
    monkeypatch.setattr(media, 'get_settings', lambda: SimpleNamespace(meta_app_id='123'))
    sample = Mock(side_effect=[{'id': 'upload:session'}, {'h': 'sample-only'}])
    monkeypatch.setattr(media, 'provider_upload', sample)
    assert media.sample_handle(row, entry['id'], connection) == 'sample-only'
    calls = []
    monkeypatch.setattr(media, 'provider_upload', lambda *args: calls.append(args) or {'id': '999'})
    assert media.sending_media(row, entry['id'], connection, 'IMAGE') == '999'
    assert png() in calls[0][2]
    key = media.asset_key(row, entry['id'])
    storage.delete(key); storage.put(key, b'corrupt')
    with pytest.raises(HTTPException) as error:
        media.asset(row, entry['id'])
    assert error.value.status_code == 409


@pytest.mark.parametrize('error', [ClientError({'Error': {'Code': 'AccessDenied'}}, 'GetObject'),
    EndpointConnectionError(endpoint_url='https://secret.example'),
    ReadTimeoutError(endpoint_url='https://secret.example')])
def test_r2_failures_are_safe(error):
    client = Mock(); client.get_object.side_effect = error
    storage = R2MediaStorage('https://example.com', 'private', 'test', 'test', client)
    with pytest.raises(StorageUnavailable) as caught:
        storage.get(KEY)
    assert 'secret' not in str(caught.value)


def test_bounded_r2_body(monkeypatch):
    import app.services.media_storage.r2 as r2
    monkeypatch.setattr(r2, 'MAX_MEDIA_BYTES', 4)
    client = Mock(); body = io.BytesIO(b'12345')
    client.get_object.return_value = {'Body': body}
    storage = R2MediaStorage('https://example.com', 'private', 'test', 'test', client)
    with pytest.raises(ValueError):
        storage.get(KEY)
    assert body.closed


def test_bounded_local_file(tmp_path, monkeypatch):
    import app.services.media_storage.local as local
    monkeypatch.setattr(local, 'MAX_MEDIA_BYTES', 4)
    storage = LocalMediaStorage(str(tmp_path))
    with pytest.raises(ValueError):
        storage.put(KEY, b'12345')
    path = storage._path(KEY); path.parent.mkdir(parents=True)
    path.write_bytes(b'12345')
    with pytest.raises(ValueError):
        storage.get(KEY)


@pytest.mark.parametrize('endpoint', ['http://example.com', 'https://user:pass@example.com',
                                       'https://example.com?secret=x', 'https://'])
def test_bad_r2_endpoint(endpoint):
    with pytest.raises(ValueError):
        R2MediaStorage(endpoint, 'private', 'test', 'test', Mock())


def test_factory_r2_failure_never_uses_local(monkeypatch):
    from app.services.media_storage import factory
    settings = SimpleNamespace(media_storage_backend='r2', r2_endpoint_url='https://example.com',
        r2_bucket_name='private', r2_access_key_id='test', r2_secret_access_key='test')
    monkeypatch.setattr(factory, 'get_settings', lambda: settings)
    local = Mock(); monkeypatch.setattr(factory, 'LocalMediaStorage', local)
    monkeypatch.setattr(factory, 'R2MediaStorage', Mock(side_effect=StorageUnavailable('Unavailable')))
    with pytest.raises(StorageUnavailable):
        factory.get_media_storage()
    local.assert_not_called()


def test_storage_failure_does_not_publish_metadata(monkeypatch):
    row = SimpleNamespace(id=3, tenant_id=1, organization_id=2, workflow={})
    monkeypatch.setattr(media, 'get_media_storage', lambda: Mock(put=Mock(side_effect=OSError('secret'))))
    with pytest.raises(HTTPException) as error:
        media.store_asset(row, png(), 'image/png', 'test.png')
    assert error.value.status_code == 503
    assert row.workflow == {}


@pytest.fixture
def api(storage, monkeypatch):
    from app.routers import templates
    from app.services import template_workflow
    from app.database.connection import get_db
    from app.services.security import require_organization
    row = SimpleNamespace(id=3, tenant_id=1, organization_id=2, workflow={})
    user = SimpleNamespace(tenant_id=1, organization_id=2)
    db = Mock()
    # Exercise the real ownership query and deny absent scoped records.
    db.scalar.return_value = row
    app = FastAPI(); app.include_router(templates.router, prefix='/api/templates')
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_organization] = lambda: user
    with TestClient(app) as client:
        yield client, db, row, user


def test_http_upload_preview_and_denial(api):
    client, db, row, user = api
    endpoint = '/api/templates/3/media'
    assert client.post(endpoint, files={'file': ('fake.png', b'bad', 'image/png')}).status_code == 422
    response = client.post(endpoint, files={'file': ('image.png', png(), 'image/png')})
    assert response.status_code == 200
    identifier = response.json()['data']['id']
    assert client.get(endpoint + '/' + identifier).content == png()
    db.scalar.return_value = None
    assert client.get(endpoint + '/' + identifier).status_code == 404
    assert client.post(endpoint, files={'file': ('image.png', png(), 'image/png')}).status_code == 404


@pytest.mark.parametrize('scope', ['tenant_id', 'organization_id'])
def test_http_scope_mismatch_denied(api, scope):
    client, db, row, user = api
    entry = media.store_asset(row, png(), 'image/png', 'test.png')
    setattr(user, scope, 999)
    endpoint = '/api/templates/3/media'
    assert client.get(endpoint + '/' + entry['id']).status_code == 404
    assert client.post(endpoint, files={'file': ('test.png', png(), 'image/png')}).status_code == 404


@pytest.mark.parametrize('failure', ['flush', 'constraint', 'ambiguous', 'cleanup'])
def test_transaction_failure(api, storage, failure, monkeypatch, caplog):
    client, db, row, user = api
    old = media.store_asset(row, png(), 'image/png', 'old.png')
    if failure in {'flush', 'cleanup'}:
        db.flush.side_effect = RuntimeError('secret SQL details')
    elif failure == 'constraint':
        db.commit.side_effect = IntegrityError('secret SQL', {}, Exception('secret'))
    else:
        db.commit.side_effect = OSError('secret network details')
    if failure == 'cleanup':
        monkeypatch.setattr(storage, 'delete', Mock(side_effect=OSError('secret credentials')))
    response = client.post('/api/templates/3/media', files={'file': ('new.png', png(), 'image/png')})
    assert response.status_code == 503
    db.rollback.assert_called_once()
    assert 'secret' not in response.text + caplog.text
    new = row.workflow['assets'][-1]
    key = media.asset_key(row, new['id'])
    if failure in {'flush', 'constraint'}:
        with pytest.raises(FileNotFoundError):
            storage.get(key)
    else:
        assert storage.get(key) == png()
    assert media.asset(row, old['id'])[1] == png()
