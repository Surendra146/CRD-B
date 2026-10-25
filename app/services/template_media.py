"""Private, tenant-owned template files; approval handles and messaging IDs differ."""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote, parse_qsl
from urllib.request import Request
from uuid import uuid4

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError

from app.services.meta_whatsapp import urlopen
from app.config.settings import get_settings
from app.services.media_storage.factory import get_media_storage
from app.services.media_storage.keys import validate_key

LIMITS = {'image': 5 * 1024**2, 'video': 16 * 1024**2, 'document': 100 * 1024**2}


def validate_media(data, claimed):
    if not data:
        raise HTTPException(422, 'Empty media file')
    if len(data) > LIMITS['document']:
        raise HTTPException(413, 'Media exceeds the 100 MB limit')
    if data.startswith(b'\x89PNG\r\n\x1a\n') or data.startswith(b'\xff\xd8\xff'):
        kind, mime = 'image', 'image/png' if data.startswith(b'\x89PNG') else 'image/jpeg'
        try:
            with Image.open(io.BytesIO(data)) as image:
                if image.width * image.height > 40_000_000 or getattr(image, 'n_frames', 1) != 1:
                    raise ValueError()
                image.verify()
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
            raise HTTPException(422, 'Invalid, animated or oversized image') from None
    elif data.startswith(b'%PDF-'):
        kind, mime = 'document', 'application/pdf'
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data), strict=True)
            if reader.is_encrypted or not len(reader.pages):
                raise ValueError()
        except ImportError:
            raise HTTPException(503, 'Install pypdf to enable PDF header uploads') from None
        except Exception:
            raise HTTPException(422, 'Upload a valid unencrypted PDF document') from None
    elif len(data) > 12 and data[4:8] == b'ftyp':
        kind, mime = 'video', 'video/mp4'
        if len(data) > LIMITS[kind]:
            raise HTTPException(413, 'Video exceeds the 16 MB limit')
        # ffprobe validates codecs and container; file extension is never trusted.
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'video.mp4'
            path.write_bytes(data)
            try:
                probe = subprocess.run([os.getenv('WHATSAPP_FFPROBE', 'ffprobe'), '-v', 'error', '-show_streams',
                                        '-show_format', '-of', 'json', str(path)], capture_output=True, timeout=25, check=True)
                details = json.loads(probe.stdout)
                streams = details.get('streams') or []
                videos = [s for s in streams if s.get('codec_type') == 'video']
                audio = [s for s in streams if s.get('codec_type') == 'audio']
                if len(videos) != 1 or videos[0].get('codec_name') != 'h264' or len(audio) > 1 or any(s.get('codec_name') != 'aac' for s in audio):
                    raise ValueError()
            except FileNotFoundError:
                raise HTTPException(503, 'Video validation requires ffprobe; configure WHATSAPP_FFPROBE') from None
            except (subprocess.SubprocessError, ValueError):
                raise HTTPException(422, 'Video must be a valid MP4 with H.264 video and optional single AAC audio track') from None
    else:
        raise HTTPException(422, 'Supported template media: JPEG, PNG, H.264/AAC MP4 and PDF')
    if claimed and claimed.split(';')[0].lower() not in {mime, 'application/octet-stream'}:
        raise HTTPException(422, 'Declared MIME type does not match file contents')
    if len(data) > LIMITS[kind]:
        raise HTTPException(413, f'{kind} exceeds the {LIMITS[kind] // 1024**2} MB limit')
    return kind, mime


def asset_key(row, asset_id):
    if not re.fullmatch(r'[a-f0-9]{32}', str(asset_id)):
        raise HTTPException(404, 'Media asset not found')
    try:
        return validate_key(f'{row.tenant_id}/{row.organization_id}/{row.id}/{asset_id}')
    except ValueError:
        raise HTTPException(404, 'Media asset not found') from None


def asset_path(row, asset_id):
    """Compatibility helper for existing local tooling; never used for R2 reads."""
    from app.services.media_storage.local import LocalMediaStorage
    return LocalMediaStorage(get_settings().whatsapp_template_media_root)._path(asset_key(row, asset_id))


