"""SELECT-only Azure SQL diagnosis. Plan mode never authenticates or connects."""
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
PHASE = "source_pin"
COUNT_SQL = "SELECT COUNT(*) FROM sys.objects WHERE is_ms_shipped=0"
CONTROL_SQL = "SELECT HAS_PERMS_BY_NAME(DB_NAME(),'DATABASE','CONTROL')"
SID_SQL = ("SELECT CONVERT(varchar(36),CONVERT(uniqueidentifier,sid)) "
           "FROM sys.database_principals WHERE principal_id=USER_ID()")
COMPOUND_SQL = (
    "SELECT DB_NAME(), HAS_PERMS_BY_NAME(DB_NAME(),'DATABASE','CONTROL'), "
    "(SELECT COUNT(*) FROM sys.objects WHERE is_ms_shipped=0), "
    "(SELECT CONVERT(varchar(36),CONVERT(uniqueidentifier,sid)) "
    "FROM sys.database_principals WHERE principal_id=USER_ID())"
)


class GuardFailed(Exception):
    pass


def require(ok):
    if not ok:
        raise GuardFailed()


def mark(value):
    global PHASE
    PHASE = value


def load_adapter():
    path = ROOT / "release/20261008/validate_sql_wif.py"
    data = path.read_bytes()
    require(hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()
            == "e4dd6ec391c012338d0a525a3bed414476f1f0be")
    spec = importlib.util.spec_from_file_location("pinned_wif_adapter", path)
    require(spec is not None and spec.loader is not None)
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    adapter.read_harness()  # Hash/plan checks only. Never call harness.run().
    return adapter


def safe_error(exc):
    original = getattr(exc, "orig", exc)
    states, numbers = set(), set()
    for value in getattr(original, "args", ()):
        if not isinstance(value, str):
            continue
        if re.fullmatch(r"[A-Z0-9]{5}", value):
            states.add(value)
        states.update(re.findall(r"\[([A-Z0-9]{5})\]", value))
        numbers.update(int(n) for n in re.findall(
            r"\((-?\d{1,8})\)(?:\s+\(SQL[A-Za-z0-9_]+\))?(?=\s*(?:;|$))", value))
    return {"phase": PHASE, "error_type": type(exc).__name__,
            "driver_error": type(original).__module__ == "pyodbc",
            "sqlstates": sorted(states), "native_numbers": sorted(numbers)}


def scalar(connection, label, statement):
    mark(label)
    cursor = connection.cursor()
    try:
        row = cursor.execute(statement).fetchone()
        require(row is not None)
        return row[0]
    finally:
        cursor.close()


def close(connection, failures, label):
    if connection is not None:
        mark(label)
        try:
            try:
                connection.rollback()
            finally:
                connection.close()
        except Exception as exc:
            failures.append(safe_error(exc))


