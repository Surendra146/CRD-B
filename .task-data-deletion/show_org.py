from pathlib import Path
path = Path(r'D:\web apps\React\CBD project\src\Pages\CLC\Settings.jsx')
s = path.read_text(encoding='utf-8')
before = '<p className="mt-1 text-xs text-gray-500">Tenant Code: {tenantCode}</p>'
after = before + '\n              <p className="mt-1 text-xs text-gray-500">Organization ID: {user?.organization_id || user?.organizationId || user?.organization?.id || \'Not available\'}</p>'
assert before in s
path.write_text(s.replace(before, after), encoding='utf-8')
