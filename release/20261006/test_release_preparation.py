"""Local preparation checks only; never connects to SQL or Azure."""
import importlib.util,json,subprocess,sys
from pathlib import Path
import pytest
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('validate_sql',HERE/'validate_sql.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
def test_fixed_source_and_exact_012_adaptation():
    batches=dict(v.sql_files());assert len(batches)==14
    old=(v.ROOT/'backend/migrations/012_account_lifecycle.sql').read_text()
    assert "DB_NAME()<>N'foodsave'" in old
    assert "DB_NAME()<>N'foodsave-validation-20261006'" in batches['012_account_lifecycle.sql']
    assert batches['013_store_capabilities.sql']==(v.ROOT/'backend/migrations/013_store_capabilities.sql').read_text()
    assert batches['014_store_location.sql']==(v.ROOT/'backend/migrations/014_store_location.sql').read_text()
def test_plan_has_no_database_access():
    p=subprocess.run([sys.executable,str(HERE/'validate_sql.py')],capture_output=True,text=True,check=True)
    plan=json.loads(p.stdout);assert plan['connects'] is False;assert plan['database']=='foodsave-validation-20261006'
def test_hash_mismatch_refuses_before_connect(tmp_path,monkeypatch):
    data=json.loads(v.MANIFEST.read_text());first=next(iter(data['files']));data['files'][first]='0'*64
    wrong=tmp_path/'manifest.json';wrong.write_text(json.dumps(data));monkeypatch.setattr(v,'MANIFEST',wrong)
    with pytest.raises(v.CheckFailed,match='source_hash'):v.sql_files()
def test_procedure_batches_not_concatenated():
    for name,sql in v.sql_files():
        if name[:3] in ('005','008','009','010','011'):
            code='\n'.join(x for x in sql.splitlines() if not x.strip().startswith('--')).lstrip()
            assert code.startswith('CREATE PROCEDURE')

def good_connection():
    return 'Driver={ODBC Driver 18 for SQL Server};Server=tcp:approved.database.windows.net,1433;Database=foodsave-validation-20261006;Encrypt=yes;TrustServerCertificate=no;'
def test_braced_password_is_not_parsed_as_security_settings():
    assert v.validate_connection(good_connection()+'UID=owner;PWD={semi;equals=x;brace}}end};')['pwd']=='semi;equals=x;brace}end'
@pytest.mark.parametrize('value',[
    'Driver={ODBC Driver 18 for SQL Server};Server=approved.database.windows.net;Database=foodsave-validation-20261006;PWD={Encrypt=yes;TrustServerCertificate=no};Encrypt=no;TrustServerCertificate=yes;',
    good_connection()+'Encrypt=no;',good_connection()+'Database=foodsave;',
    good_connection().replace('Database=foodsave-validation-20261006','Database=foodsave'),
    good_connection()+'DSN=production;',good_connection()+'FileDSN=x;',good_connection()+'Trusted_Connection=yes;',
    good_connection()+'Initial Catalog=foodsave;',good_connection()+'AttachDBFileName=x;',
    good_connection()+'PWD={unclosed;',good_connection()+'PWD={closed}suffix;',
    good_connection().replace('approved.database.windows.net','localhost'),
])
def test_invalid_or_ambiguous_connection_refused_without_network(value):
    with pytest.raises(v.CheckFailed):v.validate_connection(value)
