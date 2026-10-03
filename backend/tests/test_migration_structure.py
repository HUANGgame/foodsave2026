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
