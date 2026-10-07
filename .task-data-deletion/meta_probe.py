"""Read-only credential probe. Never prints tokens, secrets, or provider bodies."""
import hashlib
import hmac
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from urllib.error import HTTPError, URLError
from urllib.request import Request
from app.services.meta_whatsapp import require_configuration, urlopen

settings = require_configuration()
proof = hmac.new(settings.meta_app_secret.encode(), settings.whatsapp_access_token.encode(), hashlib.sha256).hexdigest() if settings.meta_app_secret else ''
url = f'https://graph.facebook.com/{settings.whatsapp_graph_version}/{settings.whatsapp_phone_number_id}?fields=id,verified_name,platform_type'
if proof:
    url += '&appsecret_proof=' + proof
request = Request(url, headers={'Authorization': 'Bearer ' + settings.whatsapp_access_token})
try:
    with urlopen(request, timeout=20) as response:
        data = json.load(response)
        print(json.dumps({'meta_read_http': response.status, 'sender_id_matches': data.get('id') == settings.whatsapp_phone_number_id, 'platform': data.get('platform_type'), 'verified_name_present': bool(data.get('verified_name'))}))
except HTTPError as error:
    try:
        code = json.loads(error.read()).get('error', {}).get('code')
    except ValueError:
        code = None
    print(json.dumps({'meta_read_http': error.code, 'meta_error_code': code}))
except (URLError, TimeoutError, OSError):
    print('Meta read-only request could not reach the provider')
    raise SystemExit(2)
