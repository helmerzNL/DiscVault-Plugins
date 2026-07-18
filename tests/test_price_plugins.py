from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "plugins"
EXPECTED_VERSIONS = {
    "amazon": "1.0.1",
    "arrow": "1.0.1",
    "bol": "1.0.1",
    "keepa": "1.0.1",
    "priceapi": "1.0.1",
    "zavvi": "1.0.1",
}
SECRET_PLUGINS = {"keepa", "priceapi"}


def load_plugin(name: str):
    spec = importlib.util.spec_from_file_location(
        f"price_plugin_{name}",
        PLUGIN_ROOT / name / "plugin.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


PLUGINS = {name: load_plugin(name) for name in EXPECTED_VERSIONS}


class FakeResponse:
    def __init__(self, *, text: str = "", data=None):
        self.text = text
        self._data = data
        self.content = b"json" if data is not None else b""

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


class PricePluginTests(unittest.TestCase):
    def test_manifests_declare_price_provider_contract(self):
        for name, version in EXPECTED_VERSIONS.items():
            with self.subTest(plugin=name):
                manifest = json.loads(
                    (PLUGIN_ROOT / name / "manifest.json").read_text(encoding="utf-8")
                )
                self.assertEqual(manifest["id"], name)
                self.assertEqual(manifest["version"], version)
                self.assertEqual(manifest["discVaultPluginApi"], "next-1")
                self.assertEqual(manifest["minimumDiscVaultVersion"], "26.4.63")
                self.assertEqual(manifest["categories"], ["price_provider"])
                self.assertEqual(manifest["capabilities"], ["price_check"])
                self.assertEqual(manifest["requiresSecrets"], name in SECRET_PLUGINS)

                secrets = manifest["settingsSchema"].get("secrets", [])
                if name in SECRET_PLUGINS:
                    self.assertEqual(
                        [(secret["name"], secret["required"]) for secret in secrets],
                        [("apiKey", True)],
                    )
                else:
                    self.assertEqual(secrets, [])

    def test_health_checks_report_configuration_state_without_network(self):
        for name, module in PLUGINS.items():
            with self.subTest(plugin=name):
                with patch.object(
                    module.requests,
                    "request",
                    side_effect=AssertionError("health_check must not access the network"),
                ):
                    result = module.health_check({})
                    expected = (
                        "needs_configuration"
                        if name in SECRET_PLUGINS
                        else "available"
                    )
                    self.assertEqual(result["status"], expected)

                    if name in SECRET_PLUGINS:
                        configured = module.health_check(
                            {"secrets": {"apiKey": "live_key"}}
                        )
                        self.assertEqual(configured["status"], "available")

    def test_page_providers_parse_mocked_prices_and_errors(self):
        cases = {
            "amazon": {
                "payload": {"providerProductRef": "B012345678"},
                "html": '<span class="a-offscreen">EUR 24,95</span>',
                "price": 24.95,
                "currency": "EUR",
                "error_html": "<html>robot check</html>",
            },
            "arrow": {
                "payload": {"url": "https://www.arrowfilms.com/item/1"},
                "html": (
                    '<script type="application/ld+json">'
                    '{"offers":{"price":"18.50","priceCurrency":"GBP"}}'
                    "</script>"
                ),
                "price": 18.5,
                "currency": "GBP",
                "error_html": "<html>No product price</html>",
            },
            "bol": {
                "payload": {"url": "https://www.bol.com/nl/nl/p/item/1"},
                "html": (
                    '<meta content="29.99" property="product:price:amount">'
                    '<meta content="EUR" property="product:price:currency">'
                ),
                "price": 29.99,
                "currency": "EUR",
                "error_html": "<html>No product price</html>",
            },
            "zavvi": {
                "payload": {"url": "https://www.zavvi.com/item/1"},
                "html": "<div>Now £17.99</div>",
                "price": 17.99,
                "currency": "GBP",
                "error_html": "<html>No product price</html>",
            },
        }

        for name, case in cases.items():
            module = PLUGINS[name]
            with self.subTest(plugin=name, result="success"):
                with patch.object(
                    module.requests,
                    "get",
                    return_value=FakeResponse(text=case["html"]),
                ) as request:
                    result = module.price_check(case["payload"], {})
                self.assertEqual(result["status"], "ok")
                self.assertEqual(result["price"], case["price"])
                self.assertEqual(result["currency"], case["currency"])
                request.assert_called_once()

            with self.subTest(plugin=name, result="error"):
                with patch.object(
                    module.requests,
                    "get",
                    return_value=FakeResponse(text=case["error_html"]),
                ):
                    result = module.price_check(case["payload"], {})
                self.assertEqual(result["status"], "no_match")
                self.assertIn("error", result)

    def test_keepa_parses_mocked_success_and_error_responses(self):
        module = PLUGINS["keepa"]
        payload = {"providerProductRef": "B012345678"}
        context = {"secrets": {"apiKey": "live_key"}, "settings": {"domainId": "3"}}

        with patch.object(
            module.requests,
            "get",
            return_value=FakeResponse(data={"products": [{"buyBoxPrice": 1999}]}),
        ) as request:
            result = module.price_check(payload, context)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["price"], 19.99)
        self.assertEqual(result["providerProductRef"], "B012345678")
        self.assertEqual(request.call_args.kwargs["params"]["domain"], 3)

        with patch.object(
            module.requests,
            "get",
            return_value=FakeResponse(data={"products": [{}]}),
        ):
            error = module.price_check(payload, context)
        self.assertEqual(error["status"], "no_match")
        self.assertIn("usable current price", error["error"])

    def test_priceapi_parses_mocked_success_and_error_responses(self):
        module = PLUGINS["priceapi"]
        payload = {"providerProductRef": "retailer-item-42"}
        context = {
            "secrets": {"apiKey": "live_key"},
            "settings": {"country": "de"},
        }

        with patch.object(
            module.requests,
            "post",
            return_value=FakeResponse(
                data={
                    "result": {
                        "offers": [
                            {"current_price": "1.234,56", "currency": "EUR"}
                        ]
                    }
                }
            ),
        ) as request:
            result = module.price_check(payload, context)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["price"], 1234.56)
        self.assertEqual(result["currency"], "EUR")
        self.assertEqual(request.call_args.kwargs["json"]["country"], "de")
        self.assertEqual(
            request.call_args.kwargs["headers"]["Authorization"],
            "Bearer live_key",
        )

        with patch.object(
            module.requests,
            "post",
            return_value=FakeResponse(data={"result": {"offers": []}}),
        ):
            error = module.price_check(payload, context)
        self.assertEqual(error["status"], "no_match")
        self.assertIn("usable current price", error["error"])

    def test_required_secrets_block_requests_when_missing(self):
        cases = {
            "keepa": ("get", {"providerProductRef": "B012345678"}),
            "priceapi": ("post", {"providerProductRef": "retailer-item-42"}),
        }
        for name, (method, payload) in cases.items():
            module = PLUGINS[name]
            with self.subTest(plugin=name):
                with patch.object(module.requests, method) as request:
                    result = module.price_check(payload, {})
                self.assertEqual(result["status"], "not_configured")
                request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
