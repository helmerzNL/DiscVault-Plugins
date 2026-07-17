# MovieVault v2 for DiscVault 26

This metadata-source plugin reads MovieVault v2's anonymous feed through the
compatible DiscVault core bridge. DiscVault synchronizes a durable local
index; normal barcode, title, release, and box-set lookups do not contact
MovieVault.

The plugin manifest declares a `distributionContractRange` of
`distribution-2` (minimum) through `distribution-4` (maximum). DiscVault core
negotiates the highest contract both sides support and silently falls back
to the range's minimum on any mismatch, so this plugin keeps working with
`distribution-2`/`distribution-3` cores exactly as before; `distribution-4`
only activates once the core also supports it.

## Requirements

- DiscVault `26.4.62` or newer to negotiate `distribution-4` (the first core
  release with strict `distribution-4` parsing, bounded anonymous poster
  caching, and authenticated local poster routes). Older 26.x cores keep
  negotiating `distribution-2`/`distribution-3` with this same package;
  `distribution-4` never activates on them.
- A reachable MovieVault v2 origin with a compatible distribution feed
  enabled.
- No API key, contribution token, instance identity, or other secret.

## Manual installation

1. Download `movievault_v2_1.1.0.zip` and its `.sha256` file from the release.
2. Verify the SHA-256 checksum.
3. Extract the archive directly into `DISCVAULT_PLUGIN_INSTALL_DIR`, normally
   the persistent `/data/plugins` directory. The resulting path must be
   `/data/plugins/movievault_v2/manifest.json`.
4. Restart DiscVault or refresh its plugin registry.
5. Review the automatically populated settings and enable the plugin. DiscVault
   queues the first index synchronization when the plugin is enabled.
6. Wait for the queued job and health state to become `current`.

The standard origin is `https://movies2.vaultstack.eu`. A self-hosted
MovieVault v2 origin can be saved instead; explicit operator settings are
preserved across registry refreshes and plugin upgrades. The remaining defaults
are a 6-hour sync interval, 48-hour stale threshold, 20-second request timeout,
128 MiB artifact limit, and 12 lookup results.

`movievault_26` can remain installed and enabled independently. Contributions
continue through the existing attributed MovieVault connection; this plugin
has no contribution capability and never receives those credentials.

Anonymous bucket fallback is disabled by default. When enabled, it requests
only one anonymous hash bucket after a local miss and filters that bucket by
the complete hash.

## Poster URLs stay local

When DiscVault core negotiates `distribution-4` and has cached a
rights-approved primary poster for a release or box set, lookup results carry
an additional `posterUrl` field. That value is always a local, authenticated
DiscVault asset route resolved by the core — never a MovieVault URL, and
never fetched, stored, or transmitted by this plugin. On `distribution-2`/
`distribution-3` negotiated contracts the field is simply absent.

## Release notes

- **1.1.0** — Added `distribution-4` to the negotiated `distributionContractRange`
  (minimum stays `distribution-2`) and raised the minimum DiscVault core to
  `26.4.62`. Lookup results now pass through the core's local, authenticated
  `posterUrl` when a `distribution-4` core has cached a rights-approved
  primary poster; no other behavior changed, and older cores keep negotiating
  `distribution-2`/`distribution-3` unaffected.
- **1.0.4** — Prior baseline: anonymous `distribution-2` feed only, DiscVault
  `26.4.44` or newer.

