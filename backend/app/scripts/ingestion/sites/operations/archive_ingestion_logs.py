#!/usr/bin/env python3
"""Archive completed launcher logs into Sunday–Saturday UTC week blocks."""

import argparse
import fcntl
import hashlib
import os
import re
import stat
import sys
import tarfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

FILENAME_PATTERN = re.compile(
    r"simboard-(?:ingestion-(?:staging|archive|unknown)|diagnostics)-"
    r"[a-z0-9_-]+-[a-zA-Z0-9._-]+-(?P<date>[0-9]{8})_[0-9]{6}-[0-9]+\.log"
)
COMPLETION_PATTERN = re.compile(
    rb"(?:^|\n)\[[0-9T:Z-]+\] event=launcher_finished exit_code=[0-9]+\n?$"
)


@dataclass(frozen=True)
class _Log:
    path: Path
    signature: tuple[int, ...]
    digest: str
    completed: bool


def main(argv: list[str] | None = None) -> int:
    """Read cron configuration and report failures without deleting inputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--archive-dir", type=Path)
    parser.add_argument(
        "--dry-run", action="store_true", help="Override DRY_RUN safely."
    )
    args = parser.parse_args(argv)
    try:
        dry_run = _dry_run_requested() or args.dry_run
        retention_days = int(os.environ.get("LOG_RETENTION_DAYS", "7"))
        root = os.environ.get("SIMBOARD_ROOT", "").strip()
        if not root and (args.source_dir is None or args.archive_dir is None):
            raise ValueError("SIMBOARD_ROOT or both directory options must be set")
        operations = Path(root) / "operations"
        os.umask(0o027)
        archive_logs(
            args.source_dir or operations / "raw_logs",
            args.archive_dir or operations / "history_logs",
            retention_days=retention_days,
            dry_run=dry_run,
        )
    except (OSError, ValueError, tarfile.TarError, EOFError) as error:
        print(f"Log archiving failed: {error}", file=sys.stderr)
        return 1

    return 0


def archive_logs(
    source_dir: Path,
    archive_dir: Path,
    *,
    retention_days: int = 7,
    dry_run: bool = True,
    now: datetime | None = None,
) -> None:
    """Archive eligible weeks, then delete only verified, unchanged sources.

    Directories must already exist. Dry runs do not create a lock or write files.
    """
    if retention_days < 0:
        raise ValueError("LOG_RETENTION_DAYS must be nonnegative")
    for directory in (source_dir, archive_dir):
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError(
                f"Expected an existing, non-symlink directory: {directory}"
            )
    if source_dir.resolve() == archive_dir.resolve():
        raise ValueError("Source and archive directories must differ")
    today = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).date()
    cutoff = today - timedelta(days=retention_days)
    with _archive_lock(archive_dir, dry_run):
        weeks = _eligible_logs(source_dir, cutoff)
        for sunday, logs in sorted(weeks.items()):
            saturday = sunday + timedelta(days=6)
            destination = archive_dir / f"{sunday:%Y%m%d}-{saturday:%Y%m%d}.tar.gz"
            _archive_week(destination, logs, dry_run)


def _dry_run_requested() -> bool:
    value = os.environ.get("DRY_RUN", "true").strip().lower()
    if value not in {"1", "true", "yes", "on", "0", "false", "no", "off"}:
        raise ValueError("DRY_RUN must be a boolean")

    return value in {"1", "true", "yes", "on"}


@contextmanager
def _archive_lock(directory: Path, dry_run: bool) -> Iterator[None]:
    if dry_run:
        yield
        return
    descriptor = os.open(
        directory / ".archive_ingestion_logs.lock",
        os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
        0o660,
    )
    with os.fdopen(descriptor, "r+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def _eligible_logs(source_dir: Path, cutoff: date) -> dict[date, list[_Log]]:
    weeks: dict[date, list[_Log]] = {}
    for path in sorted(source_dir.iterdir()):
        match = FILENAME_PATTERN.fullmatch(path.name)
        if path.is_symlink() or not path.is_file() or match is None:
            print(f"Skipping unrelated or unsupported input: {path.name}")
            continue
        try:
            log_date = datetime.strptime(match["date"], "%Y%m%d").date()
        except ValueError:
            print(f"Skipping invalid log date: {path.name}")
            continue
        sunday = log_date - timedelta(days=(log_date.weekday() + 1) % 7)
        if sunday + timedelta(days=7) > cutoff:
            print(f"Skipping recent week: {path.name}")
            continue
        log = _inspect_log(path)
        if not log.completed:
            print(f"Skipping incomplete log: {path.name}")
            continue
        weeks.setdefault(sunday, []).append(log)

    return weeks


def _inspect_log(path: Path) -> _Log:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"Not a regular log: {path}")
        digest = hashlib.sha256()
        tail = b""
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
            tail = (tail + chunk)[-256:]
        signature = _signature(before)
        if signature != _signature(os.fstat(source.fileno())):
            raise ValueError(f"Log changed while reading: {path}")

    return _Log(
        path, signature, digest.hexdigest(), bool(COMPLETION_PATTERN.search(tail))
    )


def _signature(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _archive_week(destination: Path, logs: list[_Log], dry_run: bool) -> None:
    if destination.is_symlink():
        raise ValueError(f"Archive must not be a symlink: {destination}")
    expected = _archive_hashes(destination) if destination.exists() else {}
    additions = []
    for log in logs:
        name = log.path.name
        if name in expected and expected[name] != log.digest:
            raise ValueError(f"Conflicting archive member; source preserved: {name}")
        if name not in expected:
            additions.append(log)
        expected[name] = log.digest
    if dry_run:
        print(
            f"Would archive {len(additions)} new log(s), then remove {len(logs)} source(s): {destination}"
        )
        return
    if additions:
        _publish_archive(destination, additions, expected)
    for log in logs:
        if _inspect_log(log.path) != log:
            raise ValueError(f"Log changed; source preserved: {log.path}")
        log.path.unlink()
    print(
        f"Archived {len(additions)} new log(s), removed {len(logs)} source(s): {destination}"
    )


def _archive_hashes(path: Path) -> dict[str, str]:
    hashes = {}
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            if not member.isfile() or Path(member.name).name != member.name:
                raise ValueError(f"Unsupported archive member: {member.name}")
            if member.name in hashes:
                raise ValueError(f"Duplicate archive member: {member.name}")
            source = archive.extractfile(member)
            if source is None:
                raise ValueError(f"Unreadable archive member: {member.name}")
            with source:
                digest = hashlib.sha256()
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
                hashes[member.name] = digest.hexdigest()

    return hashes


def _publish_archive(
    destination: Path, logs: list[_Log], expected: dict[str, str]
) -> None:
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    try:
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o660)
        with os.fdopen(descriptor, "w+b") as output:
            _write_archive(output, destination, logs)
            output.flush()
            os.fsync(output.fileno())
        if _archive_hashes(temporary) != expected:
            raise ValueError(f"Archive verification failed: {destination}")
        temporary.replace(destination)
        descriptor = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def _write_archive(output: BinaryIO, destination: Path, logs: list[_Log]) -> None:
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        if destination.exists():
            with tarfile.open(destination, "r:gz") as previous:
                for member in previous:
                    source = previous.extractfile(member)
                    if source is None:
                        raise ValueError(f"Unreadable archive member: {member.name}")
                    with source:
                        archive.addfile(member, source)
        for log in logs:
            descriptor = os.open(log.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as source:
                if _signature(os.fstat(source.fileno())) != log.signature:
                    raise ValueError(f"Log changed before archiving: {log.path}")
                member = tarfile.TarInfo(log.path.name)
                member.size = log.signature[2]
                member.mode = 0o640
                member.mtime = log.signature[3] / 1_000_000_000
                archive.addfile(member, source)


if __name__ == "__main__":
    sys.exit(main())
