"""Archive bootstrap never modifies existing publishing directories."""

import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.scripts.ingestion import initialize_diagnostics_archive as bootstrap
from app.scripts.ingestion.diagnostics_archives import (
    DIAGNOSTICS_ARCHIVES_BY_MACHINE,
    DiagnosticsArchive,
)


@pytest.fixture
def archive_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    os.chown(tmp_path, os.getuid(), os.getegid())
    root = tmp_path / "diagnostics_archive"
    monkeypatch.setitem(
        DIAGNOSTICS_ARCHIVES_BY_MACHINE,
        "test-site",
        DiagnosticsArchive(str(root), "https://example.org/diagnostics_archive"),
    )
    return root


def test_create_root_with_caller_uid_and_parent_group(archive_root: Path) -> None:
    assert bootstrap.initialize_archive("test-site") == archive_root
    info = archive_root.stat()
    assert info.st_uid == os.getuid()
    assert info.st_gid == archive_root.parent.stat().st_gid
    assert stat.S_IMODE(info.st_mode) == 0o2775
    assert list(archive_root.iterdir()) == []


def test_configured_group_is_resolved_by_name(
    archive_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(
        DIAGNOSTICS_ARCHIVES_BY_MACHINE,
        "test-site",
        DiagnosticsArchive(str(archive_root), "https://example.org", group="e3sm"),
    )
    groups = []

    def get_group(name: str):
        groups.append(name)
        return SimpleNamespace(gr_gid=os.getegid())

    monkeypatch.setattr(bootstrap.grp, "getgrnam", get_group)
    bootstrap.initialize_archive("test-site")
    assert groups == ["e3sm"]
    assert archive_root.stat().st_gid == os.getegid()


@pytest.mark.parametrize("machine", ["perlmutter", "pm", "pm-cpu", "pm-gpu"])
def test_nersc_archives_use_e3sm_group(machine: str) -> None:
    assert DIAGNOSTICS_ARCHIVES_BY_MACHINE[machine].group == "e3sm"


def test_existing_directory_and_contents_stay_unchanged(archive_root: Path) -> None:
    archive_root.mkdir(mode=0o700)
    content = archive_root / "published.txt"
    content.write_text("published diagnostics")
    before = archive_root.stat()
    bootstrap.initialize_archive("test-site")
    after = archive_root.stat()
    assert (after.st_uid, after.st_gid, after.st_mode) == (
        before.st_uid,
        before.st_gid,
        before.st_mode,
    )
    assert content.read_text() == "published diagnostics"


def test_existing_file_is_rejected(archive_root: Path) -> None:
    archive_root.write_text("not a directory")
    with pytest.raises(ValueError, match="not a directory"):
        bootstrap.initialize_archive("test-site")
    assert archive_root.read_text() == "not a directory"


def test_unknown_machine_is_rejected(archive_root: Path) -> None:
    with pytest.raises(ValueError, match="Unknown diagnostics machine"):
        bootstrap.initialize_archive("unknown")
    assert not archive_root.exists()


def test_missing_publishing_parent_is_not_created(
    archive_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = archive_root / "missing-parent/diagnostics_archive"
    monkeypatch.setitem(
        DIAGNOSTICS_ARCHIVES_BY_MACHINE,
        "test-site",
        DiagnosticsArchive(str(root), "https://example.org"),
    )
    with pytest.raises(FileNotFoundError):
        bootstrap.initialize_archive("test-site")
    assert not archive_root.exists()


def test_group_membership_required_before_creation(
    archive_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bootstrap.os, "getgroups", lambda: [])
    monkeypatch.setattr(bootstrap.os, "getegid", lambda: -1)
    with pytest.raises(ValueError, match="must belong to archive group"):
        bootstrap.initialize_archive("test-site")
    assert not archive_root.exists()


def test_failed_permissions_remove_new_empty_root(
    archive_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_chown(*args):
        raise PermissionError("cannot set ownership")

    monkeypatch.setattr(bootstrap.os, "chown", fail_chown)
    with pytest.raises(PermissionError, match="cannot set ownership"):
        bootstrap.initialize_archive("test-site")
    assert not archive_root.exists()