def run_readonly(adapter):
    import pyodbc
    from azure.identity import AzurePipelinesCredential
    from sqlalchemy import create_engine, event
    from sqlalchemy.engine import Engine, URL
    from sqlalchemy.pool import NullPool

    mark("agent_identity_guard")
    adapter.check_agent_environment()
    tenant = adapter.guid_environment("FOODSAVE_WIF_TENANT_ID")
    client = adapter.guid_environment("FOODSAVE_WIF_CLIENT_ID")
    endpoint = adapter.guid_environment("FOODSAVE_WIF_SERVICE_CONNECTION_ID")
    require((tenant, client, endpoint) == (
        adapter.EXPECTED_TENANT_ID, adapter.EXPECTED_CLIENT_ID,
        adapter.EXPECTED_SERVICE_CONNECTION_ID))
    job_token = os.environ.pop("SYSTEM_ACCESSTOKEN", "")
    require(bool(job_token) and not job_token.startswith("$("))
    require(not os.environ.get("FOODSAVE_VALIDATION_ODBC_CONNECTION"))
    pyodbc.pooling = False
    require("ODBC Driver 18 for SQL Server" in pyodbc.drivers())
    credential = AzurePipelinesCredential(
        tenant_id=tenant, client_id=client, service_connection_id=endpoint,
        system_access_token=job_token, logging_enable=False, retry_total=1,
        connection_timeout=10, read_timeout=20)
    job_token = None
    failures, completed = [], []
    scoped, empty_verified = False, False

    def open_connection(label):
        mark(label + "_token")
        attrs = {1256: adapter.token_bytes(credential)}
        mark(label + "_connect")
        result = pyodbc.connect(adapter.CONNECTION, attrs_before=attrs,
                                timeout=15, autocommit=False)
        result.timeout = 30
        return result

    try:
        connection = None
        try:
            connection = open_connection("initial")
            require(scalar(connection, "db_name", "SELECT DB_NAME()") == adapter.DATABASE)
            require(scalar(connection, "control", CONTROL_SQL) == 1)
            scoped = True
            require(scalar(connection, "initial_catalog", COUNT_SQL) == 0)
            completed.append("initial_catalog_empty")
            require(str(scalar(connection, "sid_convert", SID_SQL)).lower() == client)
            completed.append("identity_sid_verified")
            mark("original_compound_preflight")
            cursor = connection.cursor()
            try:
                row = cursor.execute(COMPOUND_SQL).fetchone()
                require(row is not None and row[0] == adapter.DATABASE and row[1] == 1
                        and row[2] == 0 and str(row[3]).lower() == client)
            finally:
                cursor.close()
            completed.append("original_compound_preflight")
        except Exception as exc:
            failures.append(safe_error(exc))
        finally:
            close(connection, failures, "initial_close")

        if not failures:
            engine = None
            callback = adapter.token_listener(adapter.read_harness()[0], credential)
            event.listen(Engine, "do_connect", callback)
            try:
                mark("sqlalchemy_engine")
                engine = create_engine(
                    URL.create("mssql+pyodbc", query={"odbc_connect": adapter.CONNECTION}),
                    poolclass=NullPool, hide_parameters=True, echo=False,
                    connect_args={"timeout": 15})
                mark("sqlalchemy_connect_initialize")
                with engine.connect() as connection:
                    connection.connection.driver_connection.timeout = 30
                    mark("sqlalchemy_metadata")
                    require(connection.exec_driver_sql("SELECT DB_NAME()").scalar_one()
                            == adapter.DATABASE)
                    require(connection.exec_driver_sql(COUNT_SQL).scalar_one() == 0)
                    connection.rollback()
                completed.append("sqlalchemy_metadata")
            except Exception as exc:
                failures.append(safe_error(exc))
            finally:
                event.remove(Engine, "do_connect", callback)
                if engine is not None:
                    engine.dispose()

        # Verify cleanup through a new physical connection. CONTROL prevents
        # restricted catalog visibility from producing a false empty result.
        if scoped:
            fresh = None
            try:
                fresh = open_connection("fresh")
                require(scalar(fresh, "fresh_db_name", "SELECT DB_NAME()") == adapter.DATABASE)
                require(scalar(fresh, "fresh_control", CONTROL_SQL) == 1)
                require(scalar(fresh, "fresh_catalog", COUNT_SQL) == 0)
                empty_verified = True
                completed.append("fresh_connection_catalog_empty")
            except Exception as exc:
                failures.append(safe_error(exc))
            finally:
                close(fresh, failures, "fresh_close")
        return {"status": "failed" if failures else "passed",
                "mode": "readonly_diagnostic", "completed_phases": completed,
                "failures": failures, "fresh_connection_catalog_empty_verified": empty_verified,
                "ddl_executed": False, "dml_executed": False, "harness_executed": False}
    finally:
        credential.close()


def interrupted(signum, frame):
    raise GuardFailed()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-readonly", action="store_true")
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    for value in (signal.SIGTERM, signal.SIGINT, signal.SIGALRM):
        signal.signal(value, interrupted)
    try:
        adapter = load_adapter()
        example = Exception("42000", "[42000] hidden (102) (SQLExecDirectW); hidden (8180)")
        result = safe_error(example)
        require(result["sqlstates"] == ["42000"] and result["native_numbers"] == [102, 8180])
        require("hidden" not in json.dumps(result))
        if not args.run_readonly:
            print(json.dumps({"mode": "plan", "connects": False, "authenticates": False,
                              "ddl_executed": False, "harness_executed": False}))
            return 0
        signal.alarm(180)
        result = run_readonly(adapter)
        signal.alarm(0)
        print(json.dumps(result))
        return int(result["status"] != "passed")
    except BaseException as exc:
        signal.alarm(0)
        print(json.dumps({"status": "failed", "mode": "readonly_diagnostic",
                          "failures": [safe_error(exc)],
                          "fresh_connection_catalog_empty_verified": False,
                          "ddl_executed": False, "harness_executed": False}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
