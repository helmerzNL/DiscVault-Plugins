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
        context = {
            "settings": {},
            "movievaultV2Lookup": lambda _request: {"state": "current", "results": []},
            "movievaultV2BucketLookup": lambda request: bucket_calls.append(request) or {"results": [RELEASE]},
        }

        result = plugin.search_barcode({"barcode": BARCODE}, context)

        self.assertEqual(result["status"], "miss")
        self.assertEqual(bucket_calls, [])

    def test_enabled_bucket_fallback_filters_through_core_callback(self):
        context = {
            "settings": {"bucketFallback": True},
            "movievaultV2Lookup": lambda _request: {"state": "current", "results": []},
            "movievaultV2BucketLookup": lambda request: {"state": "remote_bucket", "results": [RELEASE]},
        }

        result = plugin.search_barcode({"barcode": BARCODE}, context)

        self.assertEqual(result["status"], "hit")
        self.assertEqual(result["releaseId"], RELEASE["releaseId"])

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
