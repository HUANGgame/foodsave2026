"""No-connect preparation tests. These do not claim SQL Server execution."""
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
spec = importlib.util.spec_from_file_location("upgrade_preparation", HERE / "validate_upgrade.py")
upgrade = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upgrade)


class PreparationTests(unittest.TestCase):
    def test_all_sql_entrypoints_locked_before_dependencies_or_connection(self):
        self.assertIsNone(upgrade.APPROVED_SQL_PIPELINE_ID)
        with patch.dict(os.environ, {"SYSTEM_DEFINITIONID": "6", "TF_BUILD": "True"}):
            for action in (upgrade.sql_gate, upgrade.run_authorized_sql,
                           lambda: upgrade.run_upgrade([], None)):
                with self.assertRaisesRegex(upgrade.GuardFailed, "sql_execution_not_authorized"):
                    action()

    def test_cli_rejects_sql_and_plan_is_honest(self):
        with patch("sys.argv", ["validate_upgrade.py", "--run-rollback"]):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(upgrade.main(), 1)
            self.assertFalse(json.loads(out.getvalue())["sql_execution_enabled"])
        with patch("sys.argv", ["validate_upgrade.py"]):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(upgrade.main(), 0)
            plan = json.loads(out.getvalue())
            self.assertEqual(plan["status"], "prepared_not_sql_tested")
            self.assertFalse(plan["connects"])
            self.assertFalse(plan["authenticates"])
            self.assertEqual(plan["migration_count"], 14)
            self.assertEqual(tuple(plan["scenarios"]), upgrade.SCENARIOS)

    def test_exact_pinned_batches_and_guarded_test_database(self):
        observer, adapter, harness, batches = upgrade.load_pins()
        self.assertEqual(harness.SOURCE, upgrade.SOURCE)
        self.assertEqual(adapter.DATABASE, "foodsave-validation-20261006")
        self.assertGreaterEqual(observer.no_connect_checks(adapter, harness), 19)
        for name, sql in batches:
            raw = (upgrade.ROOT / "backend/migrations" / name).read_text()
            if name.startswith("012_"):
                raw = raw.replace(
                    "IF DB_NAME()<>N'foodsave' THROW 51000,'Dedicated foodsave database required',1;",
                    "IF DB_NAME()<>N'foodsave-validation-20261006' THROW 51000,'Validation database required',1;")
            self.assertEqual(sql, raw)

    def test_migration_batches_are_separate_and_second_pass_is_zero(self):
        ledger, executed = set(), []
        def fake_query(c, statement, **params):
            if statement.startswith("SELECT"):
                return SimpleNamespace(first=lambda: params["v"] in ledger)
            self.assertTrue(statement.startswith("INSERT"))
            ledger.add(params["v"])
        conn = SimpleNamespace(exec_driver_sql=executed.append)
        batches = [("013.sql", "batch one"), ("014.sql", "batch two")]
        with patch.object(upgrade, "query", fake_query):
            self.assertEqual(upgrade.apply(conn, batches), 2)
            self.assertEqual(upgrade.apply(conn, batches), 0)
        self.assertEqual(executed, ["batch one", "batch two"])

    def test_savepoint_never_used_for_doomed_or_absent_transaction(self):
        for state in (-1, 0, 1):
            rolled = []
            conn = SimpleNamespace(exec_driver_sql=lambda sql: SimpleNamespace(scalar_one=lambda: state))
            point = SimpleNamespace(rollback=lambda: rolled.append(True))
            if state == 1:
                upgrade.rollback_savepoint(conn, point)
                self.assertEqual(rolled, [True])
            else:
                with self.assertRaises(upgrade.GuardFailed):
                    upgrade.rollback_savepoint(conn, point)
                self.assertEqual(rolled, [])

    def test_identity_context_guards_and_empty_catalog(self):
        adapter = SimpleNamespace(EXPECTED_CLIENT_ID="1424737d-18e2-4e47-acea-9c2d7aa123e7")
        valid = [upgrade.DATABASE, 1, adapter.EXPECTED_CLIENT_ID, 0]
        def check(values):
            answers = iter(values)
            conn = SimpleNamespace(exec_driver_sql=lambda sql:
                                   SimpleNamespace(scalar_one=lambda: next(answers)))
            upgrade.check_context(conn, adapter, empty=True)
        check(valid)
        for index, value in ((0, "foodsave"), (1, 0), (2, "wrong"), (3, 1)):
            values = list(valid)
            values[index] = value
            with self.assertRaises(upgrade.GuardFailed):
                check(values)

    def test_no_commit_or_grant_path(self):
        source = (HERE / "validate_upgrade.py").read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                self.assertNotEqual(node.func.attr, "commit")
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                self.assertNotRegex(node.value, r"(?i)\b(?:COMMIT TRAN|GRANT |CREATE USER|ALTER ROLE)")
        self.assertIn("poolclass=NullPool", source)
        self.assertIn("pyodbc.pooling = False", source)
        self.assertIn("outer.rollback()", source)
        self.assertIn("fresh_schema_namespace_unchanged", source)


if __name__ == "__main__":
    unittest.main()
