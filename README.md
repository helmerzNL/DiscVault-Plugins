# DiscVault Plugins

Audited, standalone plugins for DiscVault 26. Source, tests, checksums, and
reproducible release packaging live together in this repository.

| Plugin | Version | Minimum DiscVault | Install |
|---|---:|---:|---|
| [MovieVault v2](plugins/movievault_v2/README.md) | 1.2.1 | 26.4.62 | Release `movievault_v2-v1.2.1` |

Archives contain one root folder named after the plugin. Extract that folder
into `DISCVAULT_PLUGIN_INSTALL_DIR` (normally `/data/plugins`) and restart or
refresh DiscVault's plugin registry.

## Repository checks

```console
python -m unittest discover -s tests
python scripts/check_secrets.py
python scripts/check_versions.py
python scripts/build_plugin.py --all
```

Run `python scripts/setup_hooks.py` once after cloning to activate the fast
pre-commit checks.

Every merge to `main` discovers all `plugins/*/manifest.json` files and builds
their archives with normalized paths, timestamps, and permissions. CI builds
every archive twice and requires byte-identical output. The release workflow
then creates each missing `<plugin-id>-v<version>` GitHub Release with its ZIP
and SHA-256 file. If a release already exists, the workflow downloads both
assets and requires them to match the reproducible build; published assets are
never overwritten.

This repository has no stable/beta channel aliases: every plugin version is
immutable and independently downloadable. A plugin source change therefore
requires its manifest and catalog version to be incremented before merge.
