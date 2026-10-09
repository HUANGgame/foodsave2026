"""Dedicated manual test-database upgrade runner; production and COMMIT are forbidden."""
import argparse
import hashlib
import importlib.util
import json
import logging
import os
from pathlib import Path
import signal
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
PIPELINE_ID = "10"
UPGRADE_BLOB = "dd3190978853febd2270f2afc7483a50a2075f0c"
SOURCE = "f5ea46c7f9ddd8d5277783488188f90d6c4fa5f9"
PROJECT_ID = "b21e6783-ad7f-4899-84a3-8557f8e39bc3"
COLLECTION = "https://dev.azure.com/foodsave2026-huanggame/"
TENANT = "399232fb-17d1-45ca-bda6-5b540441bd62"
CLIENT = "1424737d-18e2-4e47-acea-9c2d7aa123e7"
ENDPOINT = "bed364c8-145a-423d-81e4-5af179a9a9f8"
OBSERVATION = {"harness_started": False, "fresh_catalog_empty_verified": False,
               "fresh_schema_namespace_unchanged": False}
ERRORS = []
EXPECTED_INJECTION = False
INJECTION_SQL = "THROW 51099,'Synthetic upgrade rollback injection',1;"


class GuardFailed(Exception):
    pass


def require(ok):
    if not ok:
        raise GuardFailed()


def emit(value):
    print(json.dumps(value, sort_keys=True), flush=True)


def record_error(observer, exc, phase):
    # Never print exception messages, parameter values, fixture rows or credentials.
    record = observer.safe_error(exc, phase)
    ERRORS.append(record)
    emit({"event": "error", **record})


def load_pins():
    path = ROOT / "release/20261009-upgrade/validate_upgrade.py"
    data = path.read_bytes()
    require(hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest() == UPGRADE_BLOB)
    spec = importlib.util.spec_from_file_location("immutable_upgrade_helpers", path)
    u = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(u)
    require(u.APPROVED_SQL_PIPELINE_ID is None and u.SOURCE == SOURCE)
    observer, adapter, harness, batches = u.load_pins()
    require(adapter.APPLICATION_COMMIT == SOURCE)
    return u, observer, adapter, harness, batches


def assert_sql_context(adapter, authenticated=False):
    require(PIPELINE_ID.isdecimal() and os.environ.get("SYSTEM_DEFINITIONID") == PIPELINE_ID)
    require(os.environ.get("FOODSAVE_UPGRADE_RUN_ROLLBACK") == "true")
    require(os.environ.get("TF_BUILD", "").lower() == "true")
    require(os.environ.get("BUILD_REASON") == "Manual")
    require(os.environ.get("BUILD_SOURCEBRANCH") == "refs/heads/foodsave-azure-checks-20261008")
    require(os.environ.get("AGENT_OS") == "Linux")
    require(os.environ.get("SYSTEM_TEAMPROJECTID", "").lower() == PROJECT_ID)
    require(os.environ.get("SYSTEM_TEAMFOUNDATIONCOLLECTIONURI") == COLLECTION)
    require(os.environ.get("FOODSAVE_WIF_TENANT_ID") == TENANT)
    require(os.environ.get("FOODSAVE_WIF_CLIENT_ID") == CLIENT)
    require(os.environ.get("FOODSAVE_WIF_SERVICE_CONNECTION_ID") == ENDPOINT)
    require(adapter.EXPECTED_TENANT_ID == TENANT and adapter.EXPECTED_CLIENT_ID == CLIENT
            and adapter.EXPECTED_SERVICE_CONNECTION_ID == ENDPOINT
            and adapter.DATABASE == "foodsave-validation-20261006")
    token = os.environ.get("SYSTEM_ACCESSTOKEN", "")
    if authenticated:
        require(not token)
        require(os.environ.get("FOODSAVE_VALIDATION_ODBC_CONNECTION") == adapter.CONNECTION)
    else:
        require(bool(token) and not token.startswith("$("))
        require(not os.environ.get("FOODSAVE_VALIDATION_ODBC_CONNECTION"))
    adapter.check_agent_environment()


