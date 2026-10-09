"""Azure-hosted WIF adapter for the unchanged, pinned rollback harness.

Default mode does not authenticate or connect. No deployment, grants, commits,
resource creation, mail, or production database access is performed.
"""
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import UUID
import argparse
import hashlib
import importlib.util
import json
import logging
import os
import re
import signal
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
PREPARATION_COMMIT = "ba0150005e29a7c91f026fd6e8161a8978c4780c"
APPLICATION_COMMIT = "f5ea46c7f9ddd8d5277783488188f90d6c4fa5f9"
SERVER = "karea-indoor-nav-sql-ea.database.windows.net"
DATABASE = "foodsave-validation-20261006"
SQL_SCOPE = "https://database.windows.net/.default"
EXPECTED_TENANT_ID = "399232fb-17d1-45ca-bda6-5b540441bd62"
EXPECTED_CLIENT_ID = "1424737d-18e2-4e47-acea-9c2d7aa123e7"
# Verified Azure DevOps connection; authorization is restricted to this pipeline.
EXPECTED_SERVICE_CONNECTION_ID = "bed364c8-145a-423d-81e4-5af179a9a9f8"
CONNECTION = (
    "Driver={ODBC Driver 18 for SQL Server};"
    f"Server=tcp:{SERVER},1433;Database={DATABASE};"
    "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=15;"
)
REVIEWED_BLOBS = {
    "release/20261009-nearby/validate_sql.py": "0409b807de6d8121f956aab8956713da4c75603c",
    "release/20261009-nearby/source-hashes.json": "26c89c577794eca1904f6de451fc5c37b3bc64a1",
    "backend/requirements.txt": "f4c4b06fd6bcb3017c4f87c1711f7df2dc11fe81",
}


class GuardFailed(Exception):
    pass


def require(ok, label):
    if not ok:
        raise GuardFailed(label)


def read_harness():
    for relative, expected in REVIEWED_BLOBS.items():
        data = (ROOT / relative).read_bytes()
        header = f"blob {len(data)}\0".encode("ascii")
        require(hashlib.sha1(header + data).hexdigest() == expected, "reviewed_blob_mismatch")
    path = ROOT / "release/20261009-nearby/validate_sql.py"
    spec = importlib.util.spec_from_file_location("foodsave_pinned_sql_validation", path)
    require(spec is not None and spec.loader is not None, "harness_import_spec")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    require(module.SOURCE == APPLICATION_COMMIT, "application_pin")
    require(module.DATABASE == DATABASE, "database_pin")
    batches = module.sql_files()
    module.validate_connection(CONNECTION)
    return module, batches


def token_bytes(credential):
    token = credential.get_token(SQL_SCOPE)
    require(token.expires_on > time.time() + 60, "token_lifetime")
    raw = token.token.encode("utf-16-le")
    return struct.pack("<I", len(raw)) + raw


def token_listener(module, credential):
    def provide_token(dialect, connection_record, args, kwargs):
        require(dialect.name == "mssql" and dialect.driver == "pyodbc", "driver_pin")
        require(len(args) == 1 and args[0] == CONNECTION, "exact_connection_pin")
        module.validate_connection(args[0])
        require(set(kwargs) <= {"timeout"} and kwargs.get("timeout") == 15, "connect_options_pin")
        # SQLAlchemy reuses creator kwargs. Keep token bytes in a per-connect copy.
        isolated_kwargs = dict(kwargs)
        isolated_kwargs["attrs_before"] = {1256: token_bytes(credential)}
        return dialect.connect(*list(args), **isolated_kwargs)
    return provide_token


def guid_environment(name):
    value = os.environ.get(name, "")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError):
        raise GuardFailed("identity_guid_required") from None
    require(parsed.int != 0 and str(parsed) == value.lower(), "identity_guid_required")
    return str(parsed)


def check_agent_environment():
    require(os.environ.get("TF_BUILD", "").lower() == "true", "azure_pipeline_required")
    require(os.environ.get("BUILD_REASON") == "Manual", "manual_run_required")
    require(os.environ.get("BUILD_SOURCEBRANCH") == "refs/heads/foodsave-azure-checks-20261008",
            "validation_branch_required")
    require(os.environ.get("AGENT_OS") == "Linux", "linux_agent_required")
    oidc = urlsplit(os.environ.get("SYSTEM_OIDCREQUESTURI", ""))
    collection = urlsplit(os.environ.get("SYSTEM_TEAMFOUNDATIONCOLLECTIONURI", ""))
    host = collection.hostname or ""
    require(host == "dev.azure.com" or host.endswith(".visualstudio.com"), "azure_devops_host")
    require(collection.scheme == "https" and not collection.username and not collection.password
            and collection.port in (None, 443) and not collection.query and not collection.fragment,
            "azure_devops_collection")
    project_id = guid_environment("SYSTEM_TEAMPROJECTID")
    plan_id = guid_environment("SYSTEM_PLANID")
    job_id = guid_environment("SYSTEM_JOBID")
    require(os.environ.get("SYSTEM_HOSTTYPE") == "build", "build_job_required")
    suffix = (f"/{project_id}/_apis/distributedtask/hubs/build/plans/"
              f"{plan_id}/jobs/{job_id}/oidctoken")
    require(oidc.scheme == "https" and oidc.hostname == host and not oidc.username
            and not oidc.password and oidc.port in (None, 443)
            and not oidc.query and not oidc.fragment
            and oidc.path.rstrip("/").lower() == collection.path.rstrip("/").lower() + suffix,
            "azure_oidc_endpoint")


