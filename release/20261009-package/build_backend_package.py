"""Build the tested backend package. No deployment, SQL, mail or cloud changes."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = "f5ea46c7f9ddd8d5277783488188f90d6c4fa5f9"
VALIDATION_COMMIT = "5cd6e3884f577bf2104292b7a70d4f0674fb323d"
VALIDATION_URL = "https://dev.azure.com/foodsave2026-huanggame/FoodSave/_build/results?buildId=13"
MANIFEST_PATH = "release/20261009-nearby/source-hashes.json"
MANIFEST_BLOB = "26c89c577794eca1904f6de451fc5c37b3bc64a1"
STARTUP_BLOB = "de413ce8406462f1bd5e159db3621bf6f09b9dc6"
FALLBACK = "foodsave/static/demo-prizes.json"
FALLBACK_SHA = "7d6e4ec10d7bf5ed99d3868d9077e3831ba16b407a7ad100fa092f45285f5013"
EXCLUDED = {"cli.py", "migrate.py", "erasure.py", "diagnose.py"}


def git_blob(data):
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def checked(ok, label):
    if not ok:
        raise ValueError(label)


def collect(source):
    checked(source == SOURCE, "Only the Build 13 tested application is allowed")
    raw_manifest = subprocess.check_output(
        ["git", "show", f"{VALIDATION_COMMIT}:{MANIFEST_PATH}"], cwd=ROOT)
    checked(git_blob(raw_manifest) == MANIFEST_BLOB, "Validation manifest blob mismatch")
    validation = json.loads(raw_manifest)
    checked(validation["commit"] == SOURCE, "Validation source mismatch")
    raw = subprocess.check_output(["git", "archive", SOURCE, "backend"], cwd=ROOT)
    files = {}
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            path = PurePosixPath(member.name)
            checked(not path.is_absolute() and ".." not in path.parts, "Unsafe source path")
            runtime = (member.name.startswith("backend/foodsave/")
                       and path.suffix in (".py", ".json", ".js", ".css", ".html")
                       and path.name not in EXCLUDED)
            if member.name not in {"backend/requirements.txt", "backend/startup.sh"} and not runtime:
                continue
            data = archive.extractfile(member).read()
            if member.name == "backend/startup.sh":
                checked(git_blob(data) == STARTUP_BLOB, "Startup blob mismatch")
            else:
                checked(hashlib.sha256(data).hexdigest() == validation["files"].get(member.name),
                        "Runtime file does not match tested source: " + member.name)
            files[str(path.relative_to("backend"))] = data
    expected = {
        name.removeprefix("backend/") for name in validation["files"]
        if name == "backend/requirements.txt" or (
            name.startswith("backend/foodsave/")
            and PurePosixPath(name).suffix in (".py", ".json", ".js", ".css", ".html")
            and PurePosixPath(name).name not in EXCLUDED)
    } | {"startup.sh"}
    checked(set(files) == expected, "Runtime package file set mismatch")
    checked("foodsave/nearby_queries.py" in files, "Nearby helper is required")
    checked(len(files[FALLBACK]) == 805
            and hashlib.sha256(files[FALLBACK]).hexdigest() == FALLBACK_SHA,
            "Verified fallback mismatch")
    return files


def build(source, output):
    files = collect(source)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    path = output / f"foodsave-api-{source[:7]}-candidate.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 10, 9, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}
    with zipfile.ZipFile(path) as archive:
        checked(archive.testzip() is None, "ZIP CRC verification failed")
        checked(len(archive.namelist()) == len(hashes), "Duplicate archive entries")
        checked({name: hashlib.sha256(archive.read(name)).hexdigest()
                 for name in archive.namelist()} == hashes, "ZIP readback mismatch")
    manifest = {
        "source_commit": SOURCE,
        "status": "PACKAGED_NOT_DEPLOYED",
        "deployment_authorized_by_this_package": False,
        "file": path.name,
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "entries_sha256": hashes,
        "startup": {"command": "sh startup.sh", "path": "startup.sh",
                    "git_blob": STARTUP_BLOB},
        "validation": {
            "application_commit": SOURCE, "preparation_commit": VALIDATION_COMMIT,
            "build_id": 13, "build_url": VALIDATION_URL,
            "evidence": "Recorded successful Azure validation; packaging does not rerun SQL",
            "sql_behavior_changed": False, "isolated_sql_passed": True,
            "rollback_verified": True, "fresh_catalog_empty_verified": True,
            "runtime_permissions_tested": False, "concurrency_tested": False,
            "populated_production_upgrade_tested": False,
            "deployed_http_tested_by_this_build": False
        },
        "fallback": {"path": FALLBACK, "bytes": 805, "sha256": FALLBACK_SHA},
        "external_store": "/home/data/foodsave/demo-prizes.json",
        "external_store_created_or_modified": False,
        "frontend_built_or_modified": False, "android_built_or_modified": False,
        "real_mail_sent": False, "sql_executed_during_packaging": False,
        "remaining_gates": [
            "Verify current production schema, procedure definitions and migration delta",
            "Verify production runtime identity and effective least-privilege permissions",
            "Verify recoverable runtime, configuration and database backups",
            "Approve exact production changes and deployment/recovery route",
            "Verify deployed backend HTTP and separately validate frontend/Android"
        ],
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, choices=[SOURCE])
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output), ensure_ascii=False, indent=2))