def execute_rehearsal(batches, adapter, u, observer):
    global EXPECTED_INJECTION
    assert_sql_context(adapter, authenticated=True)
    OBSERVATION['harness_started'] = True
    from sqlalchemy import create_engine
    from sqlalchemy.engine import URL
    from sqlalchemy.pool import NullPool
    from sqlalchemy.exc import DBAPIError
    import pyodbc
    pyodbc.pooling = False
    engine = create_engine(URL.create("mssql+pyodbc", query={"odbc_connect": adapter.CONNECTION}),
                           poolclass=NullPool, hide_parameters=True, connect_args={"timeout": 15})
    checks, primary, schemas = [], None, None
    cleanup_ok = False
    try:
        with engine.connect() as c:
            c.connection.driver_connection.timeout = 30
            u.check_context(c, adapter, empty=True)
            schemas = [tuple(r) for r in c.exec_driver_sql("SELECT schema_id,name,principal_id FROM sys.schemas ORDER BY schema_id").fetchall()]
            c.rollback()
            outer = c.begin()
            try:
                c.exec_driver_sql(u.SETTINGS)
                c.exec_driver_sql("DECLARE @r int; EXEC @r=sp_getapplock "
                    "@Resource='foodsave:validation-migrate',@LockMode='Exclusive',"
                    "@LockOwner='Transaction',@LockTimeout=10000; "
                    "IF @r<0 THROW 51000,'Migration lock unavailable',1;")
                c.exec_driver_sql("CREATE TABLE dbo.schema_migrations(version varchar(80) PRIMARY KEY,"
                                 "applied_at datetime2 NOT NULL DEFAULT SYSUTCDATETIME())")
                u.require(u.apply(c, batches[:12]) == 12, "baseline_012")
                u.seed(c)
                baseline, metadata = u.data_snapshot(c), u.metadata_snapshot(c)
                u.require(all(len(baseline[t]) == n for t, n in {"users": 4, "sessions": 4,
                        "stores": 2, "products": 2, "reservations": 2, "request_results": 2}.items()),
                        "minimal_synthetic_fixture_counts")
                old = u.query(c, "EXEC dbo.report_stock_loss @vendor_id=:owner,@product_id=:product,"
                            "@expected_revision=1,@expected_pending=1,@actual_available=0",
                            owner=u.identity(2), product=u.identity(22)).mappings().one()
                u.require(old["outcome"] == "not_found", "old_consumer_not_supported")
                u.restored(c, baseline, metadata)
                for count in (1, 2):
                    point = c.begin_nested()
                    try:
                        u.require(u.apply(c, batches[12:12+count]) == count, "injection_stage")
                        raise u.InjectedFailure()
                    except u.InjectedFailure:
                        u.rollback_savepoint(c, point)
                    u.restored(c, baseline, metadata)
                    checks.append(u.SCENARIOS[count-1])
                point = c.begin_nested()
                try:
                    u.success_checks(c, batches, baseline, metadata)
                finally:
                    u.rollback_savepoint(c, point)
                u.restored(c, baseline, metadata)
                checks.append("populated_success")
                u.require(u.apply(c, batches[12:]) == 2, "before_sql_failure")
                EXPECTED_INJECTION = True
                try:
                    c.exec_driver_sql(INJECTION_SQL)
                except DBAPIError as exc:
                    u.require(any("(51099)" in str(value) for value in getattr(exc.orig, "args", ())),
                            "expected_injection_number")
                    u.require(c.exec_driver_sql("SELECT XACT_STATE()").scalar_one() in (-1, 0, 1),
                            "known_transaction_state")
                    emit({"event": "expected_sql_failure", "native_number": 51099})
                    checks.append("sql_throw_full_rollback")
                else:
                    raise u.GuardFailed("injected_sql_error_required")
                finally:
                    EXPECTED_INJECTION = False
            finally:
                outer.rollback()
    except BaseException as exc:
        primary = exc
        record_error(observer, exc, "rehearsal")
    finally:
        signal.alarm(75)
        try:
            with engine.connect() as fresh:
                fresh.connection.driver_connection.timeout = 20
                u.check_context(fresh, adapter, empty=True)
                now = [tuple(r) for r in fresh.exec_driver_sql(
                    "SELECT schema_id,name,principal_id FROM sys.schemas ORDER BY schema_id").fetchall()]
                u.require(schemas is not None and now == schemas, "fresh_schema_namespace_unchanged")
                cleanup_ok = True
                OBSERVATION["fresh_catalog_empty_verified"] = True
                OBSERVATION["fresh_schema_namespace_unchanged"] = True
                emit({"event": "fresh_cleanup", "empty_verified": True, "schema_namespace_unchanged": True})
        except BaseException as cleanup_error:
            record_error(observer, cleanup_error, "fresh_cleanup")
        finally:
            try:
                engine.dispose()
            except BaseException as dispose_error:
                cleanup_ok = False
                record_error(observer, dispose_error, "engine_dispose")
            signal.alarm(0)
    return finish_rehearsal(u, primary, cleanup_ok, checks)