def metadata_preflight(credential, client_id):
    import pyodbc
    pyodbc.pooling = False
    require("ODBC Driver 18 for SQL Server" in pyodbc.drivers(), "odbc18_required")
    # Only a known Azure SQL availability error may retry this read-only phase.
    for attempt in range(4):
        connection = None
        try:
            connection = pyodbc.connect(
                CONNECTION, attrs_before={1256: token_bytes(credential)}, timeout=15,
                autocommit=False,
            )
            connection.timeout = 30
            cursor = connection.cursor()
            try:
                row = cursor.execute(
                    "SELECT DB_NAME(), HAS_PERMS_BY_NAME(DB_NAME(),'DATABASE','CONTROL'), "
                    "(SELECT COUNT(*) FROM sys.objects WHERE is_ms_shipped=0), "
                    "(SELECT CONVERT(varchar(36),CONVERT(uniqueidentifier,sid)) "
                    "FROM sys.database_principals WHERE principal_id=USER_ID())"
                ).fetchone()
                require(row is not None and row[0] == DATABASE, "preflight_database")
                require(row[1] == 1, "preflight_control")
                require(row[2] == 0, "preflight_empty")
                require(str(row[3]).lower() == client_id, "preflight_identity_sid")
            finally:
                cursor.close()
            return
        except pyodbc.Error as exc:
            retryable = bool(re.search(r"\((40613|40197|40501|49918|49919|49920)\)", str(exc)))
            if not retryable or attempt == 3:
                raise
        finally:
            if connection is not None:
                try:
                    connection.rollback()
                finally:
                    connection.close()
        time.sleep(5)


def no_connect_tests(module):
    class FakeCredential:
        def __init__(self):
            self.calls = 0

        def get_token(self, scope):
            require(scope == SQL_SCOPE, "test_scope")
            self.calls += 1
            return SimpleNamespace(token="fake-token", expires_on=time.time() + 600)

    class FakeDialect:
        name = "mssql"
        driver = "pyodbc"

        def connect(self, *args, **kwargs):
            require(args == (CONNECTION,), "test_connected_target")
            require(set(kwargs) == {"timeout", "attrs_before"} and kwargs["timeout"] == 15,
                    "test_connected_options")
            require(set(kwargs["attrs_before"]) == {1256}, "test_connected_attributes")
            return SimpleNamespace(attrs=kwargs["attrs_before"])

    fake = FakeCredential()
    dialect = FakeDialect()
    callback = token_listener(module, fake)
    args, kwargs = [CONNECTION], {"timeout": 15}
    first = callback(dialect, None, args, kwargs)
    second = callback(dialect, None, args, kwargs)
    raw = "fake-token".encode("utf-16-le")
    require(first.attrs[1256] == struct.pack("<I", len(raw)) + raw, "test_token_structure")
    require(first is not second and fake.calls == 2, "test_two_physical_connections")
    require(args == [CONNECTION] and kwargs == {"timeout": 15}, "test_creator_parameters_unchanged")
    checks = 2
    bad_strings = [
        CONNECTION.replace(DATABASE, "foodsave"),
        CONNECTION.replace(SERVER, "other.database.windows.net"),
        CONNECTION.replace("Encrypt=yes", "Encrypt=no"),
        CONNECTION.replace("TrustServerCertificate=no", "TrustServerCertificate=yes"),
        CONNECTION + "UID=someone;",
        CONNECTION + "PWD=not-a-secret;",
        CONNECTION + "Authentication=ActiveDirectoryMsi;",
        CONNECTION + "Trusted_Connection=Yes;",
        CONNECTION + f"Database={DATABASE};",
    ]
    for value in bad_strings:
        before = fake.calls
        try:
            callback(dialect, None, [value], {"timeout": 15})
        except GuardFailed:
            pass
        else:
            raise GuardFailed("test_connection_rejection")
        require(fake.calls == before, "test_no_token_for_rejected_target")
        checks += 1
    for value in ({"timeout": 15, "attrs_before": {1256: b"unapproved"}},
                  {"timeout": 15, "unexpected": True}):
        before = fake.calls
        try:
            callback(dialect, None, [CONNECTION], value)
        except GuardFailed:
            pass
        else:
            raise GuardFailed("test_existing_options_rejected")
        require(fake.calls == before, "test_no_token_for_rejected_options")
        checks += 1
    if (importlib.util.find_spec("sqlalchemy") is not None
            and importlib.util.find_spec("pyodbc") is not None):
        from sqlalchemy import create_engine, event
        from sqlalchemy.engine import Engine, URL
        from sqlalchemy.pool import NullPool
        engine = None
        event.listen(Engine, "do_connect", callback)
        try:
            engine = create_engine(
                URL.create("mssql+pyodbc", query={"odbc_connect": CONNECTION}),
                poolclass=NullPool, hide_parameters=True, connect_args={"timeout": 15},
            )
            cargs, cparams = engine.dialect.create_connect_args(engine.url)
            cparams["timeout"] = 15
            results = [handler(dialect, None, cargs, cparams)
                       for handler in engine.dialect.dispatch.do_connect]
            require(any(result is not None and 1256 in result.attrs for result in results),
                    "test_registered_token_hook")
            require(cparams == {"timeout": 15}, "test_registered_creator_parameters_unchanged")
        finally:
            if engine is not None:
                engine.dispose()
            event.remove(Engine, "do_connect", callback)
        checks += 1
    return checks


