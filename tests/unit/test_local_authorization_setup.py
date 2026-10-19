from unittest.mock import Mock

import pytest

from scripts.provision_database_authorization_keys import provision_keys, main

KEYS = {'identity': 'i' * 48, 'staff': 's' * 48, 'jobs': 'j' * 48}


def connection(database, operator, current=None):
    db = Mock()
    db.execute.return_value.one.return_value = (database, operator, current or operator)
    db.scalar.side_effect = [99, True, True, True, True, False]
    return db

@pytest.mark.parametrize('local,database,operator', [
    (False, 'hanuram_production_ii23', 'hanuram_production_user'),
    (True, 'hanuram_dev', 'hanuram_dev_user'),
])

def test_explicit_setup_mode_accepts_only_its_database_and_operator(local, database, operator):
    db = connection(database, operator)
    provision_keys(db, KEYS, local_development=local)
    writes = [call for call in db.execute.call_args_list if 'INSERT INTO hanuram_auth.signing_keys' in str(call.args[0])]
    assert len(writes) == 3
    assert {call.args[1]['purpose'] for call in writes} == set(KEYS)


@pytest.mark.parametrize('local,database,operator,current', [
    (False, 'hanuram_dev', 'hanuram_dev_user', None),
    (True, 'hanuram_production', 'hanuram_production_user', None),
    (True, 'hanuram_dev', 'postgres', None),
    (True, 'hanuram_dev', 'hanuram_dev_user', 'another_role'),
])
def test_wrong_target_or_operator_rejected_before_key_access(local, database, operator, current):
    db = connection(database, operator, current)
    with pytest.raises(RuntimeError):
        provision_keys(db, KEYS, local_development=local)
    db.scalar.assert_not_called()


@pytest.mark.parametrize('url', [
    'postgresql://hanuram_dev_user:secret@remote.example/hanuram_dev',
    'postgresql://hanuram_dev_user:secret@localhost/hanuram_production',
    'postgresql://postgres:secret@localhost/hanuram_dev',
    'invalid-url-containing-private-value',
])
def test_local_cli_refuses_wrong_url_before_prompting_for_keys(monkeypatch, capsys, url):
    monkeypatch.setenv('OPERATOR_DATABASE_URL', url)
    monkeypatch.setattr('sys.argv', ['provision', '--apply', '--local-development'])
    prompt = Mock(side_effect=AssertionError('Should not prompt'))
    monkeypatch.setattr('getpass.getpass', prompt)
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    prompt.assert_not_called()
    output = capsys.readouterr().err
    assert 'secret' not in output and 'private-value' not in output
