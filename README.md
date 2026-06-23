# DiscVault-Plugins

Official plug-ins for **DiscVault 26**. Newer plug-in versions are developed and published here.

Each plug-in lives in its own folder under [`plugins/`](plugins/) and contains a
`manifest.json` (metadata, capabilities and settings schema) and a `plugin.py`
(implementation against the `next-1` DiscVault plug-in API). The shared
[`plugins/_collection_import_base.py`](plugins/_collection_import_base.py) module
provides common logic used by the `import_*` plug-ins.

## Available plug-ins

Plug-ins are listed in the same order DiscVault shows them: grouped by role and
sorted by each plug-in's `orderIndex` within the group (lower numbers appear
first). The `orderIndex` bands map to the groups — `10-99` metadata sources,
`100-199` library & list sources, `200-299` import sources, `900+` system.

### Metadata sources (`10-99`)

| Order | Plug-in | ID | Version | Categories |
| --- | --- | --- | --- | --- |
| 10 | TMDb | `tmdb` | 1.0.2 | metadata_source |
| 15 | Wikidata | `wikidata` | 1.0.0 | metadata_source |
| 20 | OMDb | `omdb` | 1.0.0 | metadata_source |
| 30 | Barcode Hub | `barcode_hub` | 1.1.0 | metadata_source, metadata_bootstrap |
| 30 | UPCItemDB | `upcitemdb` | 1.0.2 | metadata_source, metadata_bootstrap _(superseded by `barcode_hub`)_ |
| 40 | Blu-ray.com | `bluray_com` | 1.0.2 | metadata_source |
| 45 | DVDFr | `dvd_fr` | 1.0.0 | metadata_source |
| 51 | MovieVault 26 | `movievault_26` | 1.4.0 | metadata_source, metadata_receiver |

### Library & personal-list sources (`100-199`)

| Order | Plug-in | ID | Version | Categories |
| --- | --- | --- | --- | --- |
| 110 | Plex | `plex` | 1.0.1 | digital_media_source, personal_list_source |
| 120 | Jellyfin | `jellyfin` | 1.0.1 | digital_media_source, personal_list_source |
| 130 | Trakt | `trakt` | 1.0.2 | personal_list_source |

### Import sources (`200-299`)

| Order | Plug-in | ID | Version | Categories |
| --- | --- | --- | --- | --- |
| 210 | My Movies.dk Import | `import_mymovies_dk` | 1.2.0 | import_source |
| 220 | Letterboxd Import | `import_letterboxd` | 1.2.0 | import_source |
| 230 | Blu-ray.com Import | `import_bluray_com` | 1.2.0 | import_source |
| 240 | CLZ Movies Web Import | `import_clz_movies` | 1.2.0 | import_source |

### System (`900+`)

| Order | Plug-in | ID | Version | Categories |
| --- | --- | --- | --- | --- |
| 910 | DiscVault MCP Server | `discvault_mcp` | 1.0.0 | system, mcp |
| 920 | DiscVault API Access | `discvault_api` | 1.1.0 | system, api |

## Plug-in layout

```
plugins/
  <plugin_id>/
    manifest.json   # id, name, version, capabilities, settings/secrets schema
    plugin.py       # implementation
  _collection_import_base.py   # shared helpers for import_* plug-ins
```

## Barcode Hub

`barcode_hub` is a multi-source barcode → title hint (bootstrap) plug-in that
supersedes the standalone `upcitemdb` plug-in. It queries up to three barcode
databases and merges the results (de-duplicated by title, disc releases ranked
first):

| Source | API key | Notes |
| --- | --- | --- |
| UPCItemDB | none | Free trial lookup, always on. |
| Go-UPC | none | Public-page scrape of [go-upc.com](https://go-upc.com), always on; good brand/category data. |
| EAN-Search | optional (`eanSearchToken`) | 1.2B barcodes from [ean-search.org](https://www.ean-search.org); free accounts get a small daily quota (~100-250/day), strong on EU/PAL releases. |
| Barcode Lookup | optional (`barcodeLookupKey`) | International database from [barcodelookup.com](https://www.barcodelookup.com) via its **API key** (the public site is bot-protected and cannot be scraped). |

Without keys it runs UPCItemDB + Go-UPC (both free, no key). Add an EAN-Search
token (free tier works) or Barcode Lookup key in the plug-in settings to widen
barcode coverage for discs the free sources do not know.

