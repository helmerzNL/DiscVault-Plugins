from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from check_versions import REPO_ROOT, base_manifest, version_tuple


def changed_since(base_ref: str, plugin_id: str) -> bool:
    result = subprocess.run(
        ["git", "diff", "--quiet", base_ref, "--", f"plugins/{plugin_id}"],
        cwd=REPO_ROOT,
        check=False,
    )
    return result.returncode == 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Bump a plugin version only when needed.")
    parser.add_argument("--plugin", required=True)
    parser.add_argument("--part", choices=("major", "minor", "patch"), default="patch")
    parser.add_argument("--base-ref", default="origin/main")
    args = parser.parse_args()

    manifest_path = REPO_ROOT / "plugins" / args.plugin / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    relative = f"plugins/{args.plugin}/manifest.json"
    previous = base_manifest(args.base_ref, relative)
    if previous is None:
        print(f"{args.plugin}: new plugin already has version {manifest['version']}; no bump needed.")
        return 0
    if not changed_since(args.base_ref, args.plugin):
        print(f"{args.plugin}: no plugin changes; no bump needed.")
        return 0
    current = version_tuple(manifest["version"])
    baseline = version_tuple(previous["version"])
    if current > baseline:
        print(f"{args.plugin}: version {manifest['version']} already exceeds {previous['version']}.")
        return 0

    major, minor, patch = current
    if args.part == "major":
        next_version = (major + 1, 0, 0)
    elif args.part == "minor":
        next_version = (major, minor + 1, 0)
    else:
        next_version = (major, minor, patch + 1)
    manifest["version"] = ".".join(str(part) for part in next_version)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    catalog_path = REPO_ROOT / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    entry = next(
        (
            item
            for item in catalog.get("plugins") or []
            if isinstance(item, dict) and item.get("id") == args.plugin
        ),
        None,
    )
    if entry is None:
        raise ValueError(f"{args.plugin}: catalog entry is missing")
    entry.update(
        {
            "version": manifest["version"],
            "minimumDiscVaultVersion": manifest.get("minimumDiscVaultVersion"),
            "archive": f"{args.plugin}_{manifest['version']}.zip",
            "checksum": f"{args.plugin}_{manifest['version']}.zip.sha256",
            "releaseTag": f"{args.plugin}-v{manifest['version']}",
        }
    )
    catalog_path.write_text(
        json.dumps(catalog, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"{args.plugin}: bumped manifest and catalog to {manifest['version']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
