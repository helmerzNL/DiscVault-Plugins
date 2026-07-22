from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = REPO_ROOT / "plugins" / "movievault_v2"
spec = importlib.util.spec_from_file_location("movievault_v2_plugin", PLUGIN_DIR / "plugin.py")
plugin = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(plugin)

BARCODE = "4006381333931"
BARCODE_HASH = hashlib.sha256(BARCODE.encode("ascii")).hexdigest()

RELEASE = {
    "recordType": "release",
    "releaseId": "10000000-0000-0000-0000-000000000001",
    "filmId": "20000000-0000-0000-0000-000000000001",
    "canonicalTitle": "Example Film",
    "releaseYear": 2024,
    "providerIds": {"tmdb": "42"},
    "releaseTitle": "Example Film",
    "edition": "Theatrical",
    "format": "4K UHD",
    "region": "B",
    "discCount": 1,
    "revision": 40,
}

BOX_SET = {
    "recordType": "box_set",
    "boxSetId": "30000000-0000-0000-0000-000000000001",
    "title": "Example Collection",
    "edition": "Collector's Edition",
    "format": "Mixed",
    "members": [
        {
            "position": 1,
            "releaseId": "10000000-0000-0000-0000-000000000001",
            "filmId": "20000000-0000-0000-0000-000000000001",
            "canonicalTitle": "Example Film",
            "releaseTitle": "Example Film",
            "releaseEdition": "Theatrical",
            "format": "4K UHD",
            "region": "B",
            "relationship": "contains",
            "discNumber": 1,
        },
        {
            "position": 2,
            "releaseId": "10000000-0000-0000-0000-000000000002",
            "filmId": "20000000-0000-0000-0000-000000000001",
            "canonicalTitle": "Example Film",
            "releaseTitle": "Example Film",
            "releaseEdition": "Director's Cut",
            "format": "Blu-ray",
            "region": "B",
            "relationship": "contains",
            "discNumber": 2,
        },
    ],
    "revision": 42,
}

EXTERNAL_RELEASE_DETAILS = {
    "contractVersion": "release-technical-1",
    "status": "external_hit",
    "verificationStatus": "unreviewed_external",
    "film": {
        "title": "Example Film",
        "year": 2024,
        "identifiers": {
            "tmdbMovieId": "123",
            "imdbId": "tt1234567",
        },
        "links": {
            "tmdb": "https://www.themoviedb.org/movie/123",
            "imdb": "https://www.imdb.com/title/tt1234567/",
        },
    },
    "release": {
        "barcodes": [
            {
                "type": "ean13",
                "value": BARCODE,
                "scope": "package",
            }
        ],
        "title": "Example Film - Collector's Edition",
        "format": "4K UHD",
        "edition": "SteelBook",
        "discCount": 2,
        "regions": ["B"],
        "packaging": ["steelbook"],
        "video": {
            "resolution": "2160p",
            "codecs": ["hevc"],
            "hdrFormats": ["dolby_vision"],
            "aspectRatios": ["2.39:1"],
        },
        "audioTracks": [
            {
                "languageCode": "en",
                "codec": "dolby_truehd",
                "channels": "7.1",
                "immersiveFormat": "dolby_atmos",
            }
        ],
        "subtitleLanguages": ["en", "nl"],
    },
    "moderation": {
        "candidateId": "discovery_abcdefghijkl",
        "status": "pending",
    },
}


