"""Run tests against only the dedicated test URL; never print connection secrets."""
import os
import sys
import argparse
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine import make_url

backend = Path(__file__).resolve().parents[1]
test_url = os.getenv('TEST_DATABASE_URL') or dotenv_values(backend / '.env').get('TEST_DATABASE_URL')
if not test_url:
    raise SystemExit('TEST_DATABASE_URL is required')
url = make_url(test_url)
if url.get_backend_name() != 'postgresql' or not (url.database or '').endswith('_test'):
    raise SystemExit('A dedicated PostgreSQL *_test database is required')
os.environ['TEST_DATABASE_URL'] = test_url
os.chdir(backend)
sys.path.insert(0, str(backend))
import pytest

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--no-migrations', action='store_true', help='Exclude tests that execute migration functions')
args = parser.parse_args()
test_args = ['-q', '--require-db', '-p', 'no:cacheprovider']
if args.no_migrations:
    test_args += ['--ignore=tests/integration/' + name for name in (
        'test_tenant_migration.py', 'test_rls_database.py', 'test_payment_gateway_api.py',
        'test_manual_subscription_migration.py')]
raise SystemExit(pytest.main(test_args))