def interrupted(signum, frame):
    raise GuardFailed("validation_interrupted")


def run(module, batches):
    from azure.identity import AzurePipelinesCredential
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    check_agent_environment()
    tenant_id = guid_environment("FOODSAVE_WIF_TENANT_ID")
    client_id = guid_environment("FOODSAVE_WIF_CLIENT_ID")
    connection_id = guid_environment("FOODSAVE_WIF_SERVICE_CONNECTION_ID")
    require(tenant_id == EXPECTED_TENANT_ID and client_id == EXPECTED_CLIENT_ID
            and connection_id == EXPECTED_SERVICE_CONNECTION_ID, "approved_identity_pin")
    access_token = os.environ.pop("SYSTEM_ACCESSTOKEN", "")
    require(bool(access_token) and not access_token.startswith("$("), "pipeline_token_required")
    require(not os.environ.get("FOODSAVE_VALIDATION_ODBC_CONNECTION"), "external_connection_forbidden")
    # No DefaultAzureCredential fallback, client secret, or persistent token cache.
    credential = AzurePipelinesCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        service_connection_id=connection_id,
        system_access_token=access_token,
        logging_enable=False,
        retry_total=1,
        connection_timeout=10,
        read_timeout=20,
    )
    access_token = None
    callback = token_listener(module, credential)
    registered = False
    try:
        metadata_preflight(credential, client_id)
        sys.path.insert(0, str(ROOT / "backend"))
        os.environ["FOODSAVE_VALIDATION_ODBC_CONNECTION"] = CONNECTION
        event.listen(Engine, "do_connect", callback)
        registered = True
        result = module.run(batches)
        require(result.get("status") == "passed" and result.get("rollback_verified") is True,
                "rollback_result_required")
        return {**result, "adapter": "azure_pipelines_wif", "identity_sid_verified": True,
                "preparation_commit": PREPARATION_COMMIT, "application_commit": APPLICATION_COMMIT}
    finally:
        if registered:
            event.remove(Engine, "do_connect", callback)
        os.environ.pop("FOODSAVE_VALIDATION_ODBC_CONNECTION", None)
        credential.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-rollback", action="store_true")
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    signal.signal(signal.SIGALRM, interrupted)
    try:
        module, batches = read_harness()
        checks = no_connect_tests(module)
        if not args.run_rollback:
            print(json.dumps({
                "mode": "plan", "connects": False, "authenticates": False,
                "preparation_commit": PREPARATION_COMMIT, "application_commit": APPLICATION_COMMIT,
                "database": DATABASE, "adapter_checks": checks,
                "batches": [{"name": name, "adapted_sha256": hashlib.sha256(sql.encode()).hexdigest()}
                            for name, sql in batches],
                "not_covered": ["runtime principal permissions", "concurrency", "deployed HTTP", "Android"],
            }))
            return 0
        signal.alarm(420)
        result = run(module, batches)
        signal.alarm(0)
        print(json.dumps(result))
        return 0
    except BaseException as exc:
        signal.alarm(0)
        # Never emit exception text, SQL arguments, driver details, or credential values.
        print(json.dumps({
            "status": "failed", "error_type": type(exc).__name__,
            "check": str(exc) if isinstance(exc, GuardFailed) else None,
            "rollback_verified": False,
        }))
        return 1


if __name__ == "__main__":
    sys.exit(main())
