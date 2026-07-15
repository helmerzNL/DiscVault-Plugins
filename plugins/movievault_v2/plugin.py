"""Callback-only MovieVault v2 metadata adapter for DiscVault 26."""

from __future__ import annotations

import hashlib


PROVIDER_ID = "movievault_v2"
PROVIDER_LABEL = "MovieVault v2"


def _settings(context):
    value = (context or {}).get("settings")
    return value if isinstance(value, dict) else {}


def _callback(context, name):
    value = (context or {}).get(name)
    return value if callable(value) else None


def _bridge_error():
    return {
        "status": "error",
        "provider": PROVIDER_ID,
        "reason": "core_bridge_unavailable",
    }


def _limit(context):
    value = _settings(context).get("maximumResults")
    if value is None or value == "" or isinstance(value, bool):
        return 12
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 12
    return min(max(parsed, 1), 50)


def _bool_setting(context, name, default=False):
    value = _settings(context).get(name)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() in {"1", "true", "yes", "on"}


def _normalized_barcode(value):
    text = str(value or "").strip()
    if any(not character.isdigit() and character not in {" ", "-"} for character in text):
        return ""
    digits = "".join(character for character in text if character.isdigit())
    if len(digits) not in {8, 12, 13, 14}:
        return ""
    expected = (
        10
        - sum(
            int(digit) * (3 if index % 2 == 0 else 1)
            for index, digit in enumerate(reversed(digits[:-1]))
        )
        % 10
    ) % 10
    return digits if expected == int(digits[-1]) else ""


def _barcode_hash(value):
    normalized = _normalized_barcode(value)
    return hashlib.sha256(normalized.encode("ascii")).hexdigest() if normalized else ""


def _source_ref(record):
    if record.get("recordType") == "release":
        return f"release:{record.get('releaseId') or ''}"
    return f"box_set:{record.get('boxSetId') or ''}"


def _identifiers(record):
    identifiers = {}
    for provider, value in (record.get("providerIds") or {}).items():
        if not value:
            continue
        if provider == "tmdb":
            identifiers["tmdbId"] = str(value)
        elif provider == "imdb":
            identifiers["imdbId"] = str(value)
    return identifiers


def _release_data(record):
    movie = {
        "title": record.get("canonicalTitle") or record.get("releaseTitle") or "",
        "releaseTitle": record.get("releaseTitle") or "",
        "year": record.get("releaseYear"),
        "format": record.get("format"),
        "edition": record.get("edition"),
        "country": record.get("countryCode"),
        "language": record.get("languageCode"),
        "regions": [record["region"]] if record.get("region") else [],
        "discCount": record.get("discCount"),
    }
    identifiers = _identifiers(record)
    return {
        key: value
        for key, value in {
            "provider": PROVIDER_ID,
            "providerLabel": PROVIDER_LABEL,
            "id": record.get("releaseId"),
            "releaseId": record.get("releaseId"),
            "filmId": record.get("filmId"),
            "title": movie["title"],
            "releaseTitle": movie["releaseTitle"],
            "year": movie["year"],
            "format": movie["format"],
            "edition": movie["edition"],
            "region": record.get("region"),
            "movie": movie,
            "release": {
                "id": record.get("releaseId"),
                "title": record.get("releaseTitle"),
                "edition": record.get("edition"),
                "format": record.get("format"),
                "region": record.get("region"),
                "country": record.get("countryCode"),
                "language": record.get("languageCode"),
                "releaseDate": record.get("releaseDate"),
                "discCount": record.get("discCount"),
            },
            "identifiers": identifiers,
            "sourceRef": _source_ref(record),
        }.items()
        if value not in (None, "", [], {})
    }


def _box_set_proposal(record):
    members = []
    for member in record.get("members") or []:
        members.append(
            {
                key: value
                for key, value in {
                    "position": member.get("position"),
                    "releaseId": member.get("releaseId"),
                    "filmId": member.get("filmId"),
                    "title": member.get("canonicalTitle"),
                    "canonicalTitle": member.get("canonicalTitle"),
                    "releaseTitle": member.get("releaseTitle"),
                    "edition": member.get("releaseEdition"),
                    "releaseEdition": member.get("releaseEdition"),
                    "format": member.get("format"),
                    "region": member.get("region"),
                    "discNumber": member.get("discNumber"),
                    "discFormat": member.get("discFormat"),
                    "relationship": "contains",
                }.items()
                if value not in (None, "", [], {})
            }
        )
    source_ref = _source_ref(record)
    evidence = {
        "entityType": "box_set",
        "memberSource": "movievault_v2_distribution",
        "memberConfidence": "confirmed",
        "memberCount": len(members),
        "membersAreExplicit": True,
        "detectedWithoutMembers": not bool(members),
        "sourceRef": source_ref,
    }
    return {
        key: value
        for key, value in {
            "id": record.get("boxSetId"),
            "boxSetId": record.get("boxSetId"),
            "title": record.get("title"),
            "edition": record.get("edition"),
            "yearRange": record.get("yearRange"),
            "format": record.get("format"),
            "country": record.get("countryCode"),
            "language": record.get("languageCode"),
            "members": members,
            "memberCount": len(members),
            "isBoxSet": True,
            "sourceRef": source_ref,
            "boxSetEvidence": evidence,
        }.items()
        if value not in (None, "", [], {})
    }


