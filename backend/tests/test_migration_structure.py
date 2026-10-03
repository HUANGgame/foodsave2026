"""Static T-SQL shape regressions, not a SQL Server compile/integration test."""
from pathlib import Path
import re
import pytest

MIGRATIONS = Path(__file__).resolve().parents[1] / 'migrations'


def column_check_violations(sql):
    """Inspect this repository's one-column-per-line CREATE TABLE convention."""
    failures = []
    for name, body in re.findall(r'CREATE TABLE\s+([\w.]+)\s*\((.*?)\n\);', sql, re.I | re.S):
        definitions = {}
        for line in body.splitlines():
            match = re.match(r'\s*(\w+)\s+(?:int|bigint|bit|char|varchar|nvarchar|decimal|datetime2)\b', line, re.I)
            if match:
                definitions[match[1].lower()] = line
        for column, line in definitions.items():
            if re.search(r'\bCHECK\s*\(', line, re.I):
                condition = re.split(r'\bCHECK\s*\(', line, maxsplit=1, flags=re.I)[1]
                condition = re.sub(r"'(?:''|[^'])*'", '', condition)
                refs = set(re.findall(r'\b\w+\b', condition.lower())) & definitions.keys()
                if refs - {column}:
                    failures.append((name, column, sorted(refs - {column})))
    return failures


@pytest.mark.parametrize('path', sorted(MIGRATIONS.glob('*.sql')), ids=lambda p: p.name)
def test_no_column_check_references_other_columns(path):
    assert not column_check_violations(path.read_text())


def test_8141_regression_rejected_and_table_constraint_present():
    fixed = (MIGRATIONS / '002_rankings.sql').read_text()
    assert 'CONSTRAINT ck_ranking_rules_range CHECK(end_rank>=start_rank)' in fixed
    broken = fixed.replace('end_rank int NOT NULL,', 'end_rank int NOT NULL CHECK(end_rank>=start_rank),')
    assert column_check_violations(broken) == [('dbo.ranking_rules', 'end_rank', ['start_rank'])]


def test_request_procedure_and_runtime_permission_boundary():
    sql = (MIGRATIONS / '005_deletion_request_procedure.sql').read_text()
    body = re.sub(r'--[^\n]*', '', sql)
    parameters = re.findall(r'@(\w+)\s+uniqueidentifier', body)
    assert parameters == ['request_id', 'user_id']
    assert "'requested',SYSUTCDATETIME(),NULL,0,NULL,NULL,NULL" in body
    assert '@@TRANCOUNT=0 OR XACT_STATE()<>1' in body
    assert not re.search(r'\b(?:UPDATE|DELETE|EXECUTE|GRANT)\b', body, re.I)
    root = MIGRATIONS.parents[1]
    grants = (root / 'infra/sqlserver/runtime-grants.review.sql').read_text()
    assert 'GRANT EXECUTE ON OBJECT::dbo.submit_deletion_request' in grants
    assert not re.search(r'GRANT\s+[^;]*\bINSERT\b[^;]*OBJECT::dbo.deletion_requests', grants)
    assert 'DENY INSERT, UPDATE, DELETE ON OBJECT::dbo.deletion_requests' in grants
    assert 'DENY SELECT (approved_for_erasure,pii_cleared_at,purge_after,policy_version,completed_at,requested_at)' in grants
    service = (MIGRATIONS.parent / 'foodsave/service.py').read_text()
    assert 'INSERT INTO dbo.deletion_requests' not in service
    assert 'EXEC dbo.submit_deletion_request @request_id=:id,@user_id=:u' in service


def test_managed_identity_uses_object_id_for_resolution_and_app_id_for_sid():
    grants = (MIGRATIONS.parents[1] / 'infra/sqlserver/runtime-grants.review.sql').read_text()
    assert "WITH OBJECT_ID='REPLACE_WITH_APPROVED_OBJECT_ID'" in grants
    assert "sid=CONVERT(binary(16),CONVERT(uniqueidentifier,'REPLACE_WITH_APPROVED_APP_ID'))" in grants
    assert "CONVERT(uniqueidentifier,'REPLACE_WITH_APPROVED_OBJECT_ID')" not in grants
    assert "authentication_type_desc='EXTERNAL'" in grants
    assert 'ROLLBACK' in grants and 'Principal identity mismatch' in grants
