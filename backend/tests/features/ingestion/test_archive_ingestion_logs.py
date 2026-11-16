"""Safety and retention tests for the weekly launcher-log archiver."""

import fcntl
import io
import tarfile
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from app.scripts.ingestion.sites.operations import archive_ingestion_logs as archiver

NOW = datetime(2026, 10, 25, tzinfo=timezone.utc)
COMPLETION = b"[2026-10-10T12:00:00Z] event=launcher_finished exit_code=0\n"


@pytest.fixture
def directories(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "raw_logs"
    archive = tmp_path / "history_logs"
    source.mkdir()
    archive.mkdir()

    return source, archive


@pytest.mark.parametrize("value", [None, "true", " YES ", "1", "on"])
def test_dry_run_defaults_and_true_values(monkeypatch, value):
    monkeypatch.delenv("DRY_RUN", raising=False)
    if value is not None:
        monkeypatch.setenv("DRY_RUN", value)
    assert archiver._dry_run_requested() is True


@pytest.mark.parametrize("value", ["false", " NO ", "0", "off"])
def test_live_values(monkeypatch, value):
    monkeypatch.setenv("DRY_RUN", value)
    assert archiver._dry_run_requested() is False


@pytest.mark.parametrize(
    "variable,value",
    [
        ("DRY_RUN", "typo"),
        ("LOG_RETENTION_DAYS", "-1"),
        ("LOG_RETENTION_DAYS", "seven"),
    ],
)
def test_invalid_configuration_preserves_files(
    directories, monkeypatch, variable, value
):
    source, archive = directories
    _log(source)
    before = _snapshot(source.parent)
    monkeypatch.setenv(variable, value)
    assert (
        archiver.main(["--source-dir", str(source), "--archive-dir", str(archive)]) == 1
    )
    assert _snapshot(source.parent) == before


def test_cli_uses_root_and_dry_run_override(tmp_path, monkeypatch):
    source = tmp_path / "operations/raw_logs"
    archive = tmp_path / "operations/history_logs"
    source.mkdir(parents=True)
    archive.mkdir()
    _log(source)
    monkeypatch.setenv("SIMBOARD_ROOT", str(tmp_path))
    monkeypatch.setenv("DRY_RUN", "false")
    before = _snapshot(tmp_path)
    assert archiver.main(["--dry-run"]) == 0
    assert _snapshot(tmp_path) == before


def test_cli_requires_root_or_explicit_paths(monkeypatch):
    monkeypatch.delenv("SIMBOARD_ROOT", raising=False)
    assert archiver.main([]) == 1


@pytest.mark.parametrize("existing", [False, True])
def test_dry_run_is_read_only(directories, existing):
    source, archive = directories
    _log(source)
    if existing:
        _tar(archive / "20261004-20261010.tar.gz", {"previous.log": b"previous"})
    before = _snapshot(source.parent)
    archiver.archive_logs(source, archive, now=NOW)
    assert _snapshot(source.parent) == before


@pytest.mark.parametrize(
    "day,now,retention,expected",
    [
        ("20261010", NOW, 7, "20261004-20261010"),
        ("20261011", NOW, 7, "20261011-20261017"),
        ("20261017", NOW, 7, "20261011-20261017"),
        ("20261018", NOW, 7, None),
        ("20261010", datetime(2026, 10, 17, tzinfo=timezone.utc), 7, None),
        (
            "20261010",
            datetime(2026, 10, 18, tzinfo=timezone.utc),
            7,
            "20261004-20261010",
        ),
        ("20261025", NOW, 0, None),
        (
            "20251231",
            datetime(2026, 1, 11, tzinfo=timezone.utc),
            7,
            "20251228-20260103",
        ),
    ],
)
def test_week_and_retention_boundaries(directories, day, now, retention, expected):
    source, archive = directories
    path = _log(source, day)
    contents = path.read_bytes()
    archiver.archive_logs(
        source, archive, now=now, retention_days=retention, dry_run=False
    )
    assert path.exists() is (expected is None)
    if expected:
        assert _contents(archive / f"{expected}.tar.gz") == {path.name: contents}
    else:
        assert not list(archive.glob("*.tar.gz"))


@pytest.mark.parametrize("exit_code", [0, 7])
@pytest.mark.parametrize("mode", ["staging", "archive", "unknown"])
def test_completed_success_and_failure_are_archived(directories, exit_code, mode):
    source, archive = directories
    path = _log(
        source,
        prefix=f"simboard-ingestion-{mode}-test-offline",
        contents=COMPLETION.replace(b"exit_code=0", f"exit_code={exit_code}".encode()),
    )
    archiver.archive_logs(source, archive, now=NOW, dry_run=False)
    assert not path.exists()


def test_unsupported_inputs_remain_untouched(directories, capsys):
    source, archive = directories
    incomplete = _log(source, contents=b"still running\n")
    invalid = _log(source, "20260230")
    unrelated = source / "other-20261010_120000-1.log"
    unrelated.write_bytes(COMPLETION)
    legacy = source / "SBCS-chrysalis-20261010_120000.log"
    legacy.write_bytes(COMPLETION)
    link = source / "simboard-ingestion-staging-test-offline-20261009_120000-1.log"
    link.symlink_to(unrelated)
    (source / "subdirectory").mkdir()
    before = _snapshot(source)
    archiver.archive_logs(source, archive, now=NOW, dry_run=False)
    assert _snapshot(source) == before
    assert all(path.exists() for path in (incomplete, invalid, unrelated, legacy, link))
    assert "Skipping invalid log date" in capsys.readouterr().out


def test_updates_preserve_members_and_remove_identical_duplicates(directories):
    source, archive = directories
    duplicate = _log(source)
    new = _log(source, "20261009", prefix="simboard-diagnostics-test-env.prod.sh")
    destination = archive / "20261004-20261010.tar.gz"
    expected = {duplicate.name: duplicate.read_bytes(), "previous.log": b"previous"}
    _tar(destination, expected)
    expected[new.name] = new.read_bytes()
    archiver.archive_logs(source, archive, now=NOW, dry_run=False)
    assert _contents(destination) == expected
    assert not list(source.iterdir())
    # A retry with an identical extracted file does not rebuild the archive.
    duplicate.write_bytes(expected[duplicate.name])
    original = destination.read_bytes()
    archiver.archive_logs(source, archive, now=NOW, dry_run=False)
    assert destination.read_bytes() == original
    assert not duplicate.exists()


def test_conflict_preserves_source_and_archive(directories):
    source, archive = directories
    path = _log(source)
    later = _log(source, "20261011")
    destination = archive / "20261004-20261010.tar.gz"
    _tar(destination, {path.name: b"different"})
    before = destination.read_bytes()
    with pytest.raises(ValueError, match="Conflicting archive member"):
        archiver.archive_logs(source, archive, now=NOW, dry_run=False)
    assert path.exists()
    assert later.exists()
    assert not (archive / "20261011-20261017.tar.gz").exists()
    assert destination.read_bytes() == before


@pytest.mark.parametrize("failure", ["write", "verify", "replace"])
def test_failed_publication_preserves_sources_and_previous_archive(
    directories, monkeypatch, failure
):
    source, archive = directories
    path = _log(source)
    destination = archive / "20261004-20261010.tar.gz"
    _tar(destination, {"previous.log": b"previous"})
    before = destination.read_bytes()
    if failure == "write":
        monkeypatch.setattr(archiver, "_write_archive", _fail)
    elif failure == "verify":
        monkeypatch.setattr(
            archiver,
            "_archive_hashes",
            Mock(side_effect=[archiver._archive_hashes(destination), {}]),
        )
    else:
        monkeypatch.setattr(Path, "replace", _fail)
    with pytest.raises((OSError, ValueError)):
        archiver.archive_logs(source, archive, now=NOW, dry_run=False)
    assert path.exists()
    assert destination.read_bytes() == before
    assert not list(archive.glob("*.tmp"))


def test_corrupt_archive_preserves_source(directories):
    source, archive = directories
    path = _log(source)
    (archive / "20261004-20261010.tar.gz").write_bytes(b"corrupt")
    with pytest.raises(tarfile.TarError):
        archiver.archive_logs(source, archive, now=NOW, dry_run=False)
    assert path.exists()


def test_changed_source_is_not_deleted(directories, monkeypatch):
    source, archive = directories
    path = _log(source)
    original = archiver._publish_archive
    monkeypatch.setattr(
        archiver, "_publish_archive", partial(_publish_then_change, original, path)
    )
    with pytest.raises(ValueError, match="Log changed; source preserved"):
        archiver.archive_logs(source, archive, now=NOW, dry_run=False)
    assert path.read_bytes() == b"changed\n" + COMPLETION


def test_cleanup_failure_can_be_retried(directories):
    source, archive = directories
    path = _log(source)
    with patch.object(
        Path,
        "unlink",
        autospec=True,
        side_effect=partial(_fail_source_unlink, path, Path.unlink),
    ):
        with pytest.raises(OSError, match="injected failure"):
            archiver.archive_logs(source, archive, now=NOW, dry_run=False)
    assert path.exists()
    archiver.archive_logs(source, archive, now=NOW, dry_run=False)
    assert not path.exists()


def test_live_runs_require_exclusive_lock(directories):
    source, archive = directories
    path = _log(source)
    with (archive / ".archive_ingestion_logs.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            archiver.archive_logs(source, archive, now=NOW, dry_run=False)
    assert path.exists()


def test_empty_input(directories):
    source, archive = directories
    archiver.archive_logs(source, archive, now=NOW, dry_run=False)
    assert not list(archive.glob("*.tar.gz"))


def test_changed_source_before_write_preserves_previous_archive(
    directories, monkeypatch
):
    source, archive = directories
    path = _log(source)
    destination = archive / "20261004-20261010.tar.gz"
    _tar(destination, {"previous.log": b"previous"})
    before = destination.read_bytes()
    monkeypatch.setattr(
        archiver,
        "_write_archive",
        partial(_change_then_write, path, archiver._write_archive),
    )
    with pytest.raises(ValueError, match="Log changed before archiving"):
        archiver.archive_logs(source, archive, now=NOW, dry_run=False)
    assert path.exists()
    assert destination.read_bytes() == before


@pytest.mark.parametrize("kind", ["directory", "link", "duplicate"])
def test_unsupported_archive_members_preserve_source(directories, kind):
    source, archive = directories
    path = _log(source)
    destination = archive / "20261004-20261010.tar.gz"
    with tarfile.open(destination, "w:gz") as output:
        member = tarfile.TarInfo("entry")
        if kind == "directory":
            member.type = tarfile.DIRTYPE
        elif kind == "link":
            member.type = tarfile.SYMTYPE
            member.linkname = "elsewhere"
        output.addfile(member)
        if kind == "duplicate":
            output.addfile(member)
    before = destination.read_bytes()
    with pytest.raises(ValueError):
        archiver.archive_logs(source, archive, now=NOW, dry_run=False)
    assert path.exists()
    assert destination.read_bytes() == before


def test_archive_symlink_is_rejected(directories, tmp_path):
    source, archive = directories
    path = _log(source)
    target = tmp_path / "target.tar.gz"
    _tar(target, {"previous.log": b"previous"})
    (archive / "20261004-20261010.tar.gz").symlink_to(target)
    before = target.read_bytes()
    with pytest.raises(ValueError, match="Archive must not be a symlink"):
        archiver.archive_logs(source, archive, now=NOW, dry_run=False)
    assert path.exists()
    assert target.read_bytes() == before


@pytest.mark.parametrize("kind", ["missing", "same", "symlink"])
def test_invalid_directories_fail_without_mutation(directories, kind):
    source, archive = directories
    if kind == "missing":
        archive.rmdir()
    elif kind == "same":
        archive = source
    else:
        archive.rmdir()
        archive.symlink_to(source, target_is_directory=True)
    before = _snapshot(source.parent)
    with pytest.raises(ValueError):
        archiver.archive_logs(source, archive, now=NOW, dry_run=False)
    assert _snapshot(source.parent) == before


def _log(
    directory,
    day="20261010",
    *,
    prefix="simboard-ingestion-staging-test-offline",
    contents=COMPLETION,
):
    path = directory / f"{prefix}-{day}_120000-1.log"
    path.write_bytes(contents)

    return path


def _snapshot(directory):
    snapshot = {}
    for path in directory.rglob("*"):
        contents = None
        if path.is_symlink():
            contents = path.readlink()
        elif path.is_file():
            contents = path.read_bytes()
        snapshot[str(path.relative_to(directory))] = contents

    return snapshot


def _tar(path, members):
    with tarfile.open(path, "w:gz") as archive:
        for name, contents in members.items():
            member = tarfile.TarInfo(name)
            member.size = len(contents)
            archive.addfile(member, io.BytesIO(contents))


def _contents(path):
    with tarfile.open(path, "r:gz") as archive:
        return {member.name: archive.extractfile(member).read() for member in archive}


def _fail(*args, **kwargs):
    raise OSError("injected failure")


def _publish_then_change(original, path, *args):
    original(*args)
    path.write_bytes(b"changed\n" + COMPLETION)


def _change_then_write(path, original, *args):
    path.write_bytes(b"changed\n" + COMPLETION)
    original(*args)


def _fail_source_unlink(source, original, path, *args, **kwargs):
    if path == source:
        _fail()
    original(path, *args, **kwargs)
