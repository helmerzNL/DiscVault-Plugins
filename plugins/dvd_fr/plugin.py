"""DVDFr metadata source plug-in.

Looks up DVD/Blu-ray releases on the official DVDFr.com XML API. The API exposes
rich, disc-level metadata that is especially strong for DVD technical specs
(region/zone codes, PAL/NTSC standard, disc layer type, packaging, audio/subtitle
tracks) which makes it a good DVD-focused companion to the Blu-ray.com source.

Endpoints (no API key required):
    - https://www.dvdfr.com/api/search.php?title=<title>
    - https://www.dvdfr.com/api/search.php?gencode=<EAN barcode>
    - https://www.dvdfr.com/api/dvd.php?id=<id>

DVDFr API usage terms (https://www.dvdfr.com/api/) require, among other things,
that the data be used for strictly personal purposes, not republished without
prior agreement, and that any software integrating the API be distributed free of
charge. Those terms are surfaced on results via ``usageTerms``.
"""

import re
from urllib.parse import urlencode
from xml.etree import ElementTree as ET

import requests

API_BASE = "https://www.dvdfr.com/api"
PROVIDER = "dvd_fr"
PROVIDER_LABEL = "DVDFr"
USAGE_TERMS = (
    "Data provided by DVDFr.com. Use of the DVDFr API is for strictly personal "
    "purposes; data must not be republished without prior agreement, and software "
    "integrating the API must be distributed free of charge. "
    "See https://www.dvdfr.com/api/ for the full terms."
)


def _headers():
    return {"User-Agent": "Mozilla/5.0 (DiscVault Next; +https://discvault.eu)"}


def _get(path, **params):
    url = f"{API_BASE}/{path}?{urlencode(params)}"
    response = requests.get(url, headers=_headers(), timeout=10)
    response.raise_for_status()
    return response.text


def _parse_xml(text):
    try:
        return ET.fromstring(text)
    except ET.ParseError:
        return None


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _node_text(node):
    if node is None or node.text is None:
        return ""
    return _clean(node.text)


def _child_text(parent, tag):
    if parent is None:
        return ""
    return _node_text(parent.find(tag))


def _join(values):
    return ", ".join(value for value in values if value)


def _normalize_format(media):
    text = str(media or "").strip().lower()
    if "blu" in text:
        return "Blu-ray"
    if "uhd" in text or "4k" in text:
        return "4K UHD"
    if "umd" in text:
        return "UMD"
    if "hd" in text and "dvd" in text:
        return "HD DVD"
    if "dvd" in text:
        return "DVD"
    return _clean(media)


def _runtime_minutes(value):
    match = re.search(r"\d+", str(value or ""))
    return int(match.group(0)) if match else None


def _collect(root, container_tag, item_tag):
    values = []
    container = None if root is None else root.find(container_tag)
    if container is None:
        return values
    for item in container.findall(item_tag):
        text = _node_text(item)
        if text and text not in values:
            values.append(text)
    return values


def _stars(root, role_substr):
    names = []
    stars = None if root is None else root.find("stars")
    if stars is None:
        return names
    needle = role_substr.casefold()
    for star in stars.findall("star"):
        if needle in str(star.get("type") or "").casefold():
            name = _node_text(star)
            if name and name not in names:
                names.append(name)
    return names


def _audio_tracks(root):
    tracks = []
    container = None if root is None else root.find("audiotracks")
    if container is None:
        return tracks
    for track in container.findall("track"):
        langue = _child_text(track, "langue")
        codec = _child_text(track, "standard") or _child_text(track, "code")
        encodage = _child_text(track, "encodage")
        label = _clean(" ".join(part for part in (langue, codec, encodage) if part))
        if label and label not in tracks:
            tracks.append(label)
    return tracks


def _search(params):
    root = _parse_xml(_get("search.php", **params))
    if root is None:
        return []
    items = []
    for dvd in root.findall("dvd"):
        titres = dvd.find("titres")
        fr_title = _child_text(titres, "fr")
        vo_title = _child_text(titres, "vo")
        dvd_id = _child_text(dvd, "id")
        items.append(
            {
                "provider": PROVIDER,
                "providerLabel": PROVIDER_LABEL,
                "id": dvd_id,
                "title": fr_title or vo_title,
                "originalTitle": vo_title,
                "year": _child_text(dvd, "annee"),
                "edition": _child_text(dvd, "edition"),
                "publisher": _child_text(dvd, "editeur"),
                "posterUrl": _child_text(dvd, "cover"),
                "format": _normalize_format(_child_text(dvd, "media")),
            }
        )
    return items


