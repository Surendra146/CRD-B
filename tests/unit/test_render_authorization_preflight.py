"""Offline prerequisite tests: no app imports, database connections or migrations."""
import copy
import importlib.util
import io
import os
from contextlib import redirect_stdout
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "render_preflight", Path(__file__).resolve().parents[2] / "scripts" / "render_authorization_preflight.py")
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


def fixture():
    def role(name, login=True, create_role=False):
        return dict(name=name, login=login, superuser=False, bypass_rls=False,
                    create_role=create_role, create_db=False)
    operator = role("migration_operator", create_role=True)
    roles = {name: role(name) for name in ("hanuram_runtime", "hanuram_control")}
    roles[operator["name"]] = operator
    return dict(server_version_num=180000, operator=operator, roles=roles,
                runtime_role="hanuram_runtime", control_role="hanuram_control",
                database_create=True, public_schema_create=True,
                pgcrypto=dict(trusted=True, installed=False, installed_schema=None),
                public_tables=[], unowned_tables=[], application_owned_tables={},
                operator_set_owner={}, application_owner_memberships={})


class PreflightTests(unittest.TestCase):
    def test_non_superuser_operator_supported(self):
        result = preflight.assess(fixture())
        self.assertTrue(result["installation_prerequisites_satisfied"])
        self.assertTrue(result["manual_requirements"])
        self.assertIn("final policies", result["scope"])

    def reject(self, snapshot, expected):
        result = preflight.assess(snapshot)
        self.assertFalse(result["installation_prerequisites_satisfied"])
        self.assertTrue(any(expected in item for item in result["blockers"]), result)

    def test_no_createrole(self):
        data = fixture()
        data["operator"]["create_role"] = False
        self.reject(data, "CREATEROLE")

    def test_missing_schema_create(self):
        data = fixture()
        data["database_create"] = False
        self.reject(data, "CREATE on the database")

    def test_missing_public_create(self):
        data = fixture()
        data["public_schema_create"] = False
        self.reject(data, "CREATE on public")

    def test_unowned_existing_tables(self):
        data = fixture()
        data["unowned_tables"] = ["users"]
        self.reject(data, "does not own")

    def test_application_cannot_be_operator(self):
        data = fixture()
        data["operator"]["name"] = data["runtime_role"]
        self.reject(data, "separate migration/operator")

    def test_superuser_cannot_prove_render_compatibility(self):
        for attribute in ("superuser", "bypass_rls"):
            with self.subTest(attribute=attribute):
                data = fixture()
                data["operator"][attribute] = True
                self.reject(data, "Render-compatible")

    def test_elevated_application_attributes(self):
        for attribute in ("superuser", "bypass_rls", "create_role", "create_db"):
            with self.subTest(attribute=attribute):
                data = fixture()
                data["roles"]["hanuram_control"][attribute] = True
                self.reject(data, "elevated role attributes")

    def test_application_ownership(self):
        data = fixture()
        data["application_owned_tables"]["hanuram_runtime"] = ["users"]
        self.reject(data, "owns public tables")

    def test_pgcrypto_unavailable(self):
        data = fixture()
        data["pgcrypto"] = None
        self.reject(data, "unavailable")

    def test_pgcrypto_untrusted(self):
        data = fixture()
        data["pgcrypto"]["trusted"] = False
        self.reject(data, "not marked trusted")

    def test_owner_transfer_requires_set_role(self):
        data = fixture()
        owner = preflight.OWNER_ROLES[0]
        data["roles"][owner] = dict(name=owner, login=False, superuser=False,
                                   bypass_rls=False, create_role=False, create_db=False)
        self.reject(data, "cannot SET ROLE")
        data["operator_set_owner"][owner] = True
        self.assertTrue(preflight.assess(data)["installation_prerequisites_satisfied"])

    def test_application_owner_membership_rejected(self):
        data = fixture()
        owner = preflight.OWNER_ROLES[0]
        data["roles"][owner] = dict(name=owner, login=False, superuser=False,
                                   bypass_rls=False, create_role=False, create_db=False)
        data["operator_set_owner"][owner] = True
        data["application_owner_memberships"] = {"hanuram_control": {owner: True}}
        self.reject(data, "must not be a member")

    def test_owner_must_be_non_login_unprivileged(self):
        for attribute in ("login", "superuser", "bypass_rls", "create_role", "create_db"):
            data = fixture()
            owner = preflight.OWNER_ROLES[0]
            data["roles"][owner] = dict(name=owner, login=False, superuser=False,
                                       bypass_rls=False, create_role=False, create_db=False)
            data["roles"][owner][attribute] = True
            data["operator_set_owner"][owner] = True
            self.reject(data, "without elevated attributes")

    def test_distinct_application_roles(self):
        data = fixture()
        data["control_role"] = data["runtime_role"]
        self.reject(data, "must be distinct")

    def test_assessment_does_not_mutate_snapshot(self):
        data = fixture()
        before = copy.deepcopy(data)
        preflight.assess(data)
        self.assertEqual(before, data)

    def test_missing_url_does_not_connect_or_load_application_env(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(preflight, "create_engine") as create, redirect_stdout(io.StringIO()):
            self.assertEqual(preflight.main([]), 2)
            create.assert_not_called()

    def test_exception_output_never_discloses_url(self):
        secret = "this-is-an-ephemeral-unit-test-marker"
        output = io.StringIO()
        with patch.dict(os.environ, {"AUTHORIZATION_PREFLIGHT_URL": "postgresql://operator:" + secret + "@localhost/sandbox"}), patch.object(preflight, "create_engine", side_effect=RuntimeError(secret)), redirect_stdout(output):
            self.assertEqual(preflight.main([]), 2)
        self.assertNotIn(secret, output.getvalue())
        self.assertIn("RuntimeError", output.getvalue())


if __name__ == "__main__":
    unittest.main()
