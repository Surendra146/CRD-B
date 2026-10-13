"""Verify the frozen replacement preserves every authorization check."""
from pathlib import Path


def test_establish_only_removes_global_expired_context_cleanup():
    root = Path(__file__).resolve().parents[2] / 'alembic' / 'authorization'
    previous = (root / 'f91c320ab006.sql').read_text()
    start = previous.index('CREATE FUNCTION hanuram_auth.establish(')
    end = previous.index('\nCREATE FUNCTION hanuram_auth.register_account()', start)
    previous = previous[start:end].strip()
    current = (root / 'f91c320ab008.sql').read_text()
    start = current.index('CREATE OR REPLACE FUNCTION hanuram_auth.establish(')
    end = current.index('-- Bounded retention', start)
    current = current[start:end].strip()
    expected = previous.replace('CREATE FUNCTION', 'CREATE OR REPLACE FUNCTION', 1).replace(
        "    DELETE FROM hanuram_auth.contexts WHERE expires < clock_timestamp()-interval '5 minutes';",
        '    -- Retention is operator maintenance, never part of request authorization.')
    assert current == expected
