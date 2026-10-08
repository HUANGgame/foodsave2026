"""Validate a scoped nearby-query candidate inside the pinned rollback harness."""
from pathlib import Path
import argparse
import ast
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
OBSERVATION = {"harness_started": False, "fresh_catalog_empty_verified": False,
               "candidate_queries": 0}
CANDIDATE = "nearby_optional_predicates"
PRODUCTS_SHA = "f122efea22e42fc074945f0490d2700d8b4141b90c87fe4000d46c2d3a3da52a"
STORES_SHA = "745bf37f548395381992d64e1720363f5985037cbd5d30b197af8122393fd758"
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
    return (adapter.no_connect_tests(module) + 6 + candidate_no_connect_checks()
            + reconnect_no_connect_checks(adapter, module))



def fresh_token_listener(original_factory, module, credential):
    original_guard = original_factory(module, credential)

    def connect(dialect, connection_record, args, kwargs):
        # SQLAlchemy reuses its creator args/kwargs. Never place token bytes there.
        isolated_args = list(args)
        isolated_kwargs = dict(kwargs)
        original_guard(dialect, connection_record, isolated_args, isolated_kwargs)
        connection = dialect.connect(*isolated_args, **isolated_kwargs)
        require(connection is not None)
        return connection
    return connect


def reconnect_no_connect_checks(adapter, module):
    from types import SimpleNamespace
    import time

    class FakeCredential:
        calls = 0

        def get_token(self, scope):
            require(scope == adapter.SQL_SCOPE)
            self.calls += 1
            return SimpleNamespace(token="fake-token-" + str(self.calls),
                                   expires_on=time.time() + 600)

    class FakeDialect:
        name = "mssql"
        driver = "pyodbc"

        def connect(self, *args, **kwargs):
            require(args == (adapter.CONNECTION,))
            require(set(kwargs) == {"timeout", "attrs_before"} and kwargs["timeout"] == 15)
            require(set(kwargs["attrs_before"]) == {1256})
            return SimpleNamespace(token_bytes=kwargs["attrs_before"][1256])

    credential = FakeCredential()
    dialect = FakeDialect()
    callback = fresh_token_listener(adapter.token_listener, module, credential)
    args, kwargs = [adapter.CONNECTION], {"timeout": 15}
    first = callback(dialect, None, args, kwargs)
    second = callback(dialect, None, args, kwargs)
    require(credential.calls == 2 and first is not second
            and first.token_bytes != second.token_bytes)
    require(args == [adapter.CONNECTION] and kwargs == {"timeout": 15})
    for rejected in ({"timeout": 15, "attrs_before": {1256: b"unapproved"}},
                     {"timeout": 15, "unexpected": True}):
        before = credential.calls
        try:
            callback(dialect, None, args, rejected)
        except adapter.GuardFailed:
            require(credential.calls == before)
        else:
            raise GuardFailed()
    require(args == [adapter.CONNECTION] and kwargs == {"timeout": 15})
    return 4


