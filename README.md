# DiscVault-Plugins

Official plug-ins for **DiscVault 26**. Newer plug-in versions are developed and published here.

Each plug-in lives in its own folder under [`plugins/`](plugins/) and contains a
`manifest.json` (metadata, capabilities and settings schema) and a `plugin.py`
(implementation against the `next-1` DiscVault plug-in API). The shared
[`plugins/_collection_import_base.py`](plugins/_collection_import_base.py) module
provides common logic used by the `import_*` plug-ins.

## Available plug-ins

| Plug-in | ID | Version | Categories |
| --- | --- | --- | --- |
| Blu-ray.com | `bluray_com` | 1.0.2 | metadata_source |
| DVDFr | `dvd_fr` | 1.0.0 | metadata_source |
| DiscVault API Access | `discvault_api` | 1.1.0 | system, api |
| DiscVault MCP Server | `discvault_mcp` | 1.0.0 | system, mcp |
| Blu-ray.com Import | `import_bluray_com` | 1.2.0 | import_source |
| CLZ Movies Web Import | `import_clz_movies` | 1.2.0 | import_source |
| Letterboxd Import | `import_letterboxd` | 1.2.0 | import_source |
| My Movies.dk Import | `import_mymovies_dk` | 1.2.0 | import_source |
| Jellyfin | `jellyfin` | 1.0.1 | digital_media_source, personal_list_source |
| MovieVault 26 | `movievault_26` | 1.4.0 | metadata_source, metadata_receiver |
| OMDb | `omdb` | 1.0.0 | metadata_source |
| Plex | `plex` | 1.0.1 | digital_media_source, personal_list_source |
| TMDb | `tmdb` | 1.0.2 | metadata_source |
| Trakt | `trakt` | 1.0.2 | personal_list_source |
| UPCItemDB | `upcitemdb` | 1.0.2 | metadata_source, metadata_bootstrap |
| Wikidata | `wikidata` | 1.0.0 | metadata_source |

## Plug-in layout

```
plugins/
  <plugin_id>/
    manifest.json   # id, name, version, capabilities, settings/secrets schema
    plugin.py       # implementation
  _collection_import_base.py   # shared helpers for import_* plug-ins
```
