from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {".git", "dist", "build", "__pycache__", ".pytest_cache"}
FORBIDDEN_FILES = {".env", ".env.local", ".env.production", ".env.development"}
SECRET_PATTERNS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github_token": re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "assigned_secret": re.compile(
        r"(?i)\b(?:api[_-]?key|secret|password|access[_-]?token)\s*[:=]\s*['\"](?!example|placeholder|change-me)[^'\"]{12,}['\"]"
    ),
}


def checked_files() -> list[Path]:
    files = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(REPO_ROOT)
        if any(part in EXCLUDED_DIRS for part in relative.parts):
            continue
        files.append(path)
    return files


def main() -> int:
    failures = []
    for path in checked_files():
        relative = path.relative_to(REPO_ROOT)
        if path.name in FORBIDDEN_FILES:
            failures.append(f"{relative}: environment file must not be committed")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for name, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                failures.append(f"{relative}: possible {name}")
    if failures:
        print("\n".join(failures))
        print("Remove the secret, rotate it, and keep only a safe placeholder in .env.example.")
        return 1
    print("Secret guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
