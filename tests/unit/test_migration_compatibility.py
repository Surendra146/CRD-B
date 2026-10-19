from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import OperationalError

from app.database import migrations


@pytest.fixture
def graph(tmp_path, monkeypatch):
    (tmp_path / "alembic.ini").write_text("[alembic]\nscript_location = alembic\n")
    versions = tmp_path / "alembic" / "versions"
    versions.mkdir(parents=True)
    def add(revision, parent):
        (versions / f"{revision}.py").write_text(
            f"revision = {revision!r}\ndown_revision = {parent!r}\n")
    add("base", None)
    add("latest", "base")
    monkeypatch.setattr(migrations, "PROJECT_ROOT", tmp_path)
    monkeypatch.chdir(tmp_path.parent)
    return add


def connection_for(rows):
    connection = MagicMock()
    connection.execute.return_value.scalars.return_value = rows
    return connection


@pytest.mark.parametrize("actual", [["latest"], ["base"], ["future"], [], [None], [""], ["bad value"], ["latest", "latest"]])
def test_strict_revisions(graph, actual):
    connection = connection_for(actual)
    if actual == ["latest"]:
        migrations.validate_schema_compatibility(connection)
    else:
        with pytest.raises(migrations.SchemaCompatibilityError):
            migrations.validate_schema_compatibility(connection)
    connection.commit.assert_not_called()
    connection.close.assert_not_called()


def test_new_migration_and_multiple_heads(graph):
    assert migrations.migration_heads() == {"latest"}
    graph("branch_a", "latest")
    graph("branch_b", "latest")
    assert migrations.migration_heads() == {"branch_a", "branch_b"}
    migrations.validate_schema_compatibility(connection_for(["branch_b", "branch_a"]))
    with pytest.raises(migrations.SchemaCompatibilityError):
        migrations.validate_schema_compatibility(connection_for(["branch_a"]))


def test_query_failure_is_sanitized(graph, caplog):
    connection = MagicMock()
    connection.execute.side_effect = OperationalError("secret-url", {}, Exception("password"))
    with pytest.raises(migrations.SchemaCompatibilityError) as error:
        migrations.validate_schema_compatibility(connection)
    assert "password" not in str(error.value) + caplog.text
    assert "secret-url" not in str(error.value) + caplog.text


def test_missing_table_and_connection_cleanup(graph):
    engine = create_engine("sqlite://")
    returned = []
    event.listen(engine, "checkin", lambda *args: returned.append(True))
    try:
        with pytest.raises(migrations.SchemaCompatibilityError):
            with engine.connect() as connection:
                migrations.validate_schema_compatibility(connection)
        assert returned == [True]
    finally:
        engine.dispose()


def test_metadata_missing_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(migrations, "PROJECT_ROOT", tmp_path)
    with pytest.raises(migrations.SchemaCompatibilityError):
        migrations.migration_heads()


@pytest.mark.parametrize("compatible", [True, False])
def test_readiness_and_cleanup(graph, monkeypatch, compatible):
    import app.main as main
    settings = main.get_settings()
    monkeypatch.setattr(settings, "require_rls", True)
    runtime, control = MagicMock(), MagicMock()
    for engine in (runtime, control):
        engine.connect.return_value.__enter__.return_value = connection_for(
            ["latest"] if compatible else ["base"])
    monkeypatch.setattr(main, "engine", runtime)
    monkeypatch.setattr(main, "control_engine", control)
    app = main.create_app()
    ready = next(route.endpoint for route in app.routes if getattr(route, "path", None) == "/ready")
    response = ready()
    if compatible:
        assert response["status"] == "ready"
        control.connect.return_value.__exit__.assert_called_once()
    else:
        assert response.status_code == 503
    runtime.connect.return_value.__exit__.assert_called_once()


def test_connection_acquisition_failure(monkeypatch):
    import app.main as main
    engine = MagicMock()
    engine.connect.side_effect = OperationalError("secret-url", {}, Exception("password"))
    monkeypatch.setattr(main, "engine", engine)
    app = main.create_app()
    ready = next(route.endpoint for route in app.routes if getattr(route, "path", None) == "/ready")
    assert ready().status_code == 503


def test_invalid_database_value_is_not_logged(graph, caplog):
    with pytest.raises(migrations.SchemaCompatibilityError):
        migrations.validate_schema_compatibility(connection_for(["postgres://secret:password@host/db"]))
    assert "password" not in caplog.text


def test_empty_migration_graph_fails_closed(graph, monkeypatch):
    monkeypatch.setattr(migrations.ScriptDirectory, "get_heads", lambda self: [])
    with pytest.raises(migrations.SchemaCompatibilityError):
        migrations.migration_heads()


@pytest.mark.parametrize("compatible", [True, False])
def test_real_connection_returned_after_validation(graph, compatible):
    engine = create_engine("sqlite://")
    returned = []
    event.listen(engine, "checkin", lambda *args: returned.append(True))
    try:
        with engine.begin() as connection:
            connection.execute(text("ATTACH DATABASE ':memory:' AS public"))
            connection.execute(text("CREATE TABLE public.alembic_version (version_num VARCHAR(32))"))
            connection.execute(text("INSERT INTO public.alembic_version VALUES (:revision)"),
                               {"revision": "latest" if compatible else "base"})
        returned.clear()
        if compatible:
            with engine.connect() as connection:
                migrations.validate_schema_compatibility(connection)
        else:
            with pytest.raises(migrations.SchemaCompatibilityError):
                with engine.connect() as connection:
                    migrations.validate_schema_compatibility(connection)
        assert returned == [True]
    finally:
        engine.dispose()
