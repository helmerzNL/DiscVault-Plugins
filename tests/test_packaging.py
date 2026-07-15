from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.build_plugin import build_plugin


REPO_ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_archive_is_byte_reproducible_with_one_plugin_root(self):
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first, first_checksum = build_plugin("movievault_v2", Path(first_dir))
            second, second_checksum = build_plugin("movievault_v2", Path(second_dir))

            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(first_checksum.read_text(), second_checksum.read_text())
            with zipfile.ZipFile(first) as bundle:
                names = bundle.namelist()
                self.assertEqual(names, sorted(names))
                self.assertTrue(names)
                self.assertTrue(all(name.startswith("movievault_v2/") for name in names))
                self.assertEqual(
                    {info.date_time for info in bundle.infolist()},
                    {(1980, 1, 1, 0, 0, 0)},
                )

            digest = hashlib.sha256(first.read_bytes()).hexdigest()
            self.assertEqual(
                first_checksum.read_text(encoding="ascii"),
                f"{digest}  {first.name}\n",
            )

    def test_catalog_matches_manifest_and_release_names(self):
        manifest = json.loads(
            (REPO_ROOT / "plugins" / "movievault_v2" / "manifest.json").read_text(encoding="utf-8")
        )
        catalog = json.loads((REPO_ROOT / "catalog.json").read_text(encoding="utf-8"))
        entry = catalog["plugins"][0]

        self.assertEqual(entry["id"], manifest["id"])
        self.assertEqual(entry["version"], manifest["version"])
        self.assertEqual(entry["minimumDiscVaultVersion"], manifest["minimumDiscVaultVersion"])
        self.assertEqual(entry["archive"], "movievault_v2_1.0.2.zip")
        self.assertEqual(entry["releaseTag"], "movievault_v2-v1.0.2")


if __name__ == "__main__":
    unittest.main()