def finish_rehearsal(u, primary, cleanup_ok, checks):
    # Preserve the first failure even if fresh verification also fails.
    if primary is not None:
        raise primary
    u.require(cleanup_ok and tuple(checks) == u.SCENARIOS, "complete_upgrade_rehearsal")
    return {"status": "passed", "checks": checks, "rollback_verified": True,
            "fresh_catalog_empty_verified": True, "commit_tested": False,
            "runtime_permissions_tested": False, "concurrency_tested": False}


def run_with_adapter(u, observer, adapter, harness, batches):
    assert_sql_context(adapter)
    # An explicit interface object avoids modifying either historical harness or gate.
    target = SimpleNamespace(
        validate_connection=harness.validate_connection,
        run=lambda files: execute_rehearsal(files, adapter, u, observer))
    return invoke_with_observation(adapter, target, batches, observer)


def handle_driver_error(context, observer):
    record = observer.safe_error(context.original_exception, "sql_execution")
    if (EXPECTED_INJECTION and record["native_numbers"] == [51099]
            and getattr(context, "statement", None) == INJECTION_SQL):
        return
    statement = getattr(context, "statement", None)
    if isinstance(statement, str):
        record["statement_sha256"] = hashlib.sha256(statement.encode("utf-8")).hexdigest()
    ERRORS.append(record)
    emit({"event": "error", **record})


def invoke_with_observation(adapter, target, batches, observer):
    from sqlalchemy import event
    from sqlalchemy.engine import Engine
    callback = lambda context: handle_driver_error(context, observer)
    event.listen(Engine, "handle_error", callback)
    try:
        return adapter.run(target, batches)
    finally:
        event.remove(Engine, "handle_error", callback)


def interrupted(signum, frame):
    raise GuardFailed()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-rollback", action="store_true")
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    result, observer, status = None, None, "failed"
    for value in (signal.SIGTERM, signal.SIGINT, signal.SIGALRM):
        signal.signal(value, interrupted)
    try:
        u, observer, adapter, harness, batches = load_pins()
        checks = observer.no_connect_checks(adapter, harness)
        if not args.run_rollback:
            emit({"mode": "plan", "source_commit": SOURCE, "pipeline_id": PIPELINE_ID,
                  "connects": False, "authenticates": False, "no_connect_checks": checks,
                  "migration_count": len(batches), "scenarios": u.SCENARIOS,
                  "requires_specific_endpoint_authorization": True,
                  "old_sql_gate_unchanged": u.APPROVED_SQL_PIPELINE_ID is None})
            return 0
        assert_sql_context(adapter)
        signal.alarm(420)
        result = run_with_adapter(u, observer, adapter, harness, batches)
        status = "passed" if not ERRORS else "failed"
    except BaseException as exc:
        if observer is not None:
            record_error(observer, exc, "runner_exit")
        else:
            emit({"event": "error", "phase": "source_pin", "error_type": "GuardFailed"})
    finally:
        signal.alarm(0)
    emit({"event": "summary", "mode": "populated_upgrade_rollback", "status": status,
          "source_commit": SOURCE, "pipeline_id": PIPELINE_ID, **OBSERVATION,
          "errors": ERRORS, "harness_result": result,
          "commit_tested": False, "runtime_permissions_tested": False,
          "concurrency_tested": False, "production_modified": False})
    return int(status != "passed")


if __name__ == "__main__":
    sys.exit(main())
