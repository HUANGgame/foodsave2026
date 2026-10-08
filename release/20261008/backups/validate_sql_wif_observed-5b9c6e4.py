"""Observe the pinned rollback harness without changing its SQL or transactions."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import logging
import os
import re
import signal
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE_COMMIT = "b098a613534965235364f18a637efa90459c0a5d"
ADAPTER_BLOB = "e4dd6ec391c012338d0a525a3bed414476f1f0be"
PHASE = "source_pin"
ERRORS = []
OBSERVATION = {"harness_started": False, "fresh_catalog_empty_verified": False}
COUNT_SQL = "SELECT COUNT(*) FROM sys.objects WHERE is_ms_shipped=0"
CONTROL_SQL = "SELECT HAS_PERMS_BY_NAME(DB_NAME(),'DATABASE','CONTROL')"
SID_SQL = ("SELECT CONVERT(varchar(36),CONVERT(uniqueidentifier,sid)) "
           "FROM sys.database_principals WHERE principal_id=USER_ID()")


class GuardFailed(Exception):
    pass


def require(ok):
    if not ok:
        raise GuardFailed()


def mark(label):
    global PHASE
    PHASE = label


def emit(value):
    print(json.dumps(value, sort_keys=True), flush=True)


def digest(statement):
    return hashlib.sha256(statement.encode("utf-8")).hexdigest()


def safe_error(exc, phase=None):
    original = getattr(exc, "orig", exc)
    driver = type(original).__module__ == "pyodbc"
    states, numbers, objects, functions = set(), set(), set(), set()
    unrecognized_object = False
    allowed_objects = {"dbo.stores", "dbo.users", "dbo.products", "dbo.request_results",
                       "visible", "distances", "nearby"}
    allowed_functions = {"SQLExecDirectW", "SQLExecDirect", "SQLExecute",
                         "SQLPrepareW", "SQLPrepare", "SQLDescribeParam",
                         "SQLBindParameter", "SQLSetDescField", "SQLSetDescFieldW",
                         "SQLFetch", "SQLFetchScroll", "SQLMoreResults"}
    if driver:
        args = getattr(original, "args", ())
        if args and isinstance(args[0], str) and re.fullmatch(r"(?:[0-9]{2}|HY|IM)[A-Z0-9]{3}", args[0]):
            states.add(args[0])
        for value in args[1:]:
            if isinstance(value, str):
                numbers.update(int(n) for n in re.findall(
                    r"\((-?\d{1,8})\)(?:\s+\(SQL[A-Za-z0-9_]+\))?(?=\s*(?:;|$))", value))
                for token in re.findall(r"\((SQL[A-Za-z0-9_]+)\)", value):
                    if token in allowed_functions:
                        functions.add(token)
                # Emit only fixed known labels, never captured arbitrary identifiers.
                for token in re.findall(r"Invalid object name '([^'\r\n]{1,128})'", value, re.I):
                    normalized = token.replace("[", "").replace("]", "").lower()
                    if normalized in allowed_objects:
                        objects.add(normalized)
                    else:
                        unrecognized_object = True
    name = type(exc).__name__
    if name not in {"ProgrammingError", "OperationalError", "InterfaceError",
                    "IntegrityError", "DataError", "DatabaseError", "InternalError",
                    "NotSupportedError", "TimeoutError", "GuardFailed", "CheckFailed",
                    "ResourceClosedError", "InvalidRequestError"}:
        name = "Exception"
    return {"phase": phase or PHASE, "error_type": name, "driver_error": driver,
            "sqlstates": sorted(states), "native_numbers": sorted(numbers),
            "invalid_objects": sorted(objects), "unrecognized_invalid_object": unrecognized_object,
            "odbc_functions": sorted(functions)}


def record_error(exc, phase=None, **metadata):
    item = {**safe_error(exc, phase), **metadata}
    ERRORS.append(item)
    emit({"event": "error", **item})


def load_adapter():
    path = ROOT / "release/20261008/validate_sql_wif.py"
    data = path.read_bytes()
    require(hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest() == ADAPTER_BLOB)
    spec = importlib.util.spec_from_file_location("pinned_observed_wif_adapter", path)
    require(spec is not None and spec.loader is not None)
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    module, batches = adapter.read_harness()
    require(adapter.PREPARATION_COMMIT == "1ec5b4ffd89ec1ff4d46b6ac2485b6d91bf99ef8")
    require(adapter.APPLICATION_COMMIT == "e5290df728a85a2b50b228a3d8ef1b601971f9f0")
    return adapter, module, batches


def no_connect_checks(adapter, module):
    class FakeError(Exception):
        __module__ = "pyodbc"
    result = safe_error(FakeError("42000", "[42000] private-text (102) (SQLExecDirectW); private-text (8180)"))
    require(result["sqlstates"] == ["42000"] and result["native_numbers"] == [102, 8180])
    require("private-text" not in json.dumps(result))
    require(safe_error(Exception("private-text (102)"))["native_numbers"] == [])
    require(digest("SELECT 1") == hashlib.sha256(b"SELECT 1").hexdigest())
    known = safe_error(FakeError("42S02", "Invalid object name '[dbo].[products]'. (208) (SQLExecDirectW)"))
    require(known["invalid_objects"] == ["dbo.products"]
            and known["odbc_functions"] == ["SQLExecDirectW"]
            and known["unrecognized_invalid_object"] is False)
    unknown = safe_error(FakeError("42S02", "Invalid object name 'private-secret.table'. (208) (SQLExecDirectW)"))
    require(unknown["invalid_objects"] == [] and unknown["unrecognized_invalid_object"] is True)
    require("private-secret" not in json.dumps(unknown))
    return adapter.no_connect_tests(module) + 6


def verify_fresh(adapter):
    from sqlalchemy import create_engine
    from sqlalchemy.engine import URL
    from sqlalchemy.pool import NullPool
    engine = None
    connection = None
    verified = False
    try:
        mark("fresh_connect")
        engine = create_engine(
            URL.create("mssql+pyodbc", query={"odbc_connect": adapter.CONNECTION}),
            poolclass=NullPool, hide_parameters=True, echo=False,
            connect_args={"timeout": 15})
        connection = engine.connect()
        connection.connection.driver_connection.timeout = 20
        mark("fresh_database")
        require(connection.exec_driver_sql("SELECT DB_NAME()").scalar_one() == adapter.DATABASE)
        mark("fresh_control")
        require(connection.exec_driver_sql(CONTROL_SQL).scalar_one() == 1)
        mark("fresh_identity")
        require(str(connection.exec_driver_sql(SID_SQL).scalar_one()).lower() == adapter.EXPECTED_CLIENT_ID)
        mark("fresh_catalog")
        require(connection.exec_driver_sql(COUNT_SQL).scalar_one() == 0)
        verified = True
        OBSERVATION["fresh_catalog_empty_verified"] = True
        emit({"event": "fresh_catalog", "same_database": True, "control_verified": True,
              "identity_verified": True, "empty_verified": True})
    except BaseException as exc:
        record_error(exc)
    finally:
        mark("fresh_close")
        if connection is not None:
            try:
                connection.close()
            except BaseException as exc:
                record_error(exc)
                verified = False
        if engine is not None:
            try:
                engine.dispose()
            except BaseException as exc:
                record_error(exc)
                verified = False
    return verified


def run_observed(adapter, module, batches):
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    migration_labels = {digest(sql): name for name, sql in batches}
    original_run = module.run
    original_preflight = adapter.metadata_preflight
    sequence = 0

    def before(conn, cursor, statement, parameters, context, executemany):
        nonlocal sequence
        sequence += 1
        fingerprint = digest(statement)
        label = migration_labels.get(fingerprint)
        phase = "migration_batch" if label else PHASE
        metadata = {"sequence": sequence, "phase": phase, "statement_sha256": fingerprint}
        if label is not None:
            metadata["migration"] = label
        context._foodsave_observation = metadata
        emit({"event": "execute_start", **metadata})

    def after(conn, cursor, statement, parameters, context, executemany):
        # This means execute returned, not that every result in a batch was drained.
        emit({"event": "execute_returned", **context._foodsave_observation})

    def on_error(context):
        metadata = getattr(context.execution_context, "_foodsave_observation", {})
        phase = metadata.get("phase", PHASE)
        safe_metadata = {key: value for key, value in metadata.items() if key != "phase"}
        # Emit before SQLAlchemy propagates the error into rollback/finally code.
        record_error(context.original_exception, phase, **safe_metadata)
        # No exception replacement, retry, SQL execution, or connection mutation.

    def preflight(*args, **kwargs):
        mark("adapter_preflight")
        try:
            return original_preflight(*args, **kwargs)
        except BaseException as exc:
            record_error(exc)
            raise

    def observed_run(files):
        OBSERVATION["harness_started"] = True
        mark("harness_sql")
        outcome = None
        primary = None
        try:
            outcome = original_run(files)
        except BaseException as exc:
            primary = exc
            record_error(exc, "harness_exit")
        finally:
            # The original harness has unwound and attempted rollback/close.
            # The unchanged adapter's WIF token callback is still registered.
            signal.alarm(75)
            cleanup_ok = verify_fresh(adapter)
            signal.alarm(0)
        if primary is not None:
            raise primary
        require(cleanup_ok)
        return outcome

    listeners = [("before_cursor_execute", before), ("after_cursor_execute", after),
                 ("handle_error", on_error)]
    registered = []
    try:
        for name, callback in listeners:
            event.listen(Engine, name, callback)
            registered.append((name, callback))
        module.run = observed_run
        adapter.metadata_preflight = preflight
        mark("adapter_identity")
        return adapter.run(module, batches)
    finally:
        module.run = original_run
        adapter.metadata_preflight = original_preflight
        for name, callback in reversed(registered):
            event.remove(Engine, name, callback)


def interrupted(signum, frame):
    raise GuardFailed()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-rollback", action="store_true")
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    for value in (signal.SIGTERM, signal.SIGINT, signal.SIGALRM):
        signal.signal(value, interrupted)
    result = None
    status = "failed"
    try:
        adapter, module, batches = load_adapter()
        checks = no_connect_checks(adapter, module)
        if not args.run_rollback:
            emit({"mode": "plan", "connects": False, "authenticates": False,
                  "base_commit": BASE_COMMIT, "no_connect_checks": checks,
                  "migration_count": len(batches), "sql_behavior_changed": False})
            return 0
        signal.alarm(420)
        result = run_observed(adapter, module, batches)
        status = "passed" if not ERRORS else "failed"
    except BaseException as exc:
        record_error(exc, "wrapper_exit")
    finally:
        signal.alarm(0)
    emit({"event": "summary", "mode": "observed_rollback", "status": status,
          "base_commit": BASE_COMMIT, **OBSERVATION, "errors": ERRORS,
          "harness_result": result, "sql_behavior_changed": False})
    return int(status != "passed")


if __name__ == "__main__":
    sys.exit(main())
