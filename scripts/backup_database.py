"""Create a custom-format PostgreSQL backup without credentials in command arguments."""
import argparse
import os
import subprocess
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import make_url


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    destination = Path(args.output).resolve()
    if destination.exists():
        raise SystemExit('Refusing to overwrite an existing backup')
    raw = os.getenv('BACKUP_DATABASE_URL') or os.getenv('CONTROL_DATABASE_URL')
    if not raw:
        raise SystemExit('BACKUP_DATABASE_URL or CONTROL_DATABASE_URL is required')
    url = make_url(raw.replace('postgres://', 'postgresql://', 1))
    if url.get_backend_name() != 'postgresql':
        raise SystemExit('PostgreSQL is required')
    environment = os.environ.copy()
    environment.update(PGHOST=url.host or 'localhost', PGPORT=str(url.port or 5432),
        PGDATABASE=url.database or '', PGUSER=url.username or '', PGPASSWORD=url.password or '',
        PGSSLMODE=url.query.get('sslmode', 'require'))
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(['pg_dump', '--format=custom', '--no-owner', '--no-acl', '--file', str(destination)],
            env=environment, check=True, capture_output=True)
        subprocess.run(['pg_restore', '--list', str(destination)], check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError):
        raise SystemExit('Backup failed; inspect connectivity and pg_dump installation privately') from None
    print('Backup created and archive catalog validated. Restore testing is still required.')


if __name__ == '__main__':
    main()
