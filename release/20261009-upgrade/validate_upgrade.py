"""Offline by default. Prepared synthetic populated upgrade; SQL execution is locked."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
SOURCE = "f5ea46c7f9ddd8d5277783488188f90d6c4fa5f9"
DATABASE = "foodsave-validation-20261006"
OBSERVER_BLOB = "75931e04fe985d0ed1880d076be3ddda00f128a5"
# No pipeline is approved to execute this new SQL rehearsal yet.
APPROVED_SQL_PIPELINE_ID = None
TABLES = {"users": "id", "sessions": "token_hash", "stores": "id",
          "products": "id", "reservations": "id",
          "request_results": "user_id,operation,request_key",
          "deletion_requests": "id", "notifications": "id",
          "reservation_terminals": "reservation_id"}
OLD_STORE_COLUMNS = "id,owner_id,name,latitude,longitude,service_mode"
PROCEDURES = ("close_vendor_business", "report_stock_loss")
SCENARIOS = ("rollback_after_013", "rollback_after_014", "populated_success", "sql_throw_full_rollback")
SETTINGS = ("SET XACT_ABORT ON; SET ANSI_NULLS ON; SET QUOTED_IDENTIFIER ON; "
            "SET ANSI_PADDING ON; SET ANSI_WARNINGS ON; SET CONCAT_NULL_YIELDS_NULL ON; "
            "SET ARITHABORT ON; SET NUMERIC_ROUNDABORT OFF; SET LOCK_TIMEOUT 10000; "
            "IF @@TRANCOUNT=0 BEGIN TRANSACTION;")


class GuardFailed(Exception):
    pass


class InjectedFailure(Exception):
    pass


def require(ok, label):
    if not ok:
        raise GuardFailed(label)


def identity(n):
    return str(UUID(int=n))


def sql_gate():
    require(APPROVED_SQL_PIPELINE_ID is not None, "sql_execution_not_authorized")
    require(os.environ.get("SYSTEM_DEFINITIONID") == str(APPROVED_SQL_PIPELINE_ID),
            "specific_pipeline_required")


def load_pins():
    path = ROOT / "release/20261009-nearby/validate_sql_wif_observed.py"
    raw = path.read_bytes()
    require(hashlib.sha1(f"blob {len(raw)}\0".encode("ascii") + raw).hexdigest()
            == OBSERVER_BLOB, "observer_pin")
    spec = importlib.util.spec_from_file_location("upgrade_pinned_observer", path)
    observer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(observer)
    adapter, harness, batches = observer.load_adapter()
    require(adapter.DATABASE == DATABASE and harness.SOURCE == SOURCE, "source_and_database_pin")
    require([name[:3] for name, _ in batches] == [f"{i:03}" for i in range(1, 15)], "migration_set")
    return observer, adapter, harness, batches


def query(c, statement, **params):
    from sqlalchemy import text
    return c.execute(text(statement), params)


def data_snapshot(c):
    result = {}
    for table, order in TABLES.items():
        columns = OLD_STORE_COLUMNS if table == "stores" else "*"
        result[table] = [tuple(row) for row in c.exec_driver_sql(
            f"SELECT {columns} FROM dbo.{table} ORDER BY {order}").fetchall()]
    return result


def metadata_snapshot(c):
    return {
        "ledger": [tuple(r) for r in c.exec_driver_sql(
            "SELECT version,applied_at FROM dbo.schema_migrations ORDER BY version").fetchall()],
        "columns": [tuple(r) for r in c.exec_driver_sql(
            "SELECT name,column_id,user_type_id,is_nullable FROM sys.columns "
            "WHERE object_id=OBJECT_ID('dbo.stores') ORDER BY column_id").fetchall()],
        "indexes": [tuple(r) for r in c.exec_driver_sql(
            "SELECT name,is_unique,is_disabled,is_hypothetical,type,filter_definition "
            "FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.stores') ORDER BY index_id").fetchall()],
        "index_columns": [tuple(r) for r in c.exec_driver_sql(
            "SELECT index_id,column_id,key_ordinal,is_included_column FROM sys.index_columns "
            "WHERE object_id=OBJECT_ID('dbo.stores') ORDER BY index_id,index_column_id").fetchall()],
        "defaults": [tuple(r) for r in c.exec_driver_sql(
            "SELECT name,definition,parent_column_id FROM sys.default_constraints "
            "WHERE parent_object_id=OBJECT_ID('dbo.stores') ORDER BY name").fetchall()],
        "checks": [tuple(r) for r in c.exec_driver_sql(
            "SELECT name,definition,is_disabled FROM sys.check_constraints "
            "WHERE parent_object_id=OBJECT_ID('dbo.stores') ORDER BY name").fetchall()],
        "procedures": [tuple(r) for r in c.exec_driver_sql(
            "SELECT OBJECT_NAME(object_id),definition,uses_ansi_nulls,uses_quoted_identifier,"
            "is_recompiled,execute_as_principal_id FROM sys.sql_modules "
            "WHERE object_id IN(OBJECT_ID('dbo.close_vendor_business'),"
            "OBJECT_ID('dbo.report_stock_loss')) ORDER BY OBJECT_NAME(object_id)").fetchall()],
        "permissions": [tuple(r) for r in c.exec_driver_sql(
            "SELECT class,major_id,minor_id,grantee_principal_id,grantor_principal_id,"
            "type,state FROM sys.database_permissions ORDER BY class,major_id,minor_id,"
            "grantee_principal_id,grantor_principal_id,type,state").fetchall()],
    }


def apply(c, batches):
    applied = 0
    for name, statement in batches:
        if query(c, "SELECT version FROM dbo.schema_migrations WHERE version=:v", v=name).first():
            continue
        c.exec_driver_sql(statement)
        query(c, "INSERT dbo.schema_migrations(version) VALUES(:v)", v=name)
        applied += 1
    return applied


def seed(c):
    for n, role in ((1, "vendor"), (2, "consumer"), (3, "consumer"), (4, "admin")):
        query(c, "INSERT dbo.users(id,email,password_hash,role) VALUES(:id,:email,:password,:role)",
              id=identity(n), email=f"upgrade-{n}@example.invalid",
              password="synthetic-upgrade-not-a-login-hash", role=role)
        query(c, "INSERT dbo.sessions(token_hash,user_id,expires_at) "
              "VALUES(:token,:id,DATEADD(hour,1,SYSUTCDATETIME()))",
              token=f"{n:064x}", id=identity(n))
    for n, mode, lat, lon in ((1, "information", "25.123456", "121.654321"),
                               (2, "reservation", "-12.345678", "45.678901")):
        query(c, "INSERT dbo.stores(id,owner_id,name,latitude,longitude,service_mode) "
              "VALUES(:id,:owner,:name,:lat,:lon,:mode)", id=identity(10+n),
              owner=identity(n), name=f"synthetic store {n}", lat=lat, lon=lon, mode=mode)
        query(c, "INSERT dbo.products(id,store_id,name,photo_url,original_price_minor,"
              "sale_price_minor,available_quantity,pickup_deadline) "
              "VALUES(:id,:store,'synthetic item','https://example.invalid/item',100,50,2,"
              "DATEADD(hour,1,SYSUTCDATETIME()))", id=identity(20+n), store=identity(10+n))
        state = "completed" if n == 1 else "waiting"
        snapshot = json.dumps({"name": f"synthetic item {n}", "latitude": lat, "longitude": lon})
        query(c, "INSERT dbo.reservations(id,user_id,product_id,state,quantity,snapshot,"
              "pickup_code_hash,expires_at) VALUES(:id,:user,:product,:state,1,:snapshot,"
              ":code,DATEADD(minute,10,SYSUTCDATETIME()))", id=identity(30+n),
              user=identity(3), product=identity(20+n), state=state,
              snapshot=snapshot, code=f"{100+n:064x}")
        query(c, "INSERT dbo.request_results(user_id,operation,request_key,fingerprint,response) "
              "VALUES(:user,'reserve',:key,:fingerprint,:response)", user=identity(3),
              key=identity(40+n), fingerprint=f"{200+n:064x}",
              response=json.dumps({"id": identity(30+n), "state": state}))


def restored(c, baseline, metadata):
    require(data_snapshot(c) == baseline, "existing_rows_preserved")
    require(metadata_snapshot(c) == metadata, "schema_procedure_ledger_restored")


def rollback_savepoint(c, point):
    require(c.exec_driver_sql("SELECT XACT_STATE()").scalar_one() == 1,
            "savepoint_requires_committable_transaction")
    point.rollback()


def procedure_checks(c, baseline):
    for owner, pending in ((2, 1), (1, 0)):
        point = c.begin_nested()
        try:
            result = query(c, "EXEC dbo.report_stock_loss @vendor_id=:owner,@product_id=:product,"
                           "@expected_revision=1,@expected_pending=:pending,@actual_available=0",
                           owner=identity(owner), product=identity(20+owner),
                           pending=pending).mappings().one()
            require(result["outcome"] == "applied" and result["cancelled_count"] == pending,
                    "consumer_and_vendor_stock_loss")
            product = query(c, "SELECT available_quantity,revision FROM dbo.products WHERE id=:id",
                            id=identity(20+owner)).one()
            require(tuple(product) == (0, 2), "stock_loss_inventory_revision")
            require(query(c, "SELECT COUNT(*) FROM dbo.notifications WHERE kind='vendor_out_of_stock'").scalar_one()
                    == pending, "stock_loss_notifications")
            require(query(c, "SELECT COUNT(*) FROM dbo.reservation_terminals "
                            "WHERE reason='vendor_out_of_stock' AND released_quantity=0").scalar_one()
                    == pending, "stock_loss_terminal")
            if pending:
                require(query(c, "SELECT COUNT(*) FROM dbo.reservations WHERE id=:id",
                              id=identity(32)).scalar_one() == 0, "stock_loss_order_removed")
                response = query(c, "SELECT response FROM dbo.request_results WHERE request_key=:key",
                                 key=identity(42)).scalar_one()
                require(json.loads(response)["terminal_reason"] == "vendor_out_of_stock",
                        "stock_loss_retry_cache")
        finally:
            rollback_savepoint(c, point)
        require(data_snapshot(c) == baseline, "stock_loss_fixture_restored")
    point = c.begin_nested()
    try:
        result = query(c, "EXEC dbo.report_stock_loss @vendor_id=:owner,@product_id=:product,"
                       "@expected_revision=1,@expected_pending=1,@actual_available=0",
                       owner=identity(1), product=identity(22)).mappings().one()
        require(result["outcome"] == "not_found", "cross_store_denied")
        query(c, "UPDATE dbo.users SET active=0 WHERE id=:id", id=identity(2))
        query(c, "INSERT dbo.deletion_requests(id,user_id) VALUES(:id,:user)",
              id=identity(50), user=identity(2))
        result = query(c, "EXEC dbo.close_vendor_business @vendor_id=:owner",
                       owner=identity(2)).mappings().one()
        require(result["outcome"] == "closed" and result["removed_orders"] == 1, "consumer_close_success")
        for table, key in (("stores", 12), ("products", 22), ("reservations", 32)):
            require(query(c, f"SELECT COUNT(*) FROM dbo.{table} WHERE id=:id",
                          id=identity(key)).scalar_one() == 0, "close_related_row_removed")
        require(query(c, "SELECT COUNT(*) FROM dbo.notifications WHERE kind='vendor_closed'").scalar_one()
                == 1, "close_notification")
        require(query(c, "SELECT COUNT(*) FROM dbo.reservation_terminals WHERE reason='vendor_closed'").scalar_one()
                == 1, "close_terminal")
    finally:
        rollback_savepoint(c, point)
    require(data_snapshot(c) == baseline, "close_fixture_restored")


def success_checks(c, batches, baseline, metadata):
    require(apply(c, batches[12:]) == 2 and apply(c, batches) == 0, "upgrade_two_then_zero")
    require(data_snapshot(c) == baseline, "all_old_columns_preserved")
    old = c.exec_driver_sql("SELECT location_revision,location_confirmed FROM dbo.stores ORDER BY id").fetchall()
    require([tuple(r) for r in old] == [(1, True), (1, True)], "old_store_values")
    columns = c.exec_driver_sql("SELECT name,is_nullable FROM sys.columns WHERE "
        "object_id=OBJECT_ID('dbo.stores') AND name IN('location_revision','location_confirmed')").fetchall()
    require(len(columns) == 2 and all(not row[1] for row in columns), "new_columns_not_null")
    defaults = dict(c.exec_driver_sql("SELECT name,definition FROM sys.default_constraints "
        "WHERE parent_object_id=OBJECT_ID('dbo.stores')").fetchall())
    normalize = lambda value: re.sub(r"[()\s]", "", value)
    require(normalize(defaults.get("df_stores_location_revision", "")) == "1"
            and normalize(defaults.get("df_stores_location_confirmed", "")) == "0"
            and "df_stores_location_confirmed_existing" not in defaults, "final_defaults")
    current = metadata_snapshot(c)
    require(any(row[0] == "ck_stores_location_revision" and not row[2]
                and re.sub(r"[()\s\[\]]", "", row[1]).lower() == "location_revision>=1"
                for row in current["checks"]), "revision_check")
    require(current["permissions"] == metadata["permissions"], "permissions_unchanged")
    require(len(current["ledger"]) == 14, "exact_ledger_count")
    require(len(metadata["procedures"]) == len(current["procedures"]) == 2, "both_procedures")
    require(current["indexes"] == metadata["indexes"]
            and current["index_columns"] == metadata["index_columns"], "indexes_unchanged")
    for before, after in zip(metadata["procedures"], current["procedures"]):
        expected = before[1].replace("CREATE PROCEDURE", "ALTER PROCEDURE", 1).replace(
            "u.role='vendor'", "u.role IN ('consumer','vendor')")
        require(before[0] == after[0] and expected.strip() == after[1].strip()
                and before[2:] == after[2:], "exact_procedure_change_and_options")
    procedure_checks(c, baseline)
    point = c.begin_nested()
    try:
        query(c, "INSERT dbo.stores(id,owner_id,name,latitude,longitude) "
              "VALUES(:id,:owner,'new synthetic store',0,0)", id=identity(13), owner=identity(3))
        row = query(c, "SELECT location_revision,location_confirmed,service_mode FROM dbo.stores "
                       "WHERE id=:id", id=identity(13)).one()
        require(tuple(row) == (1, False, "information"), "new_store_defaults")
    finally:
        rollback_savepoint(c, point)


def check_context(c, adapter, empty=False):
    require(c.exec_driver_sql("SELECT DB_NAME()").scalar_one() == DATABASE, "test_database_only")
    require(c.exec_driver_sql("SELECT HAS_PERMS_BY_NAME(DB_NAME(),'DATABASE','CONTROL')").scalar_one()
            == 1, "existing_control_only")
    sid = c.exec_driver_sql("SELECT CONVERT(varchar(36),CONVERT(uniqueidentifier,sid)) "
                           "FROM sys.database_principals WHERE principal_id=USER_ID()").scalar_one()
    require(str(sid).lower() == adapter.EXPECTED_CLIENT_ID, "test_identity")
    if empty:
        require(c.exec_driver_sql("SELECT COUNT(*) FROM sys.objects WHERE is_ms_shipped=0").scalar_one()
                == 0, "empty_user_catalog")


def run_upgrade(batches, adapter):
    sql_gate()  # Fails before imports/engine creation in this preparation release.
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
            check_context(c, adapter, empty=True)
            schemas = [tuple(r) for r in c.exec_driver_sql("SELECT name,principal_id FROM sys.schemas ORDER BY name").fetchall()]
            c.rollback()
            outer = c.begin()
            try:
                c.exec_driver_sql(SETTINGS)
                c.exec_driver_sql("DECLARE @r int; EXEC @r=sp_getapplock "
                    "@Resource='foodsave:validation-migrate',@LockMode='Exclusive',"
                    "@LockOwner='Transaction',@LockTimeout=10000; "
                    "IF @r<0 THROW 51000,'Migration lock unavailable',1;")
                c.exec_driver_sql("CREATE TABLE dbo.schema_migrations(version varchar(80) PRIMARY KEY,"
                                 "applied_at datetime2 NOT NULL DEFAULT SYSUTCDATETIME())")
                require(apply(c, batches[:12]) == 12, "baseline_012")
                seed(c)
                baseline, metadata = data_snapshot(c), metadata_snapshot(c)
                require(all(len(baseline[t]) == n for t, n in {"users": 4, "sessions": 4,
                        "stores": 2, "products": 2, "reservations": 2, "request_results": 2}.items()),
                        "minimal_synthetic_fixture_counts")
                old = query(c, "EXEC dbo.report_stock_loss @vendor_id=:owner,@product_id=:product,"
                            "@expected_revision=1,@expected_pending=1,@actual_available=0",
                            owner=identity(2), product=identity(22)).mappings().one()
                require(old["outcome"] == "not_found", "old_consumer_not_supported")
                restored(c, baseline, metadata)
                for count in (1, 2):
                    point = c.begin_nested()
                    try:
                        require(apply(c, batches[12:12+count]) == count, "injection_stage")
                        raise InjectedFailure()
                    except InjectedFailure:
                        rollback_savepoint(c, point)
                    restored(c, baseline, metadata)
                    checks.append(SCENARIOS[count-1])
                point = c.begin_nested()
                try:
                    success_checks(c, batches, baseline, metadata)
                finally:
                    rollback_savepoint(c, point)
                restored(c, baseline, metadata)
                checks.append("populated_success")
                require(apply(c, batches[12:]) == 2, "before_sql_failure")
                try:
                    c.exec_driver_sql("THROW 51099,'Synthetic upgrade rollback injection',1;")
                except DBAPIError as exc:
                    require(any("(51099)" in str(value) for value in getattr(exc.orig, "args", ())),
                            "expected_injection_number")
                    require(c.exec_driver_sql("SELECT XACT_STATE()").scalar_one() in (-1, 0, 1),
                            "known_transaction_state")
                    checks.append("sql_throw_full_rollback")
                else:
                    raise GuardFailed("injected_sql_error_required")
            finally:
                outer.rollback()
    except BaseException as exc:
        primary = exc
    finally:
        try:
            with engine.connect() as fresh:
                fresh.connection.driver_connection.timeout = 20
                check_context(fresh, adapter, empty=True)
                now = [tuple(r) for r in fresh.exec_driver_sql(
                    "SELECT name,principal_id FROM sys.schemas ORDER BY name").fetchall()]
                require(schemas is not None and now == schemas, "fresh_schema_namespace_unchanged")
                cleanup_ok = True
        finally:
            engine.dispose()
    if primary is not None:
        raise primary
    require(cleanup_ok and tuple(checks) == SCENARIOS, "complete_upgrade_rehearsal")
    return {"status": "passed", "checks": checks, "rollback_verified": True,
            "fresh_catalog_empty_verified": True, "commit_tested": False,
            "runtime_permissions_tested": False, "concurrency_tested": False}


def run_authorized_sql():
    sql_gate()
    observer, adapter, harness, batches = load_pins()
    original = harness.run
    try:
        harness.run = lambda files: run_upgrade(files, adapter)
        return adapter.run(harness, batches)
    finally:
        harness.run = original


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-rollback", action="store_true")
    args = parser.parse_args()
    try:
        if args.run_rollback:
            sql_gate()
            raise GuardFailed("sql_mode_not_exposed_in_offline_workflow")
        observer, adapter, harness, batches = load_pins()
        checks = observer.no_connect_checks(adapter, harness)
        print(json.dumps({"mode": "offline_plan", "status": "prepared_not_sql_tested",
              "source_commit": SOURCE, "database": DATABASE, "connects": False,
              "authenticates": False, "sql_execution_enabled": False,
              "no_connect_checks": checks, "migration_count": len(batches),
              "scenarios": SCENARIOS, "commit_tested": False,
              "runtime_permissions_tested": False, "concurrency_tested": False}))
        return 0
    except BaseException:
        print(json.dumps({"status": "failed", "connects": False,
                          "sql_execution_enabled": False, "error": "offline_guard_failed"}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
