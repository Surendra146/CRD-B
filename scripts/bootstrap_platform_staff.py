"""Operator-only staff membership management; dry run unless --apply is supplied."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv()
from sqlalchemy import select
from app.database.connection import ControlSessionLocal
from app.models import User
from app.models.saas import PlatformStaff
from app.services.audit import audit

SCOPES = {'tenants.read', 'tenants.manage', 'plans.manage', 'subscriptions.read', 'subscriptions.manage', 'onboarding.manage', 'usage.manage', 'audit.read'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--email', required=True)
    parser.add_argument('--permissions', required=True, help='Comma-separated explicit permissions')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    permissions = sorted(set(args.permissions.split(',')))
    if not permissions or not set(permissions) <= SCOPES:
        parser.error('Unknown staff permission')
    with ControlSessionLocal() as db:
        user = db.scalar(select(User).where(User.email == args.email.strip().lower()))
        if not user or not user.is_active:
            raise SystemExit('An existing active user is required')
        print(f'User {user.id}: grant {", ".join(permissions)}; apply={args.apply}')
        if args.apply:
            row = db.get(PlatformStaff, user.id)
            if not row:
                row = PlatformStaff(user_id=user.id)
                db.add(row)
            row.is_active, row.permissions = True, permissions
            audit(db, user, 'platform.staff.permissions.updated', str(user.id), {'permissions': permissions})
            db.commit()


if __name__ == '__main__':
    main()
