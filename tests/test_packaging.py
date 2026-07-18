from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.build_plugin import build_all_plugins, build_plugin, discover_plugin_ids


REPO_ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_all_plugins_are_discovered_and_built_in_stable_order(self):
        with tempfile.TemporaryDirectory() as plugin_dir, tempfile.TemporaryDirectory() as output_dir:
            plugin_root = Path(plugin_dir)
            for plugin_id, version in (("zeta", "2.0.0"), ("alpha", "1.0.0")):
                source = plugin_root / plugin_id
                source.mkdir()
                (source / "manifest.json").write_text(
                    json.dumps({"id": plugin_id, "version": version}),
                    encoding="utf-8",
                )
                (source / "plugin.py").write_text(f'PLUGIN_ID = "{plugin_id}"\n', encoding="utf-8")

            self.assertEqual(discover_plugin_ids(plugin_root), ["alpha", "zeta"])
            artifacts = build_all_plugins(Path(output_dir), plugin_root)

            self.assertEqual(
                [archive.name for archive, _checksum in artifacts],
                ["alpha_1.0.0.zip", "zeta_2.0.0.zip"],
            )
            self.assertTrue(all(archive.is_file() for archive, _checksum in artifacts))
            self.assertTrue(all(checksum.is_file() for _archive, checksum in artifacts))

    def test_plugin_discovery_requires_at_least_one_manifest(self):
        with tempfile.TemporaryDirectory() as plugin_dir:
            with self.assertRaisesRegex(ValueError, "No plugin manifests found"):
                discover_plugin_ids(Path(plugin_dir))

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
        manifests = {
            path.parent.name: json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((REPO_ROOT / "plugins").glob("*/manifest.json"))
        }
        catalog = json.loads((REPO_ROOT / "catalog.json").read_text(encoding="utf-8"))
        entries = {entry["id"]: entry for entry in catalog["plugins"]}

        self.assertEqual(set(entries), set(manifests))
        for plugin_id, manifest in manifests.items():
            with self.subTest(plugin_id=plugin_id):
                entry = entries[plugin_id]
                self.assertEqual(entry["version"], manifest["version"])
                self.assertEqual(
                    entry["minimumDiscVaultVersion"],
                    manifest["minimumDiscVaultVersion"],
                )
                self.assertEqual(entry["archive"], f"{plugin_id}_{manifest['version']}.zip")
                self.assertEqual(
                    entry["checksum"],
                    f"{plugin_id}_{manifest['version']}.zip.sha256",
                )
                self.assertEqual(
                    entry["releaseTag"],
                    f"{plugin_id}-v{manifest['version']}",
                )


if __name__ == "__main__":
    unittest.main()