class MovieVaultV2PluginTests(unittest.TestCase):
    def test_manifest_is_independent_and_secret_free(self):
        manifest = json.loads((PLUGIN_DIR / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["id"], "movievault_v2")
        self.assertEqual(manifest["discVaultPluginApi"], "next-1")
        self.assertEqual(manifest["categories"], ["metadata_source"])
        self.assertFalse(manifest["requiresSecrets"])
        self.assertEqual(manifest["settingsSchema"]["secrets"], [])
        self.assertNotIn("replacesPlugins", manifest)
        self.assertNotIn("receive_metadata", manifest["capabilities"])
        settings = {
            item["name"]: item
            for item in manifest["settingsSchema"]["settings"]
        }
        self.assertEqual(set(settings), {"origin"})
        self.assertEqual(settings["origin"]["default"], "https://movies2.vaultstack.eu")
        self.assertEqual(settings["origin"]["type"], "url")

    def test_manifest_declares_distribution_4_range_and_minimum_core(self):
        manifest = json.loads((PLUGIN_DIR / "manifest.json").read_text(encoding="utf-8"))
        contract_range = manifest["distributionContractRange"]
        self.assertEqual(set(contract_range), {"minimum", "maximum"})
        self.assertEqual(contract_range["minimum"], "distribution-2")
        self.assertEqual(contract_range["maximum"], "distribution-4")
        self.assertEqual(manifest["minimumDiscVaultVersion"], "26.5.10")

    def test_missing_core_bridge_is_explicit(self):
        for function, payload in (
            (plugin.health_check, None),
            (plugin.sync_index, {}),
            (plugin.search_barcode, {"barcode": BARCODE}),
            (plugin.search_title, {"title": "Example"}),
            (plugin.movie_details, {"releaseId": RELEASE["releaseId"]}),
            (plugin.box_set_candidates, {"barcode": BARCODE}),
        ):
            with self.subTest(function=function.__name__):
                if payload is None:
                    result = function({})
                else:
                    result = function(payload, {})
                self.assertEqual(result["reason"], "core_bridge_unavailable")

    def test_barcode_hit_is_local_and_does_not_use_bucket_fallback(self):
        calls = []

        def local_lookup(request):
            calls.append(("local", request))
            return {"state": "current", "results": [RELEASE, BOX_SET]}

        def bucket_lookup(request):
            calls.append(("bucket", request))
            return {"results": []}

        result = plugin.search_barcode(
            {"barcode": "4006-3813 33931"},
            {
                "settings": {"bucketFallback": True},
                "movievaultV2Lookup": local_lookup,
                "movievaultV2BucketLookup": bucket_lookup,
            },
        )

        self.assertEqual(result["status"], "hit")
        self.assertEqual(result["releaseId"], RELEASE["releaseId"])
        self.assertEqual(result["edition"], "Theatrical")
        self.assertEqual(calls, [("local", {"kind": "barcode", "hash": BARCODE_HASH, "limit": 12})])

    def test_bucket_fallback_is_disabled_by_default(self):
        bucket_calls = []
        release_calls = []
        context = {
            "settings": {},
            "movievaultV2Lookup": lambda _request: {"state": "current", "results": []},
            "movievaultV2BucketLookup": lambda request: bucket_calls.append(request) or {"results": [RELEASE]},
            "movievaultV2ReleaseDetails": lambda request: (
                release_calls.append(request)
                or {"contractVersion": "release-technical-1", "status": "miss"}
            ),
        }

        result = plugin.search_barcode({"barcode": BARCODE}, context)

        self.assertEqual(result["status"], "miss")
        self.assertEqual(bucket_calls, [])
        self.assertEqual(release_calls, [{"barcode": BARCODE}])

    def test_enabled_bucket_fallback_filters_through_core_callback(self):
        context = {
            "settings": {"bucketFallback": True},
            "movievaultV2Lookup": lambda _request: {"state": "current", "results": []},
            "movievaultV2BucketLookup": lambda request: {"state": "remote_bucket", "results": [RELEASE]},
        }

        result = plugin.search_barcode({"barcode": BARCODE}, context)

        self.assertEqual(result["status"], "hit")
        self.assertEqual(result["releaseId"], RELEASE["releaseId"])

    def test_technical_fallback_runs_automatically_after_local_miss(self):
        calls = []
        context = {
            "settings": {},
            "movievaultV2Lookup": lambda _request: {"state": "current", "results": []},
            "movievaultV2ReleaseDetails": lambda request: (
                calls.append(request) or {"contractVersion": "release-technical-1", "status": "miss"}
            ),
        }

        result = plugin.search_barcode({"barcode": BARCODE}, context)

        self.assertEqual(result["status"], "miss")
        self.assertEqual(calls, [{"barcode": BARCODE}])

    def test_local_and_bucket_hits_do_not_invoke_technical_fallback(self):
        release_calls = []
        local_context = {
            "settings": {},
            "movievaultV2Lookup": lambda _request: {"state": "current", "results": [RELEASE]},
            "movievaultV2ReleaseDetails": lambda request: release_calls.append(request),
        }
        bucket_context = {
            "settings": {"bucketFallback": True},
            "movievaultV2Lookup": lambda _request: {"state": "current", "results": []},
            "movievaultV2BucketLookup": lambda _request: {
                "state": "remote_bucket",
                "results": [RELEASE],
            },
            "movievaultV2ReleaseDetails": lambda request: release_calls.append(request),
        }

        local = plugin.search_barcode({"barcode": BARCODE}, local_context)
        bucket = plugin.search_barcode({"barcode": BARCODE}, bucket_context)

        self.assertEqual(local["status"], "hit")
        self.assertEqual(bucket["status"], "hit")
        self.assertEqual(release_calls, [])

    def test_automatic_technical_fallback_maps_external_hit_as_unreviewed(self):
        calls = []
        context = {
            "settings": {},
            "movievaultV2Lookup": lambda _request: {"state": "current", "results": []},
            "movievaultV2ReleaseDetails": lambda request: (
                calls.append(request) or EXTERNAL_RELEASE_DETAILS
            ),
        }

        result = plugin.search_barcode(
            {
                "barcode": "4006-3813 33931",
                "title": "  Example   Film ",
                "year": "2024",
                "format": "4K UHD",
            },
            context,
        )

        self.assertEqual(
            calls,
            [
                {
                    "barcode": BARCODE,
                    "title": "Example Film",
                    "year": 2024,
                    "format": "4K UHD",
                }
            ],
        )
        self.assertEqual(result["status"], "unreviewed_external")
        self.assertEqual(result["verificationStatus"], "unreviewed_external")
        self.assertTrue(result["requiresReview"])
        self.assertEqual(result["moderationCandidateId"], "discovery_abcdefghijkl")
        self.assertEqual(result["identifiers"], {"tmdbId": "123", "imdbId": "tt1234567"})
        self.assertNotIn("sourceUrl", result)
        self.assertNotIn("description", result)

    def test_technical_fallback_maps_stable_failure_without_provider_data(self):
        context = {
            "settings": {},
            "movievaultV2Lookup": lambda _request: {"state": "current", "results": []},
            "movievaultV2ReleaseDetails": lambda _request: {
                "contractVersion": "release-technical-1",
                "status": "failed",
                "errorCode": "release_details_rate_limited",
            },
        }

        result = plugin.search_barcode({"barcode": BARCODE}, context)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "release_details_rate_limited")
        self.assertEqual(result["items"], [])

    def test_technical_fallback_maps_box_set_for_existing_review_flow(self):
        response = json.loads(json.dumps(EXTERNAL_RELEASE_DETAILS))
        response["boxSet"] = {
            "state": "explicit",
            "title": "Example Collection",
            "format": "4K UHD",
            "members": [
                {
                    "position": 1,
                    "title": "Example Film",
                    "year": 2024,
                    "discNumber": 1,
                    "discFormat": "4K UHD",
                    "identifiers": {
                        "tmdbMovieId": "123",
                        "imdbId": "tt1234567",
                    },
                },
                {
                    "position": 2,
                    "title": "Example Film Two",
                    "discNumber": 2,
                    "discFormat": "Blu-ray",
                    "identifiers": {
                        "tmdbMovieId": "456",
                        "imdbId": "tt7654321",
                    },
                },
            ],
        }
        context = {
            "movievaultV2Lookup": lambda _request: {"state": "current", "results": []},
            "movievaultV2ReleaseDetails": lambda _request: response,
        }

        result = plugin.search_barcode({"barcode": BARCODE}, context)

        self.assertTrue(result["isBoxSet"])
        self.assertTrue(result["isBoxSetCandidate"])
        proposal = result["boxSetProposal"]
        self.assertEqual(proposal["memberConfidence"], "needs_member_confirmation")
        self.assertEqual(
            [member["position"] for member in proposal["members"]],
            [1, 2],
        )

    def test_box_set_candidates_preserve_exact_release_editions(self):
        context = {
            "movievaultV2Lookup": lambda _request: {
                "state": "current",
                "results": [RELEASE, BOX_SET],
            }
        }

        result = plugin.box_set_candidates({"barcode": BARCODE}, context)

        self.assertEqual(result["status"], "hit")
        members = result["boxSetProposal"]["members"]
        self.assertEqual([member["position"] for member in members], [1, 2])
        self.assertEqual(
            [member["releaseEdition"] for member in members],
            ["Theatrical", "Director's Cut"],
        )
        self.assertEqual(members[0]["filmId"], members[1]["filmId"])
        self.assertNotEqual(members[0]["releaseId"], members[1]["releaseId"])

    def test_local_authenticated_poster_url_passes_through_when_present(self):
        # DiscVault core resolves "posterUrl" itself (a local, authenticated
        # asset route) only once a rights-approved primary poster has been
        # cached from a distribution-4 sync. The plugin must forward it
        # unchanged and must never fabricate or contact MovieVault for it.
        release_with_poster = {
            **RELEASE,
            "posterUrl": "/api/next/media/assets/40000000-0000-0000-0000-000000000001",
        }
        box_set_with_poster = {
            **BOX_SET,
            "posterUrl": "/api/next/media/assets/40000000-0000-0000-0000-000000000002",
        }
        context = {
            "movievaultV2Lookup": lambda _request: {
                "state": "current",
                "results": [release_with_poster, box_set_with_poster],
            }
        }

        release_result = plugin.movie_details({"releaseId": RELEASE["releaseId"]}, context)
        barcode_result = plugin.search_barcode({"barcode": BARCODE}, context)

        self.assertEqual(
            release_result["posterUrl"],
            "/api/next/media/assets/40000000-0000-0000-0000-000000000001",
        )
        self.assertEqual(
            release_result["movie"]["posterUrl"],
            "/api/next/media/assets/40000000-0000-0000-0000-000000000001",
        )
        self.assertTrue(release_result["posterUrl"].startswith("/"))
        self.assertNotIn("movies2.vaultstack.eu", release_result["posterUrl"])
        self.assertEqual(barcode_result["posterUrl"], release_result["posterUrl"])

    def test_poster_url_is_absent_without_a_negotiated_v4_contract(self):
        # v2/v3 records never carry "posterUrl"; the plugin must not invent
        # one, so the key stays entirely absent from the response.
        context = {
            "movievaultV2Lookup": lambda _request: {
                "state": "current",
                "results": [RELEASE, BOX_SET],
            }
        }

        release_result = plugin.movie_details({"releaseId": RELEASE["releaseId"]}, context)
        box_set_result = plugin.search_title({"title": "Example Collection"}, context)

        self.assertNotIn("posterUrl", release_result)
        self.assertFalse(release_result["movie"].get("posterUrl"))
        for item in box_set_result["items"]:
            self.assertNotIn("posterUrl", item)

    def test_title_and_exact_release_details_use_local_callback(self):
        requests = []

        def lookup(request):
            requests.append(request)
            return {"state": "current", "results": [RELEASE]}

        context = {"movievaultV2Lookup": lookup}
        title_result = plugin.search_title({"title": "Example", "year": "2024"}, context)
        detail_result = plugin.movie_details({"releaseId": RELEASE["releaseId"]}, context)

        self.assertEqual(title_result["items"][0]["title"], "Example Film")
        self.assertEqual(detail_result["release"]["edition"], "Theatrical")
        self.assertEqual(requests[0], {"kind": "title", "query": "Example", "limit": 12})
        self.assertEqual(
            requests[1],
            {"kind": "release", "releaseId": RELEASE["releaseId"], "limit": 1},
        )

    def test_health_and_sync_return_sanitized_core_state(self):
        context = {
            "movievaultV2Status": lambda _request: {
                "state": "stale",
                "revision": 42,
                "lastSuccessAt": "2026-07-15T10:00:00+00:00",
                "lastAttemptAt": "2026-07-15T12:00:00+00:00",
                "errorCode": None,
            },
            "movievaultV2Sync": lambda _request: {
                "state": "current",
                "mode": "delta",
                "revision": 43,
                "recordsApplied": 1,
            },
        }

        health = plugin.health_check(context)
        sync = plugin.sync_index({}, context)

        self.assertEqual(health["status"], "degraded")
        self.assertEqual(health["state"], "stale")
        self.assertEqual(sync["status"], "completed")
        self.assertEqual(sync["revision"], 43)

    def test_plugin_has_no_network_database_or_discvault_imports(self):
        source = (PLUGIN_DIR / "plugin.py").read_text(encoding="utf-8")
        for forbidden in ("requests", "urllib", "psycopg", "sqlite", "next_", "app.backend"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
