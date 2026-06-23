import re

import requests

UPCITEMDB_URL = "https://api.upcitemdb.com/prod/trial/lookup"
GO_UPC_URL = "https://go-upc.com/search"
EAN_SEARCH_URL = "https://api.ean-search.org/api"
BARCODELOOKUP_URL = "https://api.barcodelookup.com/v3/products"

PROVIDER_ID = "barcode_hub"
PROVIDER_LABEL = "Barcode Hub"

_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

_FORMAT_TOKENS = re.compile(
    r"\s*[\[(]?\s*(?:4k(?:\s*ultra)?\s*hd|ultra\s*hd|uhd|blu[- ]?ray|bd|dvd|vhs)\s*[\])]?",
    flags=re.I,
)


def _settings(context):
    return (context or {}).get("settings") or {}


def _secrets(context):
    return (context or {}).get("secrets") or {}


def _ean_search_token(context):
    secrets = _secrets(context)
    return str(secrets.get("eanSearchToken") or secrets.get("ean_search_token") or "").strip()


def _barcodelookup_key(context):
    secrets = _secrets(context)
    return str(secrets.get("barcodeLookupKey") or secrets.get("barcodelookup_key") or "").strip()


def _detect_format(value):
    text = str(value or "").lower()
    if re.search(r"4k|uhd|ultra[\s-]*hd", text):
        return "4K UHD"
    if re.search(r"blu[- ]?rays?\b", text):
        return "Blu-ray"
    if re.search(r"\bdvds?\b", text):
        return "DVD"
    return ""


def _clean_title(value):
    text = str(value or "").strip()
    text = _FORMAT_TOKENS.sub(" ", text)
    text = re.sub(r"\bdirected by\b.*$", "", text, flags=re.I)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip(" -:[](){}")


def _item(*, data_source, source_label, title, barcode, brand="", category="", source_url="", image_url="", country=""):
    title = str(title or "").strip()
    return {
        "provider": PROVIDER_ID,
        "providerLabel": PROVIDER_LABEL,
        "dataSource": data_source,
        "dataSourceLabel": source_label,
        "title": title,
        "cleanTitle": _clean_title(title),
        "barcode": barcode,
        "detectedFormat": _detect_format(title),
        "brand": brand or "",
        "category": category or "",
        "sourceUrl": source_url or "",
        "imageUrl": image_url or "",
        "country": country or "",
    }


def _query_upcitemdb(barcode):
    response = requests.get(UPCITEMDB_URL, params={"upc": barcode}, timeout=8)
    response.raise_for_status()
    items = response.json().get("items") or []
    results = []
    for item in items[:5]:
        images = item.get("images")
        results.append(
            _item(
                data_source="upcitemdb",
                source_label="UPCItemDB",
                title=item.get("title"),
                barcode=barcode,
                brand=item.get("brand"),
                category=item.get("category"),
                source_url=item.get("detailPageURL"),
                image_url=(images[0] if isinstance(images, list) and images else ""),
            )
        )
    return results


def _html_unescape(value):
    return (
        str(value or "")
        .replace("&amp;", "&")
        .replace("&#39;", "'")
        .replace("&quot;", '"')
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .strip()
    )


def _query_go_upc(barcode):
    response = requests.get(
        GO_UPC_URL, params={"q": barcode}, headers=_BROWSER_HEADERS, timeout=12
    )
    response.raise_for_status()
    html = response.text
    name_match = re.search(r'<h1[^>]*class="product-name"[^>]*>(.*?)</h1>', html, re.I | re.S)
    if not name_match:
        return []
    name = _html_unescape(re.sub(r"<[^>]+>", "", name_match.group(1)))
    if not name or name.lower() == "product not found":
        return []
    meta = {}
    for row in re.finditer(
        r'<td[^>]*class="metadata-label"[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>', html, re.I | re.S
    ):
        label = _html_unescape(re.sub(r"<[^>]+>", "", row.group(1))).lower()
        value = _html_unescape(re.sub(r"<[^>]+>", "", row.group(2)))
        if label:
            meta[label] = value
    image_match = re.search(r'<img[^>]+src="(https://go-upc\.s3\.amazonaws\.com/images/[^"]+)"', html, re.I)
    category = meta.get("category", "")
    item = _item(
        data_source="go_upc",
        source_label="Go-UPC",
        title=name,
        barcode=barcode,
        brand=meta.get("brand"),
        category=category,
        source_url=f"https://go-upc.com/search?q={barcode}",
        image_url=image_match.group(1) if image_match else "",
    )
    if not item["detectedFormat"]:
        item["detectedFormat"] = _detect_format(category)
    return [item]


