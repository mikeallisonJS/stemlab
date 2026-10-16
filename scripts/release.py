"""Release plumbing around towncrier, the same shape as Cadent's.

Towncrier renders CHANGELOG.md; everything it doesn't do lives here:

  next-version   print the version the pending fragments add up to (empty if none)
  prepare        bump the version everywhere, render CHANGELOG.md, drop hidden fragments
  notes          print the CHANGELOG.md section for a version (release body)

Fragments live in changelog.d/ as <issue>.<type>.md, or +<slug>.<type>.md for a
change without an issue. Types breaking/feature/bugfix render into the
changelog; chore/docs are the escape hatch: they satisfy the PR check, decide
nothing above a patch bump, and never render.

The version lives in three files that must agree: pyproject.toml and
stemlab/__init__.py (PEP 440, `2.0.0.dev0`) and app/package.json (semver,
`2.0.0-dev.0`). A pre-release (`.devN`) releases as its base version, whatever
the fragments say: `2.0.0.dev0` plus anything is `2.0.0`.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FRAGMENT_DIR = REPO / "changelog.d"
PYPROJECT = REPO / "pyproject.toml"
INIT = REPO / "stemlab" / "__init__.py"
PACKAGE_JSON = REPO / "app" / "package.json"
CHANGELOG = REPO / "CHANGELOG.md"

VALID_TYPES = {"breaking", "feature", "bugfix", "chore", "docs"}
HIDDEN_TYPES = {"chore", "docs"}  # never rendered; towncrier never sees them

VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:\.dev(\d+))?$")


def fragment_type(path: Path) -> str | None:
    """`12.feature.md` or `+rename.chore.md` -> the type; None when the name doesn't fit."""
    parts = path.name.split(".")
    if len(parts) != 3 or parts[2] != "md" or parts[1] not in VALID_TYPES:
        return None
    if not re.fullmatch(r"\d+|\+[a-z0-9-]+", parts[0]):
        return None
    return parts[1]


def pending_fragments() -> dict[Path, str]:
    if not FRAGMENT_DIR.is_dir():
        return {}
    found = {}
    for path in sorted(FRAGMENT_DIR.iterdir()):
        if path.name == "README.md" or not path.is_file():
            continue
        kind = fragment_type(path)
        if kind is None:
            raise SystemExit(f"not a valid fragment name: changelog.d/{path.name}")
        found[path] = kind
    return found


def current_version() -> str:
    with PYPROJECT.open("rb") as f:
        return tomllib.load(f)["project"]["version"]


def next_version(current: str, types: set[str]) -> str:
    match = VERSION_RE.match(current)
    if match is None:
        raise SystemExit(f"cannot bump version {current!r}: expected X.Y.Z or X.Y.Z.devN")
    major, minor, patch = (int(match.group(i)) for i in (1, 2, 3))
    if match.group(4) is not None:
        # A pre-release already names the version it is working towards.
        return f"{major}.{minor}.{patch}"
    # Semver-0: breaking changes ride the minor rung until 1.0 exists.
    if "breaking" in types and major >= 1:
        return f"{major + 1}.0.0"
    if "breaking" in types or "feature" in types:
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def npm_version(version: str) -> str:
    """PEP 440 `2.0.0.dev0` -> semver `2.0.0-dev.0`; a release is spelled the same in both."""
    match = VERSION_RE.match(version)
    if match is None:
        raise SystemExit(f"not a version this script knows how to spell for npm: {version!r}")
    base = ".".join(match.group(i) for i in (1, 2, 3))
    return base if match.group(4) is None else f"{base}-dev.{match.group(4)}"


def _sub_once(path: Path, pattern: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    regex = re.compile(pattern, flags=re.MULTILINE)
    if len(regex.findall(text)) != 1:
        raise SystemExit(f"expected exactly one version line in {path.name}")
    path.write_text(regex.sub(replacement, text), encoding="utf-8", newline="\n")


def write_version(version: str) -> None:
    """Write the version to the three files that carry it."""
    _sub_once(PYPROJECT, r'^version = "[^"]+"$', f'version = "{version}"')
    _sub_once(INIT, r'^__version__ = "[^"]+"$', f'__version__ = "{version}"')
    _sub_once(PACKAGE_JSON, r'^  "version": "[^"]+",$', f'  "version": "{npm_version(version)}",')
    json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))  # still valid JSON


def relock() -> None:
    """Re-resolve uv.lock so it records the version just written; `uv lock` changes nothing else."""
    if shutil.which("uv") is None:
        raise SystemExit("uv is not on PATH, so uv.lock cannot be re-locked after the version bump")
    subprocess.run(["uv", "lock"], cwd=REPO, check=True)


def changelog_section(version: str) -> str:
    text = CHANGELOG.read_text(encoding="utf-8")
    match = re.search(
        rf"^## v{re.escape(version)}[^\n]*\n(.*?)(?=^## v|\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise SystemExit(f"no CHANGELOG.md section for v{version}")
    return match.group(1).strip()


def cmd_next_version() -> None:
    fragments = pending_fragments()
    if fragments:
        print(next_version(current_version(), set(fragments.values())))


def cmd_prepare() -> None:
    fragments = pending_fragments()
    if not fragments:
        raise SystemExit("no pending fragments in changelog.d/")
    version = next_version(current_version(), set(fragments.values()))
    write_version(version)
    relock()
    for path, kind in fragments.items():
        if kind in HIDDEN_TYPES:
            path.unlink()
    subprocess.run(
        [sys.executable, "-m", "towncrier", "build", "--yes", "--version", version],
        cwd=REPO,
        check=True,
    )
    print(version)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("next-version")
    sub.add_parser("prepare")
    notes = sub.add_parser("notes")
    notes.add_argument("--version", required=True)
    args = parser.parse_args()

    if args.command == "next-version":
        cmd_next_version()
    elif args.command == "prepare":
        cmd_prepare()
    elif args.command == "notes":
        print(changelog_section(args.version))


if __name__ == "__main__":
    main()
