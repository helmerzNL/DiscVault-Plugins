# MovieVault v2 for DiscVault 26

This metadata-source plugin reads MovieVault v2's anonymous `distribution-2`
feed through the compatible DiscVault core bridge. DiscVault synchronizes a
durable local index; normal barcode, title, release, and box-set lookups do not
contact MovieVault.

## Requirements

- DiscVault `26.4.40` or newer.
- A reachable MovieVault v2 origin with `distribution-2` enabled.
- No API key, contribution token, instance identity, or other secret.

## Manual installation

1. Download `movievault_v2_1.0.0.zip` and its `.sha256` file from the release.
2. Verify the SHA-256 checksum.
3. Extract the archive directly into `DISCVAULT_PLUGIN_INSTALL_DIR`, normally
   the persistent `/data/plugins` directory. The resulting path must be
   `/data/plugins/movievault_v2/manifest.json`.
4. Restart DiscVault or refresh its plugin registry.
5. Configure the **MovieVault v2 origin**, then enable the plugin.
6. Choose **Queue sync** and wait for the job and health state to become
   `current`.

`movievault_26` can remain installed and enabled independently. Contributions
continue through the existing attributed MovieVault connection; this plugin
has no contribution capability and never receives those credentials.

Anonymous bucket fallback is disabled by default. When enabled, it requests
only one anonymous hash bucket after a local miss and filters that bucket by
the complete hash.
