"""Lint Python and Talon files, then run the repository's unit tests."""

import argparse
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRECTORIES = {".git", ".venv", ".ruff_cache", "__pycache__", "node_modules"}


def talon_files(root):
    files = []
    for directory, children, names in os.walk(root):
        children[:] = sorted(set(children) - EXCLUDED_DIRECTORIES)
        files.extend(
            Path(directory) / name for name in sorted(names) if name.endswith(".talon")
        )
    return files


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fix", action="store_true", help="Apply lint/format fixes first"
    )
    arguments = parser.parse_args(argv)
    if sys.version_info < (3, 10):
        print(
            "Python 3.10+ is required. Use a modern Python or Talon's Python.",
            file=sys.stderr,
        )
        return 1

    formatter = ROOT / "node_modules" / "@cursorless" / "talon-tools" / "package.json"
    if importlib.util.find_spec("ruff") is None:
        print(
            f"Ruff is missing. Run: {sys.executable} -m pip install -r {ROOT / 'requirements-dev.txt'}",
            file=sys.stderr,
        )
        return 1
    if not formatter.is_file():
        print(f"Talon formatter is missing. Run npm ci in {ROOT}.", file=sys.stderr)
        return 1

    steps = [
        (
            "Python lint",
            [
                sys.executable,
                "-m",
                "ruff",
                "check",
                *(["--fix"] if arguments.fix else []),
                ".",
            ],
        ),
        (
            "Python formatting",
            [
                sys.executable,
                "-m",
                "ruff",
                "format",
                *([] if arguments.fix else ["--check"]),
                ".",
            ],
        ),
        (
            "Talon syntax and formatting",
            [
                "node",
                str(ROOT / "scripts" / "lint_talon.mjs"),
                *(["--fix"] if arguments.fix else []),
                *map(str, talon_files(ROOT)),
            ],
        ),
        (
            "Unit tests",
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        ),
    ]
    failed = []
    for title, command in steps:
        print(f"\n=== {title} ===", flush=True)
        try:
            result = subprocess.run(command, cwd=ROOT, check=False)
        except FileNotFoundError as error:
            print(f"Unable to run {title}: {error}", file=sys.stderr)
            failed.append(title)
            continue
        if result.returncode:
            failed.append(title)
    if failed:
        print(f"\nFailed: {', '.join(failed)}", file=sys.stderr)
        return 1
    print("\nAll lint and test checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
