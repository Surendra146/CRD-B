from pathlib import Path
import subprocess
from dotenv import dotenv_values

backend = Path(__file__).resolve().parents[1]
frontend = Path(r'D:\web apps\React\CBD project')
values = dotenv_values(backend / '.env')
secrets = [v for k, v in values.items() if v and len(v) >= 16 and any(word in k.upper() for word in ('SECRET', 'TOKEN', 'PASSWORD', 'DATABASE_URL'))]
for root in (backend, frontend):
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
    files = [root / p for p in tracked if p and not p.endswith('.env.example')]
    if root == frontend:
        files += [p for p in (root / 'dist').rglob('*') if p.is_file()]
    found = []
    for path in files:
        if path.is_file():
            body = path.read_bytes()
            if any(value.encode() in body for value in secrets):
                found.append(str(path.relative_to(root)))
    print(root.name, 'tracked .env:', '.env' in tracked, 'files containing exact configured secrets:', found)