def _query_ean_search(barcode, token):
    key = "upc" if len(re.sub(r"\D", "", barcode)) == 12 else "ean"
    response = requests.get(
        EAN_SEARCH_URL,
        params={"op": "barcode-lookup", "format": "json", "token": token, key: barcode},
        timeout=8,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        return []
    results = []
    for entry in payload:
        if not isinstance(entry, dict) or entry.get("error"):
            continue
        name = entry.get("name")
        if not name or str(name).strip().lower() == "barcode not found":
            continue
        results.append(
            _item(
                data_source="ean_search",
                source_label="EAN-Search",
                title=name,
                barcode=barcode,
                category=entry.get("categoryName"),
                country=entry.get("issuingCountry"),
            )
        )
    return results


def _query_barcodelookup(barcode, key):
    response = requests.get(
        BARCODELOOKUP_URL,
        params={"barcode": barcode, "formatted": "y", "key": key},
        timeout=8,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        return []
    results = []
    for product in payload.get("products") or []:
        if not isinstance(product, dict):
            continue
        images = product.get("images")
        stores = product.get("stores")
        results.append(
            _item(
                data_source="barcodelookup",
                source_label="Barcode Lookup",
                title=product.get("product_name"),
                barcode=product.get("barcode_number") or barcode,
                brand=product.get("brand") or product.get("manufacturer"),
                category=product.get("category"),
                source_url=(stores[0].get("product_url") if isinstance(stores, list) and stores and isinstance(stores[0], dict) else ""),
                image_url=(images[0] if isinstance(images, list) and images else ""),
            )
        )
    return results


_SOURCE_PRIORITY = {"upcitemdb": 0, "go_upc": 1, "ean_search": 2, "barcodelookup": 3}


def _merge_items(items):
    merged = {}
    order = []
    for item in items:
        key = (item.get("cleanTitle") or item.get("title") or "").strip().lower()
        if not key:
            continue
        if key not in merged:
            entry = dict(item)
            entry["dataSources"] = [item["dataSource"]]
            merged[key] = entry
            order.append(key)
            continue
        existing = merged[key]
        if item["dataSource"] not in existing["dataSources"]:
            existing["dataSources"].append(item["dataSource"])
        for field in ("brand", "category", "sourceUrl", "imageUrl", "country"):
            if not existing.get(field) and item.get(field):
                existing[field] = item[field]
        if not existing.get("detectedFormat") and item.get("detectedFormat"):
            existing["detectedFormat"] = item["detectedFormat"]
    result = [merged[key] for key in order]
    result.sort(
        key=lambda it: (
            0 if it.get("detectedFormat") else 1,
            min(_SOURCE_PRIORITY.get(src, 9) for src in it.get("dataSources") or [it.get("dataSource")]),
        )
    )
    return result


def _provider_status(context):
    return {
        "upcitemdb": True,
        "go_upc": True,
        "ean_search": bool(_ean_search_token(context)),
        "barcodelookup": bool(_barcodelookup_key(context)),
    }


def health_check(context=None):
    configured = _provider_status(context or {})
    enabled = [name for name, on in configured.items() if on]
    optional = [name for name in ("ean_search", "barcodelookup") if not configured[name]]
    message = "Barcode Hub ready via: " + ", ".join(enabled) + "."
    if optional:
        message += " Optional sources not configured: " + ", ".join(optional) + "."
    return {"status": "available", "message": message, "providers": configured}


def search_barcode(payload, context=None):
    context = context or {}
    barcode = str((payload or {}).get("barcode") or "").strip()
    if not barcode:
        return {"status": "skipped", "provider": PROVIDER_ID, "items": []}

    token = _ean_search_token(context)
    blk = _barcodelookup_key(context)

    providers = [
        ("upcitemdb", lambda: _query_upcitemdb(barcode)),
        ("go_upc", lambda: _query_go_upc(barcode)),
    ]
    if token:
        providers.append(("ean_search", lambda: _query_ean_search(barcode, token)))
    if blk:
        providers.append(("barcodelookup", lambda: _query_barcodelookup(barcode, blk)))

    collected = []
    queried = []
    errors = []
    for name, run in providers:
        queried.append(name)
        try:
            collected.extend(run())
        except Exception as exc:  # one provider failing must not break the others
            errors.append({"provider": name, "error": str(exc)})

    items = _merge_items(collected)
    if not items:
        return {
            "status": "miss",
            "provider": PROVIDER_ID,
            "sourceLabel": PROVIDER_LABEL,
            "barcode": barcode,
            "items": [],
            "providersQueried": queried,
            "errors": errors,
        }

    first = items[0]
    return {
        "status": "hit",
        "provider": PROVIDER_ID,
        "sourceLabel": PROVIDER_LABEL,
        "sourceRef": first.get("sourceUrl") or "",
        "barcode": barcode,
        "items": items,
        "providersQueried": queried,
        "errors": errors,
        "movie": {
            "title": first.get("cleanTitle") or first.get("title") or "",
            "format": first.get("detectedFormat") or "",
        },
    }
