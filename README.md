# DiscVault Plugins

Audited, standalone plugins for DiscVault 26. Source, tests, checksums, and
reproducible release packaging live together in this repository.

| Plugin | Version | Minimum DiscVault | Install |
|---|---:|---:|---|
| [MovieVault v2](plugins/movievault_v2/README.md) | 1.2.0 | 26.4.62 | Candidate only; release follows operator acceptance |

Archives contain one root folder named after the plugin. Extract that folder
into `DISCVAULT_PLUGIN_INSTALL_DIR` (normally `/data/plugins`) and restart or
refresh DiscVault's plugin registry.

## Repository checks

```console
python -m unittest discover -s tests
python scripts/check_secrets.py
python scripts/check_versions.py
python scripts/build_plugin.py --plugin movievault_v2
```

Run `python scripts/setup_hooks.py` once after cloning to activate the fast
pre-commit checks.

Plugin releases use tags in the form `<plugin-id>-v<version>`. Release
artifacts are rebuilt from the tagged source with normalized paths,
timestamps, and permissions; identical source therefore produces identical
ZIP bytes. This repository has no stable/beta channel aliases: every plugin
version is immutable and independently downloadable.
