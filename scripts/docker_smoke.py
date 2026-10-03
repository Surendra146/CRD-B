"""Exercise ONLY the isolated cbd-validation stack on localhost:18080."""
import json
import secrets
import urllib.error
import urllib.request
import uuid

BASE = "http://127.0.0.1:18080"


def request(path, data=None, token=None, headers=None, method=None):
    request_headers = dict(headers or {})
    if data is not None:
        request_headers["Content-Type"] = "application/json"
    if token:
        request_headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(BASE + path, data=json.dumps(data).encode() if data is not None else None, headers=request_headers, method=method)
    try:
        response = urllib.request.urlopen(req, timeout=20)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        body = response.read().decode()
        return response.status, response.headers, body


status, headers, body = request("/")
assert status == 200 and '<html' in body
assert headers.get('X-Content-Type-Options') == 'nosniff'
status, _, body = request("/customers")
assert status == 200 and '<html' in body
status, _, body = request("/health")
assert status == 200 and json.loads(body)['status'] == 'ok'
print('PASS frontend, SPA route, security header, and proxied backend health')

identity = uuid.uuid4().hex
email = f"docker-{identity}@example.com"
password = secrets.token_urlsafe(24)
status, _, body = request('/api/auth/register', {'email': email, 'password': password, 'name': 'Docker validation', 'companyName': f'Validation {identity}'})
assert status == 200, f'Registration status: {status}'
registered = json.loads(body)
assert 'password' not in registered['data']
status, headers, body = request('/api/auth/login', {'email': email, 'password': password})
assert status == 200, f'Login status: {status}'
assert 'Secure' in headers.get('Set-Cookie', '')
login = json.loads(body)
assert 'password' not in login['data']
status, _, body = request('/api/auth/me', token=login['token'])
assert status == 200 and json.loads(body)['data']['email'] == email
status, _, _ = request('/api/auth/me')
assert status == 401
status, _, _ = request('/api/auth/login', {'email': email, 'password': 'incorrect'})
assert status == 401
status, _, _ = request('/api/auth/reset-password', {'email': email, 'password': 'incorrect'})
assert status == 501
print('PASS registration, login, secure cookie, authenticated profile, credential filtering, and rejected invalid access/reset')

for origin, allowed in [('http://localhost', True), ('https://untrusted.onrender.com', False)]:
    status, headers, _ = request('/api/auth/me', headers={'Origin': origin, 'Access-Control-Request-Method': 'GET'}, method='OPTIONS')
    assert (headers.get('Access-Control-Allow-Origin') == origin) == allowed
    assert status == (200 if allowed else 400)
print('PASS CORS trusted origin allowed, unrelated Render origin rejected')
