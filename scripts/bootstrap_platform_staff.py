"""Offline staff provisioning. Separate operator URL; dry run unless --apply."""
import argparse
import json
import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

SCOPES = {'tenants.read', 'tenants.manage', 'plans.manage', 'subscriptions.read',
          'subscriptions.manage', 'onboarding.manage', 'usage.manage', 'audit.read'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--email', required=True)
    parser.add_argument('--permissions', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    permissions = sorted(set(part.strip() for part in args.permissions.split(',')))
    if not permissions or not set(permissions) <= SCOPES:
        parser.error('Unknown staff permission')
    raw = os.environ.get('OPERATOR_DATABASE_URL')
    if not raw:
        parser.error('Set OPERATOR_DATABASE_URL in this process; runtime/control credentials are never used')
    url = make_url(raw.replace('postgres://', 'postgresql://', 1)).set(drivername='postgresql+psycopg')
    engine = create_engine(url, hide_parameters=True, echo=False)
    try:
        with engine.begin() as connection:
            result = connection.scalar(text('SELECT hanuram_auth.operator_staff(:email,CAST(:permissions AS jsonb),:apply)'),
                {'email': args.email.strip().lower(), 'permissions': json.dumps(permissions), 'apply': args.apply})
            print(json.dumps(result))
    except Exception:
        raise SystemExit('Operator staff provisioning failed; no credentials printed. Review operator privileges and active user.') from None
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