def _box_set_data(record):
    proposal = _box_set_proposal(record)
    return {
        "provider": PROVIDER_ID,
        "providerLabel": PROVIDER_LABEL,
        "id": record.get("boxSetId"),
        "title": record.get("title") or "",
        "format": record.get("format"),
        "edition": record.get("edition"),
        "isBoxSet": True,
        "boxSetProposal": proposal,
        "sourceRef": _source_ref(record),
    }


def _local_lookup(request, context):
    callback = _callback(context, "movievaultV2Lookup")
    if callback is None:
        return None
    return callback(request)


def _lookup_records(payload, context):
    barcode = (
        (payload or {}).get("barcode")
        or (payload or {}).get("externalBarcode")
        or (payload or {}).get("external_barcode")
    )
    digest = _barcode_hash(barcode)
    if digest:
        result = _local_lookup(
            {"kind": "barcode", "hash": digest, "limit": _limit(context)},
            context,
        )
        if result is None:
            return None
        records = result.get("results") if isinstance(result, dict) else []
        if records:
            return records
        if _bool_setting(context, "bucketFallback", False):
            fallback = _callback(context, "movievaultV2BucketLookup")
            if fallback is None:
                return None
            remote = fallback({"hash": digest, "limit": _limit(context)})
            return remote.get("results") if isinstance(remote, dict) else []
        return []
    title = str(
        (payload or {}).get("title")
        or (payload or {}).get("fallbackTitle")
        or (payload or {}).get("fallback_title")
        or ""
    ).strip()
    if not title:
        return []
    result = _local_lookup(
        {"kind": "title", "query": title, "limit": _limit(context)},
        context,
    )
    if result is None:
        return None
    return result.get("results") if isinstance(result, dict) else []


def health_check(context=None):
    callback = _callback(context, "movievaultV2Status")
    if callback is None:
        return _bridge_error()
    status = callback({})
    state = str((status or {}).get("state") or "unconfigured")
    health = {
        "current": "available",
        "stale": "degraded",
        "syncing": "syncing",
        "error": "unavailable",
        "unconfigured": "needs_configuration",
    }.get(state, "unavailable")
    return {
        "status": health,
        "provider": PROVIDER_ID,
        "state": state,
        "revision": (status or {}).get("revision") or 0,
        "lastSuccessAt": (status or {}).get("lastSuccessAt"),
        "lastAttemptAt": (status or {}).get("lastAttemptAt"),
        "errorCode": (status or {}).get("errorCode"),
    }


def sync_index(payload=None, context=None):
    callback = _callback(context, "movievaultV2Sync")
    if callback is None:
        return _bridge_error()
    result = callback({})
    return {
        "status": "completed",
        "provider": PROVIDER_ID,
        **(result if isinstance(result, dict) else {}),
    }


def search_barcode(payload, context=None):
    records = _lookup_records(payload or {}, context or {})
    if records is None:
        return _bridge_error()
    if not records:
        return {"status": "miss", "provider": PROVIDER_ID, "items": []}
    releases = [record for record in records if record.get("recordType") == "release"]
    selected = releases[0] if releases else records[0]
    data = (
        _release_data(selected)
        if selected.get("recordType") == "release"
        else _box_set_data(selected)
    )
    return {"status": "hit", **data, "items": [data]}


def search_title(payload, context=None):
    records = _lookup_records(payload or {}, context or {})
    if records is None:
        return _bridge_error()
    year = str((payload or {}).get("year") or "").strip()
    if year:
        records = [
            record
            for record in records
            if record.get("recordType") == "box_set"
            or not record.get("releaseYear")
            or str(record.get("releaseYear")) == year
        ]
    items = [
        _release_data(record)
        if record.get("recordType") == "release"
        else _box_set_data(record)
        for record in records[: _limit(context)]
    ]
    return {
        "status": "hit" if items else "miss",
        "provider": PROVIDER_ID,
        "items": items,
    }


def movie_details(payload, context=None):
    release_id = str(
        (payload or {}).get("releaseId")
        or (payload or {}).get("release_id")
        or (payload or {}).get("id")
        or ""
    ).strip()
    if release_id:
        result = _local_lookup(
            {"kind": "release", "releaseId": release_id, "limit": 1},
            context or {},
        )
        if result is None:
            return _bridge_error()
        records = result.get("results") if isinstance(result, dict) else []
    else:
        records = _lookup_records(payload or {}, context or {})
        if records is None:
            return _bridge_error()
    release = next(
        (record for record in records if record.get("recordType") == "release"),
        None,
    )
    if release is None:
        return {"status": "miss", "provider": PROVIDER_ID}
    return {"status": "hit", **_release_data(release)}


def box_set_candidates(payload, context=None):
    records = _lookup_records(payload or {}, context or {})
    if records is None:
        return _bridge_error()
    proposals = [
        _box_set_proposal(record)
        for record in records
        if record.get("recordType") == "box_set"
    ]
    return {
        "status": "hit" if proposals else "miss",
        "provider": PROVIDER_ID,
        "isBoxSetCandidate": bool(proposals),
        "boxSetProposal": proposals[0] if proposals else {},
        "boxSetProposals": proposals,
        "items": proposals,
    }
