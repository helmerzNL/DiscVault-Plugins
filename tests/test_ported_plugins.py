from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "plugins"
PLUGIN_IDS = (
    "barcode_hub",
    "dvd_fr",
    "import_bluray_com",
    "import_clz_movies",
    "import_letterboxd",
    "import_mymovies_dk",
    "jellyfin",
    "omdb",
    "plex",
    "trakt",
    "upcitemdb",
    "wikidata",
)


def load_plugin(plugin_id: str):
    module_name = f"ported_{plugin_id}_plugin"
    spec = importlib.util.spec_from_file_location(
        module_name,
        PLUGIN_ROOT / plugin_id / "plugin.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def install_collection_import_namespace() -> None:
    package = types.ModuleType("next_plugins")
    package.__path__ = [str(PLUGIN_ROOT)]
    sys.modules["next_plugins"] = package
    spec = importlib.util.spec_from_file_location(
        "next_plugins._collection_import_base",
        PLUGIN_ROOT / "_collection_import_base.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)


class PortedPluginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        install_collection_import_namespace()

    def test_manifests_are_next_1_and_require_26_4_63(self):
        for plugin_id in PLUGIN_IDS:
            with self.subTest(plugin_id=plugin_id):
                plugin_dir = PLUGIN_ROOT / plugin_id
                manifest = json.loads(
                    (plugin_dir / "manifest.json").read_text(encoding="utf-8")
                )
                self.assertEqual(manifest["id"], plugin_id)
                self.assertEqual(manifest["discVaultPluginApi"], "next-1")
                self.assertEqual(manifest["minimumDiscVaultVersion"], "26.4.63")
                self.assertEqual(
                    {path.name for path in plugin_dir.iterdir() if path.is_file()},
                    {"manifest.json", "plugin.py"},
                )

    def test_all_python_sources_compile_and_plugins_import(self):
        sources = [PLUGIN_ROOT / "_collection_import_base.py"]
        sources.extend(PLUGIN_ROOT / plugin_id / "plugin.py" for plugin_id in PLUGIN_IDS)
        for source_path in sources:
            with self.subTest(source=source_path.name):
                source = source_path.read_text(encoding="utf-8")
                compile(source, str(source_path), "exec")
        for plugin_id in PLUGIN_IDS:
            with self.subTest(plugin_id=plugin_id):
                self.assertIsNotNone(load_plugin(plugin_id))

    def test_collection_import_reads_csv_without_network(self):
        plugin = load_plugin("import_clz_movies")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "clz_movies.csv"
            source.write_text(
                "Title,Year,Barcode,Format,IMDb ID\n"
                "Example Film,2024,4006381333931,Blu-ray,tt1234567\n",
                encoding="utf-8",
            )

            inspection = plugin.inspect_source({"sourcePath": str(source)}, {})
            imported = plugin.import_source(
                {
                    "sourcePath": str(source),
                    "sourceDatabaseHash": inspection["sourceDatabaseHash"],
                },
                {},
            )

        self.assertEqual(inspection["status"], "ok")
        self.assertEqual(imported["status"], "completed")
        self.assertEqual(imported["items"][0]["title"], "Example Film")
        self.assertEqual(imported["items"][0]["imdbId"], "tt1234567")

    def test_stable_plugins_have_offline_configuration_paths(self):
        jellyfin = load_plugin("jellyfin")
        plex = load_plugin("plex")
        trakt = load_plugin("trakt")
        omdb = load_plugin("omdb")
        upcitemdb = load_plugin("upcitemdb")

        self.assertEqual(
            jellyfin.health_check({"settings": {"baseUrl": "https://jellyfin.example"}})["status"],
            "configured",
        )
        self.assertEqual(
            plex.health_check(
                {
                    "settings": {"baseUrl": "https://plex.example"},
                    "secrets": {"token": "test-token"},
                }
            )["status"],
            "configured",
        )
        self.assertEqual(
            trakt.health_check(
                {
                    "settings": {"username": "me"},
                    "secrets": {"clientId": "test-client", "accessToken": "test-token"},
                }
            )["status"],
            "configured",
        )
        self.assertEqual(omdb.health_check({})["status"], "needs_configuration")
        self.assertEqual(upcitemdb.search_barcode({}, {})["status"], "skipped")


if __name__ == "__main__":
    unittest.main()
