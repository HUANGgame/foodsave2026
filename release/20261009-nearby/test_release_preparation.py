"""Offline preparation checks for the actual-application SQL validation."""
from pathlib import Path
import ast
import hashlib
import importlib.util
import json
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SOURCE = "f5ea46c7f9ddd8d5277783488188f90d6c4fa5f9"


def load(name):
    spec = importlib.util.spec_from_file_location("actual_" + name, HERE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manifest_covers_actual_runtime_and_tests():
    manifest = json.loads((HERE / "source-hashes.json").read_text())
    assert manifest["commit"] == SOURCE
    assert "backend/foodsave/nearby_queries.py" in manifest["files"]
    for folder in ("backend/foodsave", "backend/tests"):
        for path in (ROOT / folder).rglob("*.py"):
            assert str(path.relative_to(ROOT)) in manifest["files"]
    for name, expected in manifest["files"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected


def test_harness_changes_only_source_pin():
    original = (ROOT / "release/20261006/validate_sql.py").read_text()
    expected = original.replace(
        "e5290df728a85a2b50b228a3d8ef1b601971f9f0", SOURCE)
    assert (HERE / "validate_sql.py").read_text() == expected


def test_migrations_and_connection_guards_without_connecting():
    observer = load("validate_sql_wif_observed")
    adapter, harness, batches = observer.load_adapter()
    assert len(batches) == 14
    assert harness.SOURCE == SOURCE == adapter.APPLICATION_COMMIT
    assert observer.no_connect_checks(adapter, harness) >= 19
    assert "foodsave-validation-20261006" in dict(batches)["012_account_lifecycle.sql"]


def test_observer_cannot_replace_queries():
    source = (HERE / "validate_sql_wif_observed.py").read_text()
    assert "before_execute" not in source
    assert "specialize_nearby" not in source
    assert '"sql_behavior_changed": False' in source
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute):
                    assert target.attr not in {"STORES_SQL", "PRODUCTS_SQL", "query"}


def test_historical_files_and_application_remain_pinned():
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", SOURCE, "HEAD", "--", ".",
         ":(exclude)release/20261009-nearby",
         ":(exclude)azure-pipelines-sql-actual-nearby-20261009.yml"],
        cwd=ROOT, text=True)
    assert not changed.strip()
