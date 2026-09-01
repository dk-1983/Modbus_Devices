"""Run the release-blocking Ruff correctness and format-debt ratchet."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / ".ruff-format-baseline"


def _git_lines(*arguments: str) -> tuple[str, ...]:
    result = subprocess.run(
        ("git", *arguments),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return tuple(line for line in result.stdout.splitlines() if line)


def _python_files() -> tuple[str, ...]:
    paths = {
        *(ROOT / "custom_components" / "modbus_devices").rglob("*.py"),
        *(ROOT / "scripts").glob("*.py"),
        *(ROOT / "tests").glob("test_*.py"),
    }
    return tuple(
        sorted(
            path.relative_to(ROOT).as_posix()
            for path in paths
            if "__pycache__" not in path.parts
        )
    )


def _format_baseline() -> frozenset[str]:
    entries = frozenset(
        line.strip()
        for line in BASELINE_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    missing = sorted(path for path in entries if not (ROOT / path).is_file())
    if missing:
        raise SystemExit(f"Missing Ruff baseline files: {', '.join(missing)}")
    return entries


def _run_ruff(*arguments: str) -> None:
    subprocess.run(
        (
            sys.executable,
            "-m",
            "ruff",
            "--config",
            str(ROOT / "ruff.toml"),
            *arguments,
        ),
        cwd=ROOT,
        check=True,
    )


def _changed_python_files(base: str | None, files: frozenset[str]) -> set[str]:
    if not base or set(base) == {"0"}:
        return set()
    subprocess.run(
        ("git", "rev-parse", "--verify", f"{base}^{{commit}}"),
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    committed = set(_git_lines("diff", "--name-only", f"{base}...HEAD", "--", "*.py"))
    working = set(_git_lines("diff", "--name-only", "--", "*.py"))
    return (committed | working) & files


def main() -> None:
    """Run correctness globally and formatting outside/touched inside debt."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--changed-base")
    arguments = parser.parse_args()

    python_files = frozenset(_python_files())
    baseline = _format_baseline()
    unknown = sorted(baseline - python_files)
    if unknown:
        raise SystemExit(f"Non-Python Ruff baseline entries: {', '.join(unknown)}")

    _run_ruff("check", *sorted(python_files))

    format_files = python_files - baseline
    touched_debt = (
        _changed_python_files(arguments.changed_base, python_files) & baseline
    )
    if touched_debt:
        raise SystemExit(
            "Changed Ruff debt files must be fully formatted and removed from "
            f"{BASELINE_PATH.name}: {', '.join(sorted(touched_debt))}"
        )
    _run_ruff("format", "--check", *sorted(format_files))

    print(
        "Ruff gate passed: "
        f"{len(python_files)} correctness files, "
        f"{len(format_files)} format-clean files, "
        f"{len(baseline)} bounded debt files"
    )


if __name__ == "__main__":
    main()
