"""Package verification in Azure temporary storage; no external I/O."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("backend_package", HERE / "build_backend_package.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class PackageTests(unittest.TestCase):
    def test_rejects_untested_source(self):
        with self.assertRaises(ValueError):
            builder.collect("0" * 40)

    def test_exact_package_and_deterministic_readback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = builder.build(builder.SOURCE, root / "first")
            second = builder.build(builder.SOURCE, root / "second")
            self.assertEqual(first["sha256"], second["sha256"])
            self.assertEqual(first["entries_sha256"], second["entries_sha256"])
            self.assertEqual(first, json.loads((root / "first/manifest.json").read_text()))
            self.assertEqual(first["validation"]["build_id"], 13)
            self.assertFalse(first["validation"]["sql_behavior_changed"])
            self.assertFalse(first["validation"]["runtime_permissions_tested"])
            self.assertFalse(first["deployment_authorized_by_this_package"])
            with self.assertRaises(FileExistsError):
                builder.build(builder.SOURCE, root / "first")
            with zipfile.ZipFile(root / "first" / first["file"]) as archive:
                names = archive.namelist()
                self.assertIn("startup.sh", names)
                self.assertIn("requirements.txt", names)
                self.assertIn("foodsave/nearby_queries.py", names)
                self.assertEqual(builder.git_blob(archive.read("startup.sh")), builder.STARTUP_BLOB)
                self.assertIn(b"uvicorn foodsave.api:app", archive.read("startup.sh"))
                self.assertEqual(len(archive.read(builder.FALLBACK)), 805)
                self.assertEqual(hashlib.sha256(archive.read(builder.FALLBACK)).hexdigest(),
                                 builder.FALLBACK_SHA)
                for name in names:
                    self.assertFalse(name.startswith(("migrations/", "tests/", "release/", "home/")))
                    self.assertNotIn(Path(name).name, builder.EXCLUDED | {"owner_migrate.py", ".env"})
                    if name.endswith(".py"):
                        compile(archive.read(name), name, "exec")
                archive.extractall(root / "runtime")
            # Import only the extracted ZIP and check the DB-free liveness endpoint.
            code = (
                "import sys;sys.path.insert(0,sys.argv[1]);"
                "from fastapi.testclient import TestClient;"
                "from foodsave.api import app;"
                "r=TestClient(app).get('/health/live');"
                "assert r.status_code==200 and r.json()=={'status':'alive'}"
            )
            subprocess.run([sys.executable, "-I", "-B", "-c", code, str(root / "runtime")],
                           check=True, timeout=30)


if __name__ == "__main__":
    unittest.main()
