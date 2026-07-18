"""Wikidata metadata source plug-in.

Wikidata is a free, CC0-licensed knowledge graph. For DiscVault it is most valuable
as an **identity / cross-ID hub**: from a title or an external id (IMDb / TMDb) it
resolves a stable Wikidata item (QID) and returns links to many other databases
(IMDb, TMDb, Rotten Tomatoes, Metacritic, AlloCine, OFDb, Letterboxd, FilmAffinity,
Kinopoisk, EIDR) plus structured facts (year, runtime, directors, cast, genres,
countries, franchise/series). It does NOT carry disc-level technical specs, so it
complements rather than replaces dvdfr / blu-ray.com.

No API key is required. Data is fetched from:
    - SPARQL endpoint:  https://query.wikidata.org/sparql
    - Search endpoint:  https://www.wikidata.org/w/api.php  (action=wbsearchentities)
"""

import re

import requests

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
API_ENDPOINT = "https://www.wikidata.org/w/api.php"
PROVIDER = "wikidata"
PROVIDER_LABEL = "Wikidata"
DEFAULT_LANGUAGE = "en"

# External identifier properties returned as the cross-ID hub. Wikidata property -> key.
EXTERNAL_IDS = (
    ("imdbId", "P345"),
    ("tmdbId", "P4947"),
    ("tmdbTvId", "P4983"),
    ("rottenTomatoesId", "P1258"),
    ("metacriticId", "P1712"),
    ("allocineId", "P1265"),
    ("ofdbId", "P3138"),
    ("letterboxdId", "P6127"),
    ("filmAffinityId", "P480"),
    ("kinopoiskId", "P2603"),
    ("eidrContentId", "P2704"),
)

# Multi-valued, label-resolved facts. Result key -> Wikidata property.
MULTI_FACTS = (
    ("directors", "P57"),
    ("genres", "P136"),
    ("cast", "P161"),
    ("countries", "P495"),
    ("series", "P179"),
)

_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def _headers():
    return {
        "User-Agent": "DiscVault-Next/1.0 (metadata source; +https://discvault.eu)",
        "Accept": "application/json",
    }


def _settings(context):
    return (context or {}).get("settings") or {}


def _language(context):
    raw = str(_settings(context).get("language") or DEFAULT_LANGUAGE).strip().lower()
    return raw if re.fullmatch(r"[a-z]{2,3}(-[a-z0-9]{2,8})?", raw) else DEFAULT_LANGUAGE


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _qid(value):
    match = re.search(r"(Q\d+)", str(value or ""))
    return match.group(1) if match else ""


def _is_qid(value):
    return bool(re.fullmatch(r"Q\d+", str(value or "").strip()))


