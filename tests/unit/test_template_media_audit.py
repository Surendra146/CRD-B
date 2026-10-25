from unittest.mock import Mock

import pytest

from scripts import audit_template_media as audit


def test_no_config_does_not_connect(monkeypatch, capsys):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    create = Mock(); monkeypatch.setattr(audit, 'create_engine', create)
    assert audit.main() == 2
    create.assert_not_called()
    assert '"total_templates": null' in capsys.readouterr().out


def test_failure_does_not_expose_secrets(monkeypatch, capsys):
    monkeypatch.setenv('ENVIRONMENT', 'production')
    monkeypatch.setenv('DATABASE_URL', 'postgresql://user:secret@private.invalid/database')
    monkeypatch.setattr(audit, 'create_engine', Mock(side_effect=RuntimeError('secret private.invalid')))
    assert audit.main() == 2
    output = capsys.readouterr().out
    assert 'secret' not in output and 'private.invalid' not in output


@pytest.mark.parametrize('elevated', [False, True])
def test_read_only_catalogs_never_count_tenant_rows(elevated):
    connection = Mock()
    role = dict(direct_login=True, app_login=True, rolsuper=elevated,
                rolbypassrls=False, rolcreaterole=False, rolcreatedb=False)
    connection.execute.return_value.mappings.return_value.one.return_value = role
    connection.execute.return_value.mappings.return_value.first.return_value = dict(
        relrowsecurity=True, relforcerowsecurity=True, owns_table=False)
    report = audit.inspect(connection)
    assert report['migration_required'] is None
    assert report['unique_storage_keys'] is None
    statements = [str(call.args[0]) for call in connection.execute.call_args_list]
    assert statements[0].endswith('REPEATABLE READ, READ ONLY')
    assert not any('FROM public.' in sql or 'COUNT(' in sql.upper() for sql in statements)
    assert not any('establish' in sql or 'SET ROLE' in sql for sql in statements)
