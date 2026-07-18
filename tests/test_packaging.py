from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

from scripts.build_plugin import build_plugin, discover_plugin_ids
from scripts.check_versions import changed_plugins


REPO_ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_version_guard_maps_shared_runtime_changes_to_consuming_plugins(self):
        changed_paths = "\n".join(
            [
                "plugins/_collection_import_base.py",
                "plugins/wikidata_awards.py",
            ]
        )
        completed = mock.Mock(returncode=0, stdout=changed_paths)
        with mock.patch("scripts.check_versions.subprocess.run", return_value=completed):
            changed = changed_plugins("origin/main")

        expected_imports = {
            plugin_id
            for plugin_id in discover_plugin_ids()
            if plugin_id.startswith("import_")
        }
        self.assertEqual(changed, expected_imports | {"tmdb"})

    def test_every_plugin_archive_is_byte_reproducible_with_one_plugin_root(self):
        plugin_ids = discover_plugin_ids()
        self.assertTrue(plugin_ids)

        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            for plugin_id in plugin_ids:
                with self.subTest(plugin=plugin_id):
                    first, first_checksum = build_plugin(plugin_id, Path(first_dir))
                    second, second_checksum = build_plugin(plugin_id, Path(second_dir))

                    self.assertEqual(first.read_bytes(), second.read_bytes())
                    self.assertEqual(first_checksum.read_bytes(), second_checksum.read_bytes())
                    with zipfile.ZipFile(first) as bundle:
                        names = bundle.namelist()
                        self.assertEqual(names, sorted(names))
                        self.assertTrue(names)
                        self.assertTrue(all(name.startswith(f"{plugin_id}/") for name in names))
                        self.assertEqual(
                            {info.date_time for info in bundle.infolist()},
                            {(1980, 1, 1, 0, 0, 0)},
                        )

                    digest = hashlib.sha256(first.read_bytes()).hexdigest()
                    self.assertEqual(
                        first_checksum.read_text(encoding="ascii"),
                        f"{digest}  {first.name}\n",
                    )

    def test_shared_runtime_files_are_packaged_only_for_their_consumers(self):
        with tempfile.TemporaryDirectory() as root_dir, tempfile.TemporaryDirectory() as output_dir:
            plugin_root = Path(root_dir)
            for plugin_id in ("import_example", "tmdb", "other"):
                plugin_dir = plugin_root / plugin_id
                plugin_dir.mkdir()
                (plugin_dir / "manifest.json").write_text(
                    json.dumps({"id": plugin_id, "version": "1.0.0"}),
                    encoding="utf-8",
                )
                (plugin_dir / "plugin.py").write_text("", encoding="utf-8")
            (plugin_root / "_collection_import_base.py").write_text(
                "COLLECTION_HELPER = True\n",
                encoding="utf-8",
            )
            (plugin_root / "wikidata_awards.py").write_text(
                "AWARDS_HELPER = True\n",
                encoding="utf-8",
            )

            with mock.patch("scripts.build_plugin.PLUGIN_ROOT", plugin_root):
                self.assertEqual(discover_plugin_ids(), ["import_example", "other", "tmdb"])
                archives = {
                    plugin_id: build_plugin(plugin_id, Path(output_dir))[0]
                    for plugin_id in discover_plugin_ids()
                }

            expected_helpers = {
                "import_example": {"import_example/_collection_import_base.py"},
                "tmdb": {"tmdb/wikidata_awards.py"},
                "other": set(),
            }
            for plugin_id, archive in archives.items():
                with self.subTest(plugin=plugin_id), zipfile.ZipFile(archive) as bundle:
                    helper_names = {
                        name
                        for name in bundle.namelist()
                        if name.endswith(("_collection_import_base.py", "wikidata_awards.py"))
                    }
                    self.assertEqual(helper_names, expected_helpers[plugin_id])

    def test_tmdb_archive_loads_bundled_wikidata_awards(self):
        with tempfile.TemporaryDirectory() as output_dir, tempfile.TemporaryDirectory() as extract_dir:
            archive, _checksum = build_plugin("tmdb", Path(output_dir))
            with zipfile.ZipFile(archive) as bundle:
                bundle.extractall(extract_dir)
            plugin_dir = Path(extract_dir) / "tmdb"
            spec = importlib.util.spec_from_file_location(
                "packaged_tmdb",
                plugin_dir / "plugin.py",
            )
            module = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            previous = sys.modules.pop("wikidata_awards", None)
            original_path = list(sys.path)
            try:
                sys.path[:] = [
                    entry
                    for entry in sys.path
                    if Path(entry or ".").resolve() != plugin_dir.resolve()
                ]
                spec.loader.exec_module(module)
                helper = module._import_wikidata_awards()
                self.assertIsNotNone(helper)
                self.assertEqual(
                    Path(helper.__file__).resolve(),
                    (plugin_dir / "wikidata_awards.py").resolve(),
                )
            finally:
                sys.path[:] = original_path
                sys.modules.pop("wikidata_awards", None)
                if previous is not None:
                    sys.modules["wikidata_awards"] = previous

    def test_catalog_matches_all_discovered_manifests_and_release_names(self):
        catalog = json.loads((REPO_ROOT / "catalog.json").read_text(encoding="utf-8"))
        entries = {entry["id"]: entry for entry in catalog["plugins"]}

        for plugin_id in discover_plugin_ids():
            with self.subTest(plugin=plugin_id):
                manifest = json.loads(
                    (REPO_ROOT / "plugins" / plugin_id / "manifest.json").read_text(
                        encoding="utf-8"
                    )
                )
                entry = entries[plugin_id]
                self.assertEqual(entry["version"], manifest["version"])
                self.assertEqual(
                    entry["minimumDiscVaultVersion"],
                    manifest["minimumDiscVaultVersion"],
                )
                self.assertEqual(
                    entry["archive"],
                    f"{plugin_id}_{manifest['version']}.zip",
                )
                self.assertEqual(
                    entry["releaseTag"],
                    f"{plugin_id}-v{manifest['version']}",
                )


if __name__ == "__main__":
    unittest.main()