def specialize_nearby(statement, parameters):
    source_hash = digest(statement)
    named_products = "947d1653ccf136985a102896e54b93abc338a46269c975d764517f2922237bde"
    named_stores = "cd5e860163224f3b706a676e98ea84892f494ca6b379d218478d289b9a93af86"
    if source_hash not in {named_products, named_stores}:
        return statement, parameters, None
    product = source_hash == named_products
    required = {"latitude", "longitude", "earth_radius", "radius", "fetch", "after"}
    if product:
        required.add("store_id")
    require(isinstance(parameters, dict) and set(parameters) == required)
    bound = dict(parameters)
    require(all(bound[key] is not None for key in required - {"after", "store_id"}))
    optional = [("after", " AND (:after IS NULL OR p.id>:after)" if product
                 else "WHERE (:after IS NULL OR s.id>:after)",
                 " AND p.id>:after" if product else "WHERE s.id>:after")]
    if product:
        optional.insert(0, ("store_id", " AND (:store_id IS NULL OR p.store_id=:store_id)",
                            " AND p.store_id=:store_id"))
    for key, original, replacement in optional:
        value = bound[key]
        require(value is None or (isinstance(value, str) and
                re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", value)))
        require(statement.count(original) == 1)
        statement = statement.replace(original, "" if value is None else replacement)
        if value is None:
            del bound[key]
    names = set(re.findall(r"(?<!:):([a-zA-Z_]\w*)", statement))
    require(names == set(bound) and all(value is not None for value in bound.values()))
    return statement, bound, PRODUCTS_SHA if product else STORES_SHA


def candidate_no_connect_checks():
    # Read literal templates without importing or running application code.
    tree = ast.parse((ROOT / "backend/foodsave/nearby.py").read_text())
    templates = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id not in {"NEARBY_CTE", "STORES_SQL", "PRODUCTS_SQL"}:
            continue
        value = node.value
        if target.id == "NEARBY_CTE":
            require(isinstance(value, ast.Constant) and isinstance(value.value, str))
            templates[target.id] = value.value
        else:
            require(isinstance(value, ast.BinOp) and isinstance(value.op, ast.Add)
                    and isinstance(value.left, ast.Name) and value.left.id == "NEARBY_CTE"
                    and isinstance(value.right, ast.Constant) and isinstance(value.right.value, str))
            templates[target.id] = templates["NEARBY_CTE"] + value.right.value
    require(set(templates) == {"NEARBY_CTE", "STORES_SQL", "PRODUCTS_SQL"})
    products, stores = templates["PRODUCTS_SQL"], templates["STORES_SQL"]
    require(digest(re.sub(r"(?<!:):[a-zA-Z_]\w*", "?", products)) == PRODUCTS_SHA)
    require(digest(re.sub(r"(?<!:):[a-zA-Z_]\w*", "?", stores)) == STORES_SHA)
    prefix = dict(latitude=25.0, longitude=121.0, earth_radius=6371008.8, radius=1000, fetch=101)
    boundaries = (None, "00000000-0000-0000-0000-000000000000",
                  "ffffffff-ffff-ffff-ffff-ffffffffffff")
    count = 0
    examples = []
    for store_id in boundaries:
        for after in boundaries:
            params = {**prefix, "store_id": store_id, "after": after}
            query, bound, original_hash = specialize_nearby(products, params)
            expected = {**prefix}
            if store_id is not None:
                expected["store_id"] = store_id
            if after is not None:
                expected["after"] = after
            require(original_hash == PRODUCTS_SHA and bound == expected)
            require(params == {**prefix, "store_id": store_id, "after": after})
            require((" AND p.store_id=:store_id" in query) == (store_id is not None))
            require((" AND p.id>:after" in query) == (after is not None))
            require(query.endswith("ORDER BY p.id\n"))
            examples.append((query, bound))
            count += 1
    for after in boundaries:
        params = {**prefix, "after": after}
        query, bound, original_hash = specialize_nearby(stores, params)
        expected = {**prefix}
        if after is not None:
            expected["after"] = after
        require(original_hash == STORES_SHA and bound == expected)
        require(("WHERE s.id>:after" in query) == (after is not None))
        require(query.endswith("ORDER BY s.id\n"))
        examples.append((query, bound))
        count += 1
    untouched = {"value": None}
    query, bound, original_hash = specialize_nearby("SELECT :value", untouched)
    require(query == "SELECT :value" and bound is untouched and original_hash is None)
    for params in (prefix, {**prefix, "store_id": None, "after": None, "extra": 1},
                   {**prefix, "store_id": "invalid", "after": None}):
        try:
            specialize_nearby(products, params)
        except GuardFailed:
            count += 1
        else:
            raise GuardFailed()
    if importlib.util.find_spec("sqlalchemy") is not None:
        from sqlalchemy import text
        from sqlalchemy.dialects.mssql.pyodbc import MSDialect_pyodbc
        dialect = MSDialect_pyodbc(paramstyle="qmark")
        for query, bound in examples:
            compiled = text(query).bindparams(**bound).compile(dialect=dialect)
            require(str(compiled) == re.sub(r"(?<!:):[a-zA-Z_]\w*", "?", query))
            require(all(compiled.params[key] is not None for key in compiled.positiontup))
            require(len(compiled.positiontup) == str(compiled).count("?"))
            count += 1
    return count + 1


def presence_snapshot(connection, label, ordinal):
    cursor = None
    try:
        cursor = connection.connection.driver_connection.cursor()
        row = cursor.execute(
            "SELECT @@TRANCOUNT, XACT_STATE(), "
            "CASE WHEN OBJECT_ID(N'dbo.stores') IS NULL THEN 0 ELSE 1 END, "
            "CASE WHEN DB_NAME()=N'foodsave-validation-20261006' THEN 1 ELSE 0 END"
        ).fetchone()
        require(row is not None)
        emit({"event": "candidate_presence", "phase": label,
              "connection_ordinal": ordinal, "transaction_count": int(row[0]),
              "transaction_state": int(row[1]), "stores_present": row[2] == 1,
              "database_matches": row[3] == 1})
        return row[0] > 0 and row[1] == 1 and row[2] == 1 and row[3] == 1
    except BaseException as exc:
        record_error(exc, label)
        return False
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except BaseException as exc:
                record_error(exc, label + "_close")


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
    from sqlalchemy import event, text
    from sqlalchemy.engine import Engine
    from sqlalchemy.sql.elements import TextClause

    migration_labels = {digest(sql): name for name, sql in batches}
    original_run = module.run
    original_preflight = adapter.metadata_preflight
    original_token_listener = adapter.token_listener
    sequence = 0
    connection_ordinals = {}
    candidate_digests = {}

    def per_connect_factory(module, credential):
        return fresh_token_listener(original_token_listener, module, credential)

    def before_execute(conn, clause, multiparams, params, execution_options):
        if not isinstance(clause, TextClause):
            return clause, multiparams, params
        query, bound, original_hash = specialize_nearby(clause.text, params)
        if original_hash is None:
            return clause, multiparams, params
        require(not multiparams)
        compiled_shape = re.sub(r"(?<!:):[a-zA-Z_]\w*", "?", query)
        candidate_digests[digest(compiled_shape)] = original_hash
        replacement = text(query).execution_options(**dict(clause.get_execution_options()))
        return replacement, multiparams, bound

    def before(conn, cursor, statement, parameters, context, executemany):
        nonlocal sequence
        sequence += 1
        fingerprint = digest(statement)
        label = migration_labels.get(fingerprint)
        phase = "migration_batch" if label else PHASE
        metadata = {"sequence": sequence, "phase": phase, "statement_sha256": fingerprint}
        if label is not None:
            metadata["migration"] = label
        raw_id = id(conn.connection.driver_connection)
        ordinal = connection_ordinals.setdefault(raw_id, len(connection_ordinals) + 1)
        metadata["connection_ordinal"] = ordinal
        context._foodsave_observation = metadata
        if fingerprint in candidate_digests:
            require(not executemany and all(value is not None for value in parameters))
            require(presence_snapshot(conn, "before_candidate", ordinal))
            OBSERVATION["candidate_queries"] += 1
            metadata["candidate"] = CANDIDATE
            metadata["statement_sha256"] = candidate_digests[fingerprint]
            metadata["effective_statement_sha256"] = fingerprint
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
        if metadata.get("candidate") == CANDIDATE and context.connection is not None:
            presence_snapshot(context.connection, "candidate_error",
                              metadata["connection_ordinal"])
        # No exception replacement, retry, commit, or rollback.

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

    listeners = [("before_execute", before_execute), ("before_cursor_execute", before), ("after_cursor_execute", after),
                 ("handle_error", on_error)]
    registered = []
    try:
        for name, callback in listeners:
            event.listen(Engine, name, callback, retval=(name == "before_execute"))
            registered.append((name, callback))
        module.run = observed_run
        adapter.metadata_preflight = preflight
        adapter.token_listener = per_connect_factory
        mark("adapter_identity")
        result = adapter.run(module, batches)
        require(OBSERVATION["candidate_queries"] >= 6)
        return result
    finally:
        module.run = original_run
        adapter.metadata_preflight = original_preflight
        adapter.token_listener = original_token_listener
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
                  "migration_count": len(batches), "sql_behavior_changed": True, "candidate": CANDIDATE,
                  "connection_adapter_candidate": "per_connect_parameter_copy"})
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
          "harness_result": result, "sql_behavior_changed": True, "candidate": CANDIDATE,
                  "connection_adapter_candidate": "per_connect_parameter_copy"})
    return int(status != "passed")


if __name__ == "__main__":
    sys.exit(main())
