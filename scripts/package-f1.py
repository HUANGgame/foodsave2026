"""Deterministic allowlisted code ZIPs; no builds, uploads, auth or provision."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'backend'
OUT = ROOT / 'artifacts'
RUNTIME = ['__init__','api','admin','db','diagnose','ranking','schemas','security','service']
OWNER = ['__init__','admin','db','ranking','schemas','security','service','migrate','cli','erasure']


def package(name, paths):
    target = OUT / name
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(paths):
            info = zipfile.ZipInfo(str(path.relative_to(BACKEND)), (2026,10,3,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        assert not any('.env' in n or '__pycache__' in n or n.endswith(('.apk','.aab','.keystore')) for n in names)
        assert all(b'api.foodsave.test' not in archive.read(n) for n in names)
    return {'file': name, 'bytes': target.stat().st_size, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'entries': names}


def main():
    OUT.mkdir(exist_ok=True)
    runtime = [BACKEND/'requirements.txt', BACKEND/'startup.sh']
    runtime += [BACKEND/'foodsave'/f'{name}.py' for name in RUNTIME]
    runtime += list((BACKEND/'foodsave'/'static').glob('*'))
    owner = [BACKEND/'requirements.txt', BACKEND/'owner_migrate.py', BACKEND/'owner_erase.py', BACKEND/'qa'/'terminal_rollback.py']
    owner += [BACKEND/'foodsave'/f'{name}.py' for name in OWNER]
    owner += list((BACKEND/'migrations').glob('*.sql'))
    result = [package('foodsave-f1-code.zip', runtime), package('foodsave-owner-migrations.zip', owner)]
    (OUT/'f1-package-verification.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps([{k:v for k,v in r.items() if k!='entries'} for r in result], indent=2))


if __name__ == '__main__':
    main()