def _sparql(query):
    response = requests.get(
        SPARQL_ENDPOINT,
        params={"query": query, "format": "json"},
        headers=_headers(),
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("results", {}).get("bindings", [])


def _api(**params):
    params.setdefault("format", "json")
    response = requests.get(API_ENDPOINT, params=params, headers=_headers(), timeout=20)
    response.raise_for_status()
    return response.json()


def _detail_query(qid, language):
    select = ["?item"]
    where = [f"  VALUES ?item {{ wd:{qid} }}"]

    for key, prop in EXTERNAL_IDS:
        select.append(f"  (SAMPLE(?{key}_r) AS ?{key})")
        where.append(f"  OPTIONAL {{ ?item wdt:{prop} ?{key}_r. }}")

    select.append("  (SAMPLE(?label_r) AS ?label)")
    select.append("  (SAMPLE(?labelEn_r) AS ?labelEn)")
    select.append("  (SAMPLE(?desc_r) AS ?description)")
    select.append("  (MIN(?year_r) AS ?year)")
    select.append("  (SAMPLE(?runtime_r) AS ?runtime)")
    select.append("  (SAMPLE(?origLang_r) AS ?originalLanguage)")
    for key, prop in MULTI_FACTS:
        select.append(f"  (GROUP_CONCAT(DISTINCT ?{key}Label; separator=\", \") AS ?{key})")

    where.append("  OPTIONAL { ?item wdt:P577 ?pub_r. BIND(YEAR(?pub_r) AS ?year_r) }")
    where.append("  OPTIONAL { ?item wdt:P2047 ?runtime_r. }")
    where.append(
        f"  OPTIONAL {{ ?item wdt:P364 ?ol_r. ?ol_r rdfs:label ?origLang_r. "
        f"FILTER(LANG(?origLang_r)=\"{language}\") }}"
    )
    for key, prop in MULTI_FACTS:
        where.append(
            f"  OPTIONAL {{ ?item wdt:{prop} ?{key}V. ?{key}V rdfs:label ?{key}Label. "
            f"FILTER(LANG(?{key}Label)=\"{language}\") }}"
        )
    where.append(f"  OPTIONAL {{ ?item rdfs:label ?label_r. FILTER(LANG(?label_r)=\"{language}\") }}")
    where.append("  OPTIONAL { ?item rdfs:label ?labelEn_r. FILTER(LANG(?labelEn_r)=\"en\") }")
    where.append(
        f"  OPTIONAL {{ ?item schema:description ?desc_r. FILTER(LANG(?desc_r)=\"{language}\") }}"
    )

    return (
        "SELECT\n"
        + "\n".join(select)
        + "\nWHERE {\n"
        + "\n".join(where)
        + "\n}\nGROUP BY ?item"
    )


def _val(binding, key):
    return _clean(binding.get(key, {}).get("value", ""))


def _runtime_minutes(value):
    match = re.search(r"\d+", str(value or ""))
    return int(match.group(0)) if match else None


def _build_detail(qid, language):
    bindings = _sparql(_detail_query(qid, language))
    if not bindings:
        return None
    row = bindings[0]

    identifiers = {"wikidataId": qid}
    for key, _prop in EXTERNAL_IDS:
        value = _val(row, key)
        if value:
            identifiers[key] = value

    title = _val(row, "label") or _val(row, "labelEn")
    if not title:
        return None

    movie = {
        "title": title,
        "year": _val(row, "year"),
        "runtimeMinutes": _runtime_minutes(_val(row, "runtime")),
        "language": _val(row, "originalLanguage"),
        "director": _val(row, "directors"),
        "actor": _val(row, "cast"),
        "genre": _val(row, "genres"),
        "country": _val(row, "countries"),
        "collection": _val(row, "series"),
        "description": _val(row, "description"),
    }

    return {
        "status": "hit",
        "provider": PROVIDER,
        "sourceLabel": PROVIDER_LABEL,
        "sourceRef": qid,
        "sourceUrl": f"https://www.wikidata.org/wiki/{qid}",
        "movie": movie,
        "identifiers": identifiers,
        "crossIds": identifiers,
        "wikidataId": qid,
        "imdbId": identifiers.get("imdbId", ""),
        "tmdbId": identifiers.get("tmdbId", ""),
    }


def _qid_by_external_id(prop, value):
    value = str(value or "").strip()
    if not value:
        return ""
    safe = value.replace("\\", "").replace('"', "")
    bindings = _sparql(f'SELECT ?item WHERE {{ ?item wdt:{prop} "{safe}". }} LIMIT 1')
    return _qid(bindings[0]["item"]["value"]) if bindings else ""


def _looks_like_film(description):
    text = str(description or "").lower()
    return "film" in text or "series" in text or "miniseries" in text


def _search_items(title, language):
    data = _api(
        action="wbsearchentities",
        search=title,
        language=language,
        uselang=language,
        type="item",
        limit=12,
    )
    items = []
    for entry in data.get("search", []):
        description = _clean(entry.get("description"))
        if not _looks_like_film(description):
            continue
        year_match = _YEAR_RE.search(description)
        items.append(
            {
                "provider": PROVIDER,
                "providerLabel": PROVIDER_LABEL,
                "id": entry.get("id") or "",
                "title": _clean(entry.get("label")),
                "year": year_match.group(0) if year_match else "",
                "description": description,
                "sourceUrl": f"https://www.wikidata.org/wiki/{entry.get('id')}",
            }
        )
    return items


def _resolve_qid(payload, language):
    payload = payload or {}
    identifiers = payload.get("identifiers") or {}

    direct = _qid(
        payload.get("wikidataId")
        or payload.get("wikidata_id")
        or payload.get("qid")
        or (payload.get("id") if _is_qid(payload.get("id")) else "")
        or identifiers.get("wikidataId")
    )
    if direct:
        return direct

    imdb_id = str(payload.get("imdbId") or payload.get("imdb_id") or identifiers.get("imdbId") or "").strip()
    if imdb_id:
        qid = _qid_by_external_id("P345", imdb_id)
        if qid:
            return qid

    tmdb_id = str(payload.get("tmdbId") or payload.get("tmdb_id") or identifiers.get("tmdbId") or "").strip()
    if tmdb_id:
        qid = _qid_by_external_id("P4947", tmdb_id)
        if qid:
            return qid

    title = str(payload.get("title") or "").strip()
    year = str(payload.get("year") or "").strip()
    if title:
        items = _search_items(title, language)
        if year:
            matching = [item for item in items if item.get("year") == year]
            if matching:
                return matching[0]["id"]
        if items:
            return items[0]["id"]

    return ""


def health_check(context=None):
    try:
        bindings = _sparql('SELECT ?item WHERE { ?item wdt:P345 "tt0133093". } LIMIT 1')
    except Exception as exc:  # noqa: BLE001 - report any failure as a status.
        return {"status": "unavailable", "message": f"Wikidata unreachable: {exc}"}
    if bindings:
        return {"status": "available", "message": "Wikidata SPARQL endpoint reachable."}
    return {"status": "unavailable", "message": "Wikidata returned no data."}


def search_title(payload, context=None):
    title = str((payload or {}).get("title") or "").strip()
    year = str((payload or {}).get("year") or "").strip()
    if not title:
        return {"status": "skipped", "provider": PROVIDER, "items": []}
    try:
        items = _search_items(title, _language(context))
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "provider": PROVIDER, "items": [], "error": str(exc)}
    if year:
        items = sorted(items, key=lambda item: item.get("year") != year)
    return {"status": "hit" if items else "miss", "provider": PROVIDER, "items": items[:12]}


def lookup_external_id(payload, context=None):
    language = _language(context)
    try:
        qid = _resolve_qid(payload, language)
        detail = _build_detail(qid, language) if qid else None
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "provider": PROVIDER, "error": str(exc)}
    if detail is None:
        return {"status": "miss", "provider": PROVIDER}
    return detail


def movie_details(payload, context=None):
    return lookup_external_id(payload, context)
