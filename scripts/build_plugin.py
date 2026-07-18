from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "plugins"
EXCLUDED_NAMES = {"__pycache__", ".pytest_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".zip", ".sha256"}
SHARED_RUNTIME_FILES = {
    "wikidata_awards.py": {"tmdb"},
}


def plugin_files(plugin_dir: Path) -> list[Path]:
    files = []
    for path in plugin_dir.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(plugin_dir)
        if any(part.startswith(".") or part in EXCLUDED_NAMES for part in relative.parts):
            continue
        if path.suffix in EXCLUDED_SUFFIXES:
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(plugin_dir).as_posix())


def discover_plugin_ids() -> list[str]:
    return sorted(path.parent.name for path in PLUGIN_ROOT.glob("*/manifest.json"))


def shared_runtime_files(plugin_id: str) -> list[Path]:
    names = {
        name
        for name, plugin_ids in SHARED_RUNTIME_FILES.items()
        if plugin_id in plugin_ids
    }
    if plugin_id.startswith("import_"):
        names.add("_collection_import_base.py")
    return sorted(
        (PLUGIN_ROOT / name for name in names if (PLUGIN_ROOT / name).is_file()),
        key=lambda path: path.name,
    )


def archive_files(plugin_id: str, plugin_dir: Path) -> list[tuple[str, Path]]:
    files = {
        source.relative_to(plugin_dir).as_posix(): source
        for source in plugin_files(plugin_dir)
    }
    for source in shared_runtime_files(plugin_id):
        if source.name in files:
            raise ValueError(
                f"{plugin_id}: shared runtime file conflicts with plugin file: {source.name}"
            )
        files[source.name] = source
    return sorted(files.items())


def build_plugin(plugin_id: str, output_dir: Path) -> tuple[Path, Path]:
    plugin_dir = PLUGIN_ROOT / plugin_id
    manifest_path = plugin_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"Unknown plugin: {plugin_id}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("id") != plugin_id:
        raise ValueError("Manifest id does not match the plugin directory")
    version = str(manifest.get("version") or "").strip()
    if not version:
        raise ValueError("Manifest version is required")

    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / f"{plugin_id}_{version}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as bundle:
        for relative, source in archive_files(plugin_id, plugin_dir):
            info = zipfile.ZipInfo(
                filename=f"{plugin_id}/{relative}",
                date_time=(1980, 1, 1, 0, 0, 0),
            )
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_STORED
            bundle.writestr(info, source.read_bytes())

    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum = output_dir / f"{archive.name}.sha256"
    checksum.write_text(f"{digest}  {archive.name}\n", encoding="ascii", newline="\n")
    return archive, checksum


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a deterministic DiscVault plugin archive.")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--plugin")
    selection.add_argument("--all", action="store_true", help="Build every discovered plugin.")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "dist")
    args = parser.parse_args()

    plugin_ids = discover_plugin_ids() if args.all else [args.plugin]
    for plugin_id in plugin_ids:
        archive, checksum = build_plugin(plugin_id, args.output_dir)
        print(archive)
        print(checksum)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