def asset(row, asset_id, kind=None):
    entry = next((a for a in (row.workflow or {}).get('assets', []) if a['id'] == asset_id), None)
    if not entry or (kind and entry['type'].upper() != kind.upper()):
        raise HTTPException(422, 'Select an owned asset matching the approved header type')
    key = asset_key(row, asset_id)
    try:
        data = get_media_storage().get(key)
    except (OSError, ValueError):
        raise HTTPException(409, 'Stored media is unavailable. Upload it again and reselect the asset') from None
    if hashlib.sha256(data).hexdigest() != entry['sha256']:
        raise HTTPException(409, 'Stored media changed. Upload the file again')
    return entry, data


def store_asset(row, data, claimed, filename):
    kind, mime = validate_media(data, claimed)
    identifier = uuid4().hex
    key = asset_key(row, identifier)
    try:
        get_media_storage().put(key, data)
    except (OSError, ValueError):
        raise HTTPException(503, 'Media storage is temporarily unavailable') from None
    entry = {'id': identifier, 'type': kind, 'mime': mime, 'size': len(data),
             'name': re.sub(r'[^\w. -]', '_', str(filename or 'media').replace('\\', '/').split('/')[-1])[:150],
             'sha256': hashlib.sha256(data).hexdigest()}
    row.workflow = {**(row.workflow or {}), 'assets': [*(row.workflow or {}).get('assets', []), entry]}
    return entry


def provider_upload(connection, path, data, headers):
    url = f'https://graph.facebook.com/{connection.whatsapp_graph_version}/{path}'
    request = Request(url, data=data, method='POST', headers={'Authorization': 'OAuth ' + connection.whatsapp_access_token, **headers})
    try:
        with urlopen(request, timeout=60) as response:
            result = json.loads(response.read(1_000_000))
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        raise HTTPException(502, 'Meta media upload failed. Verify file format, connection permissions and retry the upload') from None


def sample_handle(row, asset_id, connection):
    entry, data = asset(row, asset_id)
    app_id = get_settings().meta_app_id
    if not re.fullmatch(r'\d+', app_id or ''):
        raise HTTPException(503, 'META_APP_ID is required for approval sample uploads')
    params = urlencode({'file_name': entry['name'], 'file_length': len(data), 'file_type': entry['mime']})
    session = provider_upload(connection, app_id + '/uploads?' + params, b'', {})
    upload_id = session.get('id')
    if not isinstance(upload_id, str) or not upload_id.startswith('upload:'):
        raise HTTPException(502, 'Meta did not return a sample upload session')
    identifier, separator, query = upload_id.partition('?')
    path = quote(identifier, safe=':')
    if separator:
        path += '?' + urlencode(parse_qsl(query, keep_blank_values=True))
    result = provider_upload(connection, path, data, {'file_offset': '0', 'Content-Type': 'application/octet-stream'})
    if not isinstance(result.get('h'), str):
        raise HTTPException(502, 'Meta did not return an approval sample handle')
    return result['h']


def sending_media(row, asset_id, connection, kind):
    entry, data = asset(row, asset_id, kind)
    # Fresh messaging upload, never the resumable sample handle. Worker can reupload
    # from durable private storage even after an earlier messaging ID expires.
    boundary = uuid4().hex
    extension = {'image/jpeg': 'jpg', 'image/png': 'png', 'video/mp4': 'mp4', 'application/pdf': 'pdf'}[entry['mime']]
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="messaging_product"\r\n\r\nwhatsapp\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="media.{extension}"\r\n'
            f'Content-Type: {entry["mime"]}\r\n\r\n').encode() + data + f'\r\n--{boundary}--\r\n'.encode()
    result = provider_upload(connection, connection.whatsapp_phone_number_id + '/media', body,
                             {'Content-Type': f'multipart/form-data; boundary={boundary}',
                              'Authorization': 'Bearer ' + connection.whatsapp_access_token})
    if not re.fullmatch(r'\d+', str(result.get('id') or '')):
        raise HTTPException(502, 'Meta did not return a send-time media ID')
    return str(result['id'])
