"""Tests for the repository Ruff correctness and format-debt ratchet."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess

import pytest


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "ruff_gate.py"
SPEC = importlib.util.spec_from_file_location("ruff_gate", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
ruff_gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ruff_gate)


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ("git", *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _commit(repository: Path, message: str) -> str:
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", message)
    return _git(repository, "rev-parse", "HEAD")


@pytest.fixture
def ratchet_repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Create a history with debt before and clean changes after the epoch."""
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "ruff-gate@example.invalid")
    _git(tmp_path, "config", "user.name", "Ruff gate test")

    (tmp_path / "legacy.py").write_text("value=1\n", encoding="utf-8")
    pre_epoch = _commit(tmp_path, "legacy debt")
    (tmp_path / "policy.txt").write_text("ratchet\n", encoding="utf-8")
    epoch = _commit(tmp_path, "introduce ratchet")
    (tmp_path / "manifest.json").write_text('{"version":"1.0.0"}\n', encoding="utf-8")
    release = _commit(tmp_path, "release")

    monkeypatch.setattr(ruff_gate, "ROOT", tmp_path)
    monkeypatch.setattr(ruff_gate, "RATCHET_EPOCH", epoch)
    return tmp_path, pre_epoch, epoch, release


def test_push_base_before_epoch_ignores_pre_epoch_debt(ratchet_repository):
    """Do not reinterpret pre-policy edits as release-push format debt."""
    _, pre_epoch, epoch, _ = ratchet_repository
    files = frozenset({"legacy.py"})

    assert ruff_gate._effective_diff_base(pre_epoch) == epoch
    assert ruff_gate._changed_python_files(pre_epoch, files) == set()


def test_post_epoch_legacy_edit_remains_ratchet_failure(ratchet_repository):
    """A later edit to a baseline file remains visible to the debt gate."""
    repository, _, _, release = ratchet_repository
    (repository / "legacy.py").write_text("value = 2\n", encoding="utf-8")
    _commit(repository, "touch legacy debt")
    files = frozenset({"legacy.py"})
    baseline = frozenset({"legacy.py"})

    assert ruff_gate._effective_diff_base(release) == release
    changed = ruff_gate._changed_python_files(release, files)

    assert changed == {"legacy.py"}
    assert changed & baseline == {"legacy.py"}


def test_post_epoch_nonbaseline_file_stays_in_format_scope(ratchet_repository):
    """New format-clean files remain outside the bounded debt baseline."""
    repository, _, _, release = ratchet_repository
    (repository / "clean.py").write_text("value = 2\n", encoding="utf-8")
    _commit(repository, "add clean file")
    files = frozenset({"legacy.py", "clean.py"})
    baseline = frozenset({"legacy.py"})

    changed = ruff_gate._changed_python_files(release, files)

    assert changed == {"clean.py"}
    assert changed & baseline == set()


def test_unavailable_event_base_fails_clearly(ratchet_repository):
    """Never silently skip a comparison when the event history is absent."""
    with pytest.raises(SystemExit, match="fetch the required Git history"):
        ruff_gate._effective_diff_base("missing-event-base")
