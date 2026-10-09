"""No-connect checks for the definition-10 SQL runner and preserved historical gates."""
import ast
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("upgrade_sql_runner", HERE / "run_upgrade_sql.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def environment():
    return {"SYSTEM_DEFINITIONID": "10", "FOODSAVE_UPGRADE_RUN_ROLLBACK": "true",
            "TF_BUILD": "true", "BUILD_REASON": "Manual",
            "BUILD_SOURCEBRANCH": "refs/heads/foodsave-azure-checks-20261008",
            "AGENT_OS": "Linux", "SYSTEM_TEAMPROJECTID": runner.PROJECT_ID,
            "SYSTEM_TEAMFOUNDATIONCOLLECTIONURI": runner.COLLECTION,
            "FOODSAVE_WIF_TENANT_ID": runner.TENANT, "FOODSAVE_WIF_CLIENT_ID": runner.CLIENT,
            "FOODSAVE_WIF_SERVICE_CONNECTION_ID": runner.ENDPOINT,
            "SYSTEM_ACCESSTOKEN": "offline-fake-not-a-credential"}


def fake_adapter():
    return SimpleNamespace(EXPECTED_TENANT_ID=runner.TENANT, EXPECTED_CLIENT_ID=runner.CLIENT,
        EXPECTED_SERVICE_CONNECTION_ID=runner.ENDPOINT, DATABASE="foodsave-validation-20261006",
        CONNECTION="fixed-offline-test-connection", check_agent_environment=lambda: None)


class RunnerTests(unittest.TestCase):
    def test_exact_definition_and_all_context_guards(self):
        adapter = fake_adapter()
        self.assertEqual(runner.PIPELINE_ID, "10")
        good = environment()
        with patch.dict(os.environ, good, clear=True):
            runner.assert_sql_context(adapter)
        for key in good:
            invalid = {**good, key: ""}
            with patch.dict(os.environ, invalid, clear=True):
                with self.assertRaises(runner.GuardFailed, msg=key):
                    runner.assert_sql_context(adapter)
        for key, value in (("SYSTEM_DEFINITIONID", "9"), ("BUILD_REASON", "IndividualCI"),
                           ("FOODSAVE_UPGRADE_RUN_ROLLBACK", "false"),
                           ("BUILD_SOURCEBRANCH", "refs/heads/main"),
                           ("SYSTEM_ACCESSTOKEN", "$(System.AccessToken)")):
            with patch.dict(os.environ, {**good, key: value}, clear=True):
                with self.assertRaises(runner.GuardFailed):
                    runner.assert_sql_context(adapter)

    def test_adapter_consumed_token_phase_is_exact(self):
        adapter = fake_adapter()
        env = environment()
        env.pop("SYSTEM_ACCESSTOKEN")
        env["FOODSAVE_VALIDATION_ODBC_CONNECTION"] = adapter.CONNECTION
        with patch.dict(os.environ, env, clear=True):
            runner.assert_sql_context(adapter, authenticated=True)
            with self.assertRaises(runner.GuardFailed):
                runner.assert_sql_context(adapter)
        for value in ("", "other-target"):
            with patch.dict(os.environ, {**env, "FOODSAVE_VALIDATION_ODBC_CONNECTION": value}, clear=True):
                with self.assertRaises(runner.GuardFailed):
                    runner.assert_sql_context(adapter, authenticated=True)

    def test_old_gate_and_exact_pins_are_unchanged(self):
        u, observer, adapter, harness, batches = runner.load_pins()
        self.assertIsNone(u.APPROVED_SQL_PIPELINE_ID)
        with self.assertRaises(u.GuardFailed):
            u.sql_gate()
        self.assertEqual(u.SOURCE, runner.SOURCE)
        self.assertEqual(len(batches), 14)
        self.assertGreaterEqual(observer.no_connect_checks(adapter, harness), 19)

    def test_plan_never_calls_runtime_adapter(self):
        with patch("sys.argv", ["run_upgrade_sql.py"]):
            with patch.object(runner, "run_with_adapter", side_effect=AssertionError("must not run")):
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(runner.main(), 0)
        plan = json.loads(out.getvalue())
        self.assertEqual(plan["pipeline_id"], "10")
        self.assertFalse(plan["connects"])
        self.assertFalse(plan["authenticates"])
        self.assertTrue(plan["old_sql_gate_unchanged"])

    def test_proxy_does_not_modify_original_module(self):
        adapter = fake_adapter()
        validator = lambda value: value
        original_run = lambda files: "historical"
        harness = SimpleNamespace(validate_connection=validator, run=original_run)
        seen = []
        def invoke(target, batches):
            self.assertIsNot(target, harness)
            self.assertIs(target.validate_connection, validator)
            seen.append(batches)
            return "fake-adapter-result"
        adapter.run = invoke
        with patch.dict(os.environ, environment(), clear=True):
            with patch.object(runner, "invoke_with_observation",
                              side_effect=lambda a, target, files, observer: a.run(target, files)):
                self.assertEqual(runner.run_with_adapter(None, None, adapter, harness, []),
                                 "fake-adapter-result")
        self.assertIs(harness.run, original_run)
        self.assertEqual(seen, [[]])

    def test_cleanup_failure_never_hides_first_error_or_passes(self):
        u, _, _, _, _ = runner.load_pins()
        original = RuntimeError("synthetic private text")
        with self.assertRaises(RuntimeError) as caught:
            runner.finish_rehearsal(u, original, False, [])
        self.assertIs(caught.exception, original)
        with self.assertRaises(u.GuardFailed):
            runner.finish_rehearsal(u, None, False, list(u.SCENARIOS))
        with self.assertRaises(u.GuardFailed):
            runner.finish_rehearsal(u, None, True, [])
        self.assertTrue(runner.finish_rehearsal(u, None, True, list(u.SCENARIOS))["rollback_verified"])

    def test_error_output_is_sanitized(self):
        _, observer, _, _, _ = runner.load_pins()
        class FakeError(Exception):
            __module__ = "pyodbc"
        runner.ERRORS.clear()
        with contextlib.redirect_stdout(io.StringIO()) as out:
            runner.record_error(observer, FakeError("42000", "private-value (51099)"), "fixture")
        self.assertNotIn("private-value", out.getvalue())
        self.assertEqual(json.loads(out.getvalue())["native_numbers"], [51099])
        runner.ERRORS.clear()

    def test_driver_error_is_captured_before_finally_and_expected_error_is_scoped(self):
        _, observer, _, _, _ = runner.load_pins()
        class FakeError(Exception):
            __module__ = "pyodbc"
        context = SimpleNamespace(original_exception=FakeError("42000", "private-value (51099)"),
                                  statement="SELECT synthetic")
        runner.ERRORS.clear()
        with contextlib.redirect_stdout(io.StringIO()):
            with patch.object(runner, "EXPECTED_INJECTION", False):
                runner.handle_driver_error(context, observer)
            self.assertEqual(runner.ERRORS[-1]["native_numbers"], [51099])
            self.assertIn("statement_sha256", runner.ERRORS[-1])
            before = len(runner.ERRORS)
            context.statement = runner.INJECTION_SQL
            with patch.object(runner, "EXPECTED_INJECTION", True):
                runner.handle_driver_error(context, observer)
                self.assertEqual(len(runner.ERRORS), before)
                context.original_exception = FakeError("42S02", "private-value (208)")
                runner.handle_driver_error(context, observer)
                self.assertEqual(runner.ERRORS[-1]["native_numbers"], [208])
        self.assertNotIn("private-value", json.dumps(runner.ERRORS))
        runner.ERRORS.clear()

    def test_no_gate_mutation_commit_or_permission_sql(self):
        tree = ast.parse((HERE / "run_upgrade_sql.py").read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Attribute):
                        self.assertNotIn(target.attr, {"APPROVED_SQL_PIPELINE_ID", "sql_gate",
                                                      "run_upgrade", "run"})
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                self.assertNotEqual(node.func.attr, "commit")
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                self.assertNotRegex(node.value, r"(?i)\b(?:COMMIT TRAN|GRANT |CREATE USER|ALTER ROLE)")


if __name__ == "__main__":
    unittest.main()
