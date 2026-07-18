from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess

try:
    from scripts.build_plugin import shared_runtime_plugin_ids
except ModuleNotFoundError:
    from build_plugin import shared_runtime_plugin_ids


REPO_ROOT = Path(__file__).resolve().parents[1]
VERSION_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def version_tuple(value: str) -> tuple[int, int, int]:
    match = VERSION_PATTERN.fullmatch(value)
    if not match:
        raise ValueError(f"Invalid semantic version: {value}")
    return tuple(int(part) for part in match.groups())


def base_manifest(base_ref: str, relative_path: str) -> dict | None:
    result = subprocess.run(
        ["git", "show", f"{base_ref}:{relative_path}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)


def changed_plugins(base_ref: str) -> set[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", base_ref, "--", "plugins"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f"Unable to compare plugin changes with base ref {base_ref}")
    changed = set()
    for line in result.stdout.splitlines():
        parts = Path(line).parts
        if not parts or parts[0] != "plugins":
            continue
        if len(parts) >= 3:
            changed.add(parts[1])
        elif len(parts) == 2:
            changed.update(shared_runtime_plugin_ids(parts[1]))
    return changed


def validate_catalog(manifests: dict[str, dict]) -> list[str]:
    failures = []
    catalog = json.loads((REPO_ROOT / "catalog.json").read_text(encoding="utf-8"))
    entries = {
        str(entry.get("id") or ""): entry
        for entry in catalog.get("plugins") or []
        if isinstance(entry, dict)
    }
    for plugin_id, manifest in manifests.items():
        entry = entries.get(plugin_id)
        if not entry:
            failures.append(f"{plugin_id}: missing catalog entry")
            continue
        version = manifest["version"]
        expected = {
            "version": version,
            "minimumDiscVaultVersion": manifest.get("minimumDiscVaultVersion"),
            "archive": f"{plugin_id}_{version}.zip",
            "checksum": f"{plugin_id}_{version}.zip.sha256",
            "releaseTag": f"{plugin_id}-v{version}",
        }
        for key, value in expected.items():
            if entry.get(key) != value:
                failures.append(f"{plugin_id}: catalog {key} must be {value}")
    unknown = set(entries) - set(manifests)
    failures.extend(f"{plugin_id}: catalog entry has no plugin directory" for plugin_id in sorted(unknown))
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate per-plugin semantic versions.")
    parser.add_argument("--base-ref")
    args = parser.parse_args()

    manifests = {}
    failures = []
    for path in sorted((REPO_ROOT / "plugins").glob("*/manifest.json")):
        plugin_id = path.parent.name
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifests[plugin_id] = manifest
        if manifest.get("id") != plugin_id:
            failures.append(f"{plugin_id}: manifest id must match its directory")
        try:
            version_tuple(str(manifest.get("version") or ""))
        except ValueError as exc:
            failures.append(f"{plugin_id}: {exc}")
        try:
            version_tuple(str(manifest.get("minimumDiscVaultVersion") or ""))
        except ValueError as exc:
            failures.append(f"{plugin_id}: invalid minimum DiscVault version: {exc}")

    failures.extend(validate_catalog(manifests))
    if args.base_ref:
        try:
            changed = changed_plugins(args.base_ref)
        except ValueError as exc:
            failures.append(
                f"{exc}. Fetch the base ref and rerun: "
                f"python scripts/check_versions.py --base-ref {args.base_ref}"
            )
            changed = set()
        for plugin_id in sorted(changed):
            manifest = manifests.get(plugin_id)
            if not manifest:
                continue
            relative = f"plugins/{plugin_id}/manifest.json"
            previous = base_manifest(args.base_ref, relative)
            if previous is None:
                continue
            if version_tuple(manifest["version"]) <= version_tuple(previous["version"]):
                failures.append(
                    f"{plugin_id}: protected plugin files changed without a version bump. "
                    f"Run: python scripts/bump_plugin_version.py --plugin {plugin_id} --part patch "
                    f"--base-ref {args.base_ref}"
                )

    if failures:
        print("\n".join(failures))
        return 1
    print("Plugin version guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
