from __future__ import annotations

from xml.etree import ElementTree as ET
import unittest
from unittest.mock import patch

from test_ported_plugins import load_plugin


class BranchPluginCompatibilityTests(unittest.TestCase):
    def test_barcode_hub_next_1_pure_behavior(self):
        plugin = load_plugin("barcode_hub")

        first = plugin._item(
            data_source="upcitemdb",
            source_label="UPCItemDB",
            title="Example Film [Blu-ray]",
            barcode="4006381333931",
        )
        second = plugin._item(
            data_source="go_upc",
            source_label="Go-UPC",
            title="Example Film",
            barcode="4006381333931",
            brand="Example Studio",
        )
        merged = plugin._merge_items([first, second])

        self.assertEqual(plugin.search_barcode({}, {})["status"], "skipped")
        self.assertEqual(plugin.health_check({})["status"], "available")
        self.assertEqual(merged[0]["cleanTitle"], "Example Film")
        self.assertEqual(merged[0]["detectedFormat"], "Blu-ray")
        self.assertEqual(merged[0]["dataSources"], ["upcitemdb", "go_upc"])

    def test_dvd_fr_next_1_xml_normalization(self):
        plugin = load_plugin("dvd_fr")
        root = ET.fromstring(
            "<dvd>"
            "<id>42</id><titres><fr>Le Film</fr><vo>The Film</vo></titres>"
            "<media>DVD</media><ean>4006381333931</ean><duree>123 min</duree>"
            "<zones><zone>2</zone></zones><disques><disque>DVD-9</disque></disques>"
            "<image><standard>PAL</standard><aspect_ratio>2.35:1</aspect_ratio></image>"
            "</dvd>"
        )

        result = plugin._build_detail(root)

        self.assertEqual(plugin.search_title({}, {})["status"], "skipped")
        self.assertEqual(result["status"], "hit")
        self.assertEqual(result["movie"]["runtimeMinutes"], 123)
        self.assertEqual(result["technicalSpecs"]["regions"], ["2"])
        self.assertEqual(result["technicalSpecs"]["videoStandard"], "PAL")

    def test_wikidata_next_1_cross_id_normalization(self):
        plugin = load_plugin("wikidata")
        binding = {
            "label": {"value": "Example Film"},
            "year": {"value": "2024"},
            "runtime": {"value": "118"},
            "imdbId": {"value": "tt1234567"},
            "tmdbId": {"value": "42"},
            "directors": {"value": "Example Director"},
        }

        with patch.object(plugin, "_sparql", return_value=[binding]):
            result = plugin._build_detail("Q42", "en")

        self.assertEqual(plugin.search_title({}, {})["status"], "skipped")
        self.assertEqual(plugin._language({"settings": {"language": "INVALID!"}}), "en")
        self.assertEqual(result["status"], "hit")
        self.assertEqual(result["wikidataId"], "Q42")
        self.assertEqual(result["crossIds"]["imdbId"], "tt1234567")
        self.assertEqual(result["movie"]["runtimeMinutes"], 118)


if __name__ == "__main__":
    unittest.main()
