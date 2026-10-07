"""Backend-only candidate from a Git commit; no deployment or production I/O."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
FALLBACK = 'foodsave/static/demo-prizes.json'
FALLBACK_SHA = '7d6e4ec10d7bf5ed99d3868d9077e3831ba16b407a7ad100fa092f45285f5013'
EXCLUDED = {'cli.py', 'migrate.py', 'erasure.py', 'diagnose.py'}


def collect(source):
    if not re.fullmatch(r'[0-9a-f]{40}', source):
        raise ValueError('Provide a full immutable Git commit SHA')
    files = {}
    raw = subprocess.check_output(['git', 'archive', source, 'backend'], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            p = Path(member.name)
            runtime = (member.name.startswith('backend/foodsave/') and
                       p.suffix in ('.py', '.json', '.js', '.css', '.html') and p.name not in EXCLUDED)
            if member.name == 'backend/requirements.txt' or runtime:
                files[str(p.relative_to('backend'))] = archive.extractfile(member).read()
    fallback = files[FALLBACK]
    if len(fallback) != 805 or hashlib.sha256(fallback).hexdigest() != FALLBACK_SHA:
        raise ValueError('Verified production fallback bytes do not match')
    return files


def build(source, output):
    files = collect(source)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    path = output / f'foodsave-api-{source[:7]}-candidate.zip'
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 10, 6, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        assert {n: hashlib.sha256(archive.read(n)).hexdigest() for n in archive.namelist()} == hashes
    manifest = {'source_commit': source, 'status': 'LOCAL_CANDIDATE_NOT_DEPLOYED_NOT_RELEASE_APPROVED',
                'file': path.name, 'bytes': path.stat().st_size,
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'entries_sha256': hashes,
                'fallback': {'path': FALLBACK, 'bytes': 805, 'sha256': FALLBACK_SHA,
                             'evidence': 'Matches release coordinator verified production fallback bytes; full private production archive not copied into this workspace or deliverable'},
                'external_store': '/home/data/foodsave/demo-prizes.json',
                'external_store_created_or_modified': False,
                'frontend_built_or_modified': False,
                'real_mail_sent': False, 'real_sql_run': False,
                'blockers': ['Production deployment/verification of approved policy remains pending',
                             'Verified application ID/signing where applicable',
                             'Runtime identity/SID/rights and real isolated SQL validation',
                             'Production SQL/config backup and authorized deployment/recovery route'],
                'sql_validation_note': 'Existing validation tool remains pinned to 1a5a6d6; not validation of this candidate'}
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output), ensure_ascii=False, indent=2))
