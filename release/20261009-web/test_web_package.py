"""Offline tests for web packaging safeguards; no build or network in these tests."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("web_package", HERE / "build_web_package.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class WebPackageTests(unittest.TestCase):
    def test_unapproved_settings_rejected(self):
        with self.assertRaises(ValueError):
            builder.public_settings(b'{"NEXT_PUBLIC_PRIVACY_POLICY_COMPLETE":"true"}')

    def test_output_zip_readback_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            out = root / "out"
            (out / "_next").mkdir(parents=True)
            (out / "index.html").write_text("<html>candidate</html>")
            (out / "_next/app.js").write_text(builder.API)
            files = builder.collect_output(out)
            first = builder.zip_output(root / "first.zip", files)
            second = builder.zip_output(root / "second.zip", files)
            self.assertEqual(first["sha256"], second["sha256"])
            with zipfile.ZipFile(root / "first.zip") as archive:
                self.assertEqual(set(archive.namelist()), set(files))
            with self.assertRaises(ValueError):
                builder.zip_output(root / "first.zip", files)
            (out / ".env").write_text("fake")
            with self.assertRaises(ValueError):
                builder.collect_output(out)

    def test_symlink_and_fixture_api_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            (out / "_next").mkdir()
            (out / "index.html").write_text(builder.API)
            asset = out / "_next/app.js"
            asset.write_text("https://api.foodsave.test")
            with self.assertRaises(ValueError):
                builder.collect_output(out)
            asset.write_text(builder.API)
            (out / "linked.html").symlink_to(out / "index.html")
            with self.assertRaises(ValueError):
                builder.collect_output(out)


if __name__ == "__main__":
    unittest.main()
