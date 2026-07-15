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
        for source in plugin_files(plugin_dir):
            relative = source.relative_to(plugin_dir).as_posix()
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
    parser.add_argument("--plugin", required=True)
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "dist")
    args = parser.parse_args()

    archive, checksum = build_plugin(args.plugin, args.output_dir)
    print(archive)
    print(checksum)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