def _build_detail(root):
    if root is None:
        return None
    titres = root.find("titres")
    fr_title = _child_text(titres, "fr")
    vo_title = _child_text(titres, "vo")
    title = fr_title or vo_title
    image = root.find("image")
    media = _child_text(root, "media")
    fmt = _normalize_format(media)
    dvd_id = _child_text(root, "id")
    url = _child_text(root, "url")
    cover = _child_text(root, "cover")
    ean = _child_text(root, "ean")
    edition = _child_text(root, "edition")
    rating = _child_text(root, "rating")
    zones = _collect(root, "zones", "zone")
    discs = _collect(root, "disques", "disque")

    technical_specs = {
        "format": fmt,
        "media": media,
        "region": _join(zones),
        "regions": zones,
        "discTypes": discs,
        "discCount": len(discs),
        "packaging": _child_text(root, "packaging"),
        "videoStandard": _child_text(image, "standard"),
        "aspectRatio": _child_text(image, "aspect_ratio"),
        "videoFormat": _child_text(image, "format"),
        "hdr": _child_text(image, "hdrs"),
        "audioTracks": _audio_tracks(root),
        "subtitles": _collect(root, "soustitrage", "soustitre"),
        "contentRatings": {"FR": rating} if rating else {},
    }

    movie = {
        "title": title,
        "originalTitle": vo_title,
        "year": _child_text(root, "annee"),
        "releaseDate": _child_text(root, "sortie"),
        "runtimeMinutes": _runtime_minutes(_child_text(root, "duree")),
        "overview": _child_text(root, "synopsis"),
        "director": _join(_stars(root, "Réalisateur")),
        "actor": _join(_stars(root, "Acteur")),
        "genre": _join(_collect(root, "categories", "categorie")),
        "country": _join(_collect(root, "listePays", "pays")),
        "language": _child_text(root, "langueOrigine"),
        "studio": _child_text(root, "studio"),
        "publisher": _child_text(root, "editeur"),
        "distributor": _child_text(root, "distributeur"),
        "posterUrl": cover,
        "format": fmt,
    }

    return {
        "status": "hit",
        "provider": PROVIDER,
        "sourceLabel": PROVIDER_LABEL,
        "sourceRef": dvd_id or url,
        "sourceUrl": url,
        "format": fmt,
        "releaseTitle": _join([title, edition]) if edition else title,
        "movie": movie,
        "release": {
            "title": title,
            "edition": edition,
            "format": fmt,
            "posterUrl": cover,
            "barcode": ean,
        },
        "technicalSpecs": technical_specs,
        "identifiers": {"ean": ean, "barcode": ean, "dvdfrId": dvd_id},
        "barcode": ean,
        "usageTerms": USAGE_TERMS,
    }


def _detail_by_id(dvd_id):
    dvd_id = str(dvd_id or "").strip()
    if not dvd_id:
        return None
    return _build_detail(_parse_xml(_get("dvd.php", id=dvd_id)))


def _filter_by_year(items, year):
    if not year:
        return items
    matching = [item for item in items if not item.get("year") or item.get("year") == year]
    return matching or items


def _detail_from_payload(payload):
    payload = payload or {}
    identifiers = payload.get("identifiers") or {}
    dvd_id = str(
        payload.get("id")
        or payload.get("dvdfrId")
        or payload.get("dvdfr_id")
        or identifiers.get("dvdfrId")
        or ""
    ).strip()
    if dvd_id:
        return _detail_by_id(dvd_id)

    barcode = str(
        payload.get("externalBarcode")
        or payload.get("barcode")
        or payload.get("ean")
        or ""
    ).strip()
    if barcode:
        items = _search({"gencode": barcode})
        if items:
            return _detail_by_id(items[0].get("id"))

    title = str(payload.get("title") or "").strip()
    year = str(payload.get("year") or "").strip()
    if title:
        items = _filter_by_year(_search({"title": title}), year)
        if items:
            return _detail_by_id(items[0].get("id"))

    return None


def health_check(context=None):
    try:
        root = _parse_xml(_get("search.php", title="Matrix"))
    except Exception as exc:  # noqa: BLE001 - surface any network/parse failure as status.
        return {"status": "unavailable", "message": f"DVDFr API unreachable: {exc}"}
    if root is not None and root.findall("dvd"):
        return {"status": "available", "message": "DVDFr API reachable.", "usageTerms": USAGE_TERMS}
    return {"status": "unavailable", "message": "DVDFr API returned no data."}


def search_title(payload, context=None):
    title = str((payload or {}).get("title") or "").strip()
    year = str((payload or {}).get("year") or "").strip()
    if not title:
        return {"status": "skipped", "provider": PROVIDER, "items": []}
    try:
        items = _filter_by_year(_search({"title": title}), year)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "provider": PROVIDER, "items": [], "error": str(exc)}
    return {"status": "hit" if items else "miss", "provider": PROVIDER, "items": items[:12]}


def search_barcode(payload, context=None):
    barcode = str((payload or {}).get("barcode") or (payload or {}).get("ean") or "").strip()
    if not barcode:
        return {"status": "skipped", "provider": PROVIDER}
    try:
        items = _search({"gencode": barcode})
        detail = _detail_by_id(items[0].get("id")) if items else None
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "provider": PROVIDER, "error": str(exc)}
    if detail is None:
        return {"status": "miss", "provider": PROVIDER, "barcode": barcode}
    return detail


def movie_details(payload, context=None):
    try:
        detail = _detail_from_payload(payload)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "provider": PROVIDER, "error": str(exc)}
    if detail is None:
        return {"status": "miss", "provider": PROVIDER}
    return detail


def technical_specs(payload, context=None):
    return movie_details(payload, context)
