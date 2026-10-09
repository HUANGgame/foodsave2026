"""Create a website candidate from immutable source; never deploy or contact its API."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = "f5ea46c7f9ddd8d5277783488188f90d6c4fa5f9"
API = "https://foodsave-web-tku-aqhxdnhpe8fdhfee.eastasia-01.azurewebsites.net"
PRIVACY_BLOB = "2e51a1c6483ae14efe254b32fad05a0fb3595728"
PUBLIC_KEYS = {"NEXT_PUBLIC_OPERATOR_NAME", "NEXT_PUBLIC_PRIVACY_CONTACT",
               "NEXT_PUBLIC_RETENTION_SUMMARY", "NEXT_PUBLIC_PRIVACY_POLICY_COMPLETE"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(ok, label):
    if not ok:
        raise ValueError(label)


def public_settings(data):
    blob = hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()
    require(blob == PRIVACY_BLOB, "Approved public settings blob mismatch")
    public = {k: v for k, v in json.loads(data).items() if k.startswith("NEXT_PUBLIC_")}
    require(set(public) == PUBLIC_KEYS and all(isinstance(v, str) and v for v in public.values()),
            "Unexpected public configuration")
    require(public["NEXT_PUBLIC_PRIVACY_POLICY_COMPLETE"] == "true", "Approved policy required")
    return {**public, "NEXT_PUBLIC_API_BASE_URL": API, "NEXT_PUBLIC_APP_MODE": "live"}


def collect_output(directory):
    directory = Path(directory)
    require(directory.is_dir() and not directory.is_symlink(), "Output directory required")
    files = {}
    for path in sorted(directory.rglob("*")):
        require(not path.is_symlink(), "Output symlinks are forbidden")
        if path.is_dir():
            continue
        require(path.is_file(), "Only regular output files are allowed")
        name = path.relative_to(directory).as_posix()
        require(path.suffix.lower() not in {".map", ".env", ".py", ".sql"}, "Unexpected source file")
        require(not any(part.startswith(".") or part in {"node_modules", "tests", "fixtures"}
                        for part in PurePosixPath(name).parts), "Unexpected output path")
        files[name] = path.read_bytes()
    require("index.html" in files and any(n.startswith("_next/") for n in files), "Incomplete website")
    require(any(API.encode() in data for data in files.values()), "Expected API missing")
    require(not any(b"api.foodsave.test" in data for data in files.values()), "Fixture API remains")
    return files


def zip_output(path, files):
    path = Path(path)
    require(not path.exists(), "Refuse to overwrite package")
    with zipfile.ZipFile(path, "x", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 10, 9, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    entries = {name: {"sha256": sha(data), "bytes": len(data)} for name, data in sorted(files.items())}
    with zipfile.ZipFile(path) as archive:
        require(archive.testzip() is None and len(archive.namelist()) == len(entries), "ZIP integrity")
        require({name: sha(archive.read(name)) for name in archive.namelist()}
                == {name: entry["sha256"] for name, entry in entries.items()}, "ZIP readback mismatch")
    return {"file": path.name, "sha256": sha(path.read_bytes()), "bytes": path.stat().st_size,
            "entries": entries}


def build(work, output):
    work, output = Path(work).resolve(), Path(output).resolve()
    require(work != output and work not in output.parents and output not in work.parents,
            "Separate source work and deliverable directories required")
    work.mkdir(parents=True, exist_ok=False)
    output.mkdir(parents=True, exist_ok=False)
    raw = subprocess.check_output(["git", "archive", SOURCE], cwd=ROOT)
    backup = work / "source-backup.tar"
    backup.write_bytes(raw)
    require(sha(backup.read_bytes()) == sha(raw), "Source archive backup verification")
    source = work / "source"
    source.mkdir()
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        members = archive.getmembers()
        for member in members:
            p = PurePosixPath(member.name)
            require(not p.is_absolute() and ".." not in p.parts
                    and (member.isdir() or member.isfile()), "Unsafe archive member")
        archive.extractall(source, filter="data")
        for member in members:
            if member.isfile():
                require((source / member.name).read_bytes() == archive.extractfile(member).read(),
                        "Source extraction readback mismatch")
    public = public_settings((source / "infra/privacy-public-settings.example.json").read_bytes())
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("NEXT_PUBLIC_", "FOODSAVE_", "AZURE_"))
           and k not in {"SYSTEM_ACCESSTOKEN", "NODE_OPTIONS", "NODE_ENV"}}
    env.update(public)
    env["NEXT_TELEMETRY_DISABLED"] = "1"
    commands = [["npm", "ci", "--no-audit", "--no-fund"],
                ["npm", "test"],
                ["node", "node_modules/typescript/bin/tsc", "--noEmit", "--incremental", "false"],
                ["npm", "run", "build:release"],
                ["node", "scripts/check-live-bundle.cjs", "out", API]]
    for command in commands:
        subprocess.run(command, cwd=source, env=env, check=True)
    files = collect_output(source / "out")
    privacy_html = files.get("privacy/index.html", b"")
    require(b"foodsave-test-20261007-v2" in privacy_html
            and (API + "/account").encode() in privacy_html, "Privacy page or account link missing")
    static_config = source / "public/staticwebapp.config.json"
    if static_config.exists():
        require(files.get("staticwebapp.config.json") == static_config.read_bytes(),
                "Static Web App configuration was not preserved")
    package = zip_output(output / "foodsave-web-f5ea46c-candidate.zip", files)
    manifest = {
        "source_commit": SOURCE, "status": "CANDIDATE_NOT_DEPLOYED",
        "deployment_authorized_by_this_package": False,
        "public_build_settings": public, "privacy_settings_git_blob": PRIVACY_BLOB,
        "source_archive_sha256": sha(raw),
        "package_lock_sha256": sha((source / "package-lock.json").read_bytes()),
        "node_version": subprocess.check_output(["node", "--version"], text=True).strip(),
        "npm_version": subprocess.check_output(["npm", "--version"], text=True).strip(),
        "checks_passed": commands, "package": package,
        "backend_sql_evidence": {"build_id": 13,
            "preparation_commit": "5cd6e3884f577bf2104292b7a70d4f0674fb323d",
            "application_commit": SOURCE},
        "production_api_contacted_by_packager": False,
        "browser_end_to_end_tested": False, "android_built_or_signed": False,
        "source_staticwebapp_config_present": static_config.exists(),
        "existing_deployed_feature_parity_verified": False,
        "known_limits": [
            "Candidate build does not verify current production API or runtime permissions",
            "Current deployed frontend asset parity remains separately unverified",
            "Historical map-follow, navigation and other missing-feature parity is not implied",
            "No Android package, signing compatibility or device acceptance is established"
        ]
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: package[k] for k in ("file", "sha256", "bytes")}))
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    build(args.work, args.output)
