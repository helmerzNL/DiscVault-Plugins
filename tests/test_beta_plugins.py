from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "plugins"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


bluray_com = load_module("beta_bluray_com", PLUGIN_ROOT / "bluray_com" / "plugin.py")
movievault_26 = load_module("beta_movievault_26", PLUGIN_ROOT / "movievault_26" / "plugin.py")
tmdb = load_module("beta_tmdb", PLUGIN_ROOT / "tmdb" / "plugin.py")
wikidata_awards = load_module("beta_wikidata_awards", PLUGIN_ROOT / "wikidata_awards.py")


class BetaManifestTests(unittest.TestCase):
    def test_manifests_match_beta_runtime_contract(self):
        expected = {
            "bluray_com": {
                "version": "1.0.5",
                "capabilities": {"search_title"},
                "entrypoints": {"search_title"},
            },
            "movievault_26": {
                "version": "1.8.0",
                "capabilities": {
                    "connection_recovery_action",
                    "describe_payload",
                    "activity_summary",
                    "prepare_barcode_update",
                    "prepare_container_update",
                    "member_intelligence",
                },
                "entrypoints": {
                    "connection_recovery_action",
                    "describe_payload",
                    "activity_summary",
                    "prepare_barcode_update",
                    "prepare_container_update",
                    "member_intelligence",
                },
            },
            "tmdb": {
                "version": "1.0.3",
                "capabilities": {"person_details", "person_filmography", "person_awards"},
                "entrypoints": {"person_details", "person_filmography", "person_awards"},
            },
        }
        modules = {
            "bluray_com": bluray_com,
            "movievault_26": movievault_26,
            "tmdb": tmdb,
        }

        for plugin_id, contract in expected.items():
            with self.subTest(plugin=plugin_id):
                manifest = json.loads(
                    (PLUGIN_ROOT / plugin_id / "manifest.json").read_text(encoding="utf-8")
                )
                self.assertEqual(manifest["id"], plugin_id)
                self.assertEqual(manifest["version"], contract["version"])
                self.assertEqual(manifest["minimumDiscVaultVersion"], "26.4.63")
                self.assertTrue(contract["capabilities"].issubset(manifest["capabilities"]))
                for entrypoint in contract["entrypoints"]:
                    self.assertTrue(callable(getattr(modules[plugin_id], entrypoint, None)))

        movievault_manifest = json.loads(
            (PLUGIN_ROOT / "movievault_26" / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertNotIn("person_details", movievault_manifest["capabilities"])


class BlurayComBetaTests(unittest.TestCase):
    def test_release_variant_search_is_opt_in_and_returns_release_metadata(self):
        with mock.patch.object(bluray_com, "_release_urls") as release_urls:
            skipped = bluray_com.search_title({"title": "Alien"}, {})
        self.assertEqual(skipped["status"], "skipped")
        release_urls.assert_not_called()

        url = "https://www.blu-ray.com/movies/Alien-4K-Blu-ray/12345/"
        parsed = {
            "status": "hit",
            "releaseTitle": "Alien: 45th Anniversary Edition",
            "format": "4K UHD",
            "isBoxSetCandidate": True,
            "movie": {
                "title": "Alien",
                "year": "1979",
                "posterUrl": "https://images.example/alien.jpg",
            },
        }
        with (
            mock.patch.object(bluray_com, "_release_urls", return_value=[url]) as release_urls,
            mock.patch.object(bluray_com, "_parse_page", return_value=parsed),
        ):
            result = bluray_com.search_title(
                {"title": "Alien", "releaseVariants": True, "maxReleases": 1},
                {},
            )

        self.assertEqual(result["status"], "hit")
        self.assertEqual(result["items"][0]["releaseTitle"], parsed["releaseTitle"])
        self.assertEqual(result["items"][0]["format"], "4K UHD")
        self.assertTrue(result["items"][0]["isBoxSetCandidate"])
        release_urls.assert_called_once_with("Alien", "", limit=1)


class MovieVault26BetaTests(unittest.TestCase):
    def test_receiver_helpers_filter_private_data_and_normalize_members(self):
        skipped = movievault_26.prepare_barcode_update(
            {"barcode": "MANUAL-123", "entityType": "release"},
            {},
        )
        barcode = movievault_26.prepare_barcode_update(
            {
                "barcode": "8712626068546",
                "entityType": "release",
                "identity": "release-1",
                "sourceReference": {
                    "type": "release",
                    "barcode": "8712626068546",
                    "owner_id": "private-owner",
                },
            },
            {},
        )
        container = movievault_26.prepare_container_update(
            {
                "identity": "box-1",
                "container": {
                    "containerType": "box_set",
                    "title": "Back to the Future Trilogy",
                    "barcode": "5050582369601",
                    "owner_id": "private-owner",
                    "members": [
                        {"title": "Back to the Future", "year": "1985", "tmdbId": "105"},
                        {"title": "Back to the Future Part II", "year": "1989"},
                    ],
                },
            },
            {},
        )
        intelligence = movievault_26.member_intelligence(
            {
                "members": [
                    {"title": "Example One", "year": "2001", "tmdbId": "1"},
                    {"title": "Example One", "year": "2001", "tmdbId": "1"},
                    {"title": "Example Two", "year": "2002"},
                ]
            },
            {},
        )

        self.assertEqual(skipped["reason"], "not_public_barcode")
        self.assertEqual(barcode["payload"], {"barcode": "8712626068546"})
        self.assertNotIn("private-owner", str(barcode))
        self.assertEqual(container["entityType"], "box_set")
        self.assertEqual(container["payload"]["memberCount"], 2)
        self.assertEqual(container["memberIntelligence"]["membersIdentified"], 1)
        self.assertNotIn("private-owner", str(container))
        self.assertEqual(intelligence["memberCount"], 2)
        self.assertEqual(intelligence["membersNeedingConfirmation"], 1)


class TmdbBetaTests(unittest.TestCase):
    def test_person_details_and_filmography_normalize_upstream_payloads(self):
        person = {
            "name": "Example Person",
            "biography": "",
            "birthday": "1970-01-01",
            "deathday": None,
            "place_of_birth": "Example City",
            "known_for_department": "Acting",
            "also_known_as": ["Example Alias"],
            "profile_path": "/primary.jpg",
            "images": {
                "profiles": [
                    {"file_path": "/secondary.jpg", "vote_average": 8},
                ]
            },
            "external_ids": {"imdb_id": "nm0000001"},
            "translations": {
                "translations": [
                    {
                        "iso_639_1": "nl",
                        "iso_3166_1": "NL",
                        "data": {"biography": "Nederlandse biografie."},
                    }
                ]
            },
        }
        credits = {
            "cast": [
                {
                    "id": 10,
                    "media_type": "movie",
                    "title": "Example Film",
                    "release_date": "2001-02-03",
                    "character": "Lead",
                },
                {"id": 11, "media_type": "tv", "name": "Ignored TV"},
            ],
            "crew": [
                {
                    "id": 12,
                    "media_type": "movie",
                    "title": "Directed Film",
                    "release_date": "2002-03-04",
                    "job": "Director",
                }
            ],
        }

        def fake_request(_context, path, **_params):
            return credits if path.endswith("/combined_credits") else person

        with mock.patch.object(tmdb, "_request", side_effect=fake_request):
            details = tmdb.person_details(
                {"tmdbId": "585"},
                {"settings": {"language": "nl-NL"}},
            )
            filmography = tmdb.person_filmography(
                {"tmdbId": "585"},
                {"settings": {"language": "nl-NL"}},
            )

        self.assertEqual(details["biography"], "Nederlandse biografie.")
        self.assertEqual(details["imdbId"], "nm0000001")
        self.assertEqual(details["profiles"][0], tmdb.IMAGE_BASE + "/primary.jpg")
        self.assertEqual(filmography["counts"], {"cast": 1, "crew": 1, "total": 2})
        self.assertEqual(filmography["combinedCredits"]["crew"][0]["job"], "Director")

    def test_person_awards_uses_grouped_bundled_contract_without_network(self):
        awards = [
            {
                "award": "Example Award",
                "awardWikidataId": "Q100",
                "year": 2025,
                "result": "won",
            }
        ]
        fake_module = types.SimpleNamespace(
            fetch_person_awards=lambda **kwargs: {
                "wikidataId": "Q42",
                "awards": awards,
                "arguments": kwargs,
            },
            group_awards=lambda rows: [{"award": rows[0]["award"], "items": rows}],
        )
        with mock.patch.object(tmdb, "_import_wikidata_awards", return_value=fake_module):
            result = tmdb.person_awards(
                {"tmdbId": "585", "imdbId": "nm0000001"},
                {"settings": {"language": "nl-NL"}},
            )

        self.assertEqual(result["status"], "hit")
        self.assertEqual(result["wikidataId"], "Q42")
        self.assertEqual(result["awardGroups"][0]["award"], "Example Award")

    def test_wikidata_import_prefers_core_module_then_finds_standalone_bundle(self):
        core_module = types.ModuleType("wikidata_awards")
        with mock.patch.dict(sys.modules, {"wikidata_awards": core_module}):
            self.assertIs(tmdb._import_wikidata_awards(), core_module)

        previous = sys.modules.pop("wikidata_awards", None)
        original_path = list(sys.path)
        try:
            sys.path[:] = [
                entry
                for entry in sys.path
                if Path(entry or ".").resolve() != PLUGIN_ROOT.resolve()
            ]
            bundled = tmdb._import_wikidata_awards()
            self.assertIsNotNone(bundled)
            self.assertEqual(
                Path(bundled.__file__).resolve(),
                (PLUGIN_ROOT / "wikidata_awards.py").resolve(),
            )
        finally:
            sys.path[:] = original_path
            sys.modules.pop("wikidata_awards", None)
            if previous is not None:
                sys.modules["wikidata_awards"] = previous


class WikidataAwardsBetaTests(unittest.TestCase):
    def test_normalization_dedupes_rows_and_prefers_win_over_nomination(self):
        def value(text):
            return {"type": "literal", "value": text}

        rows = [
            {
                "type": value("nominated"),
                "award": value("http://www.wikidata.org/entity/Q100"),
                "awardLabel": value("Example Award"),
                "time": value("+2025-00-00T00:00:00Z"),
                "work": value("http://www.wikidata.org/entity/Q200"),
                "workLabel": value("Example Film"),
                "workTmdb": value("42"),
            },
            {
                "type": value("won"),
                "award": value("http://www.wikidata.org/entity/Q100"),
                "awardLabel": value("Example Award"),
                "time": value("+2025-00-00T00:00:00Z"),
                "work": value("http://www.wikidata.org/entity/Q200"),
                "workLabel": value("Example Film"),
                "workTmdb": value("42"),
            },
        ]

        awards = wikidata_awards._normalize_rows(rows)
        groups = wikidata_awards.group_awards(awards)

        self.assertEqual(len(awards), 1)
        self.assertEqual(awards[0]["result"], "won")
        self.assertEqual(awards[0]["workTmdbId"], 42)
        self.assertEqual(groups[0]["wins"], 1)
        self.assertEqual(groups[0]["nominations"], 0)


if __name__ == "__main__":
    unittest.main()
