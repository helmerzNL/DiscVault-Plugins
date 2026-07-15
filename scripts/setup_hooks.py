from __future__ import annotations

from pathlib import Path
import subprocess


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    subprocess.run(
        ["git", "config", "core.hooksPath", ".githooks"],
        cwd=repo_root,
        check=True,
    )
    print("Configured core.hooksPath=.githooks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
