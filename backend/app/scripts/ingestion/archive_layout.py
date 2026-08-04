"""Archive layout, path filtering, identity, and snapshot helpers."""

from __future__ import annotations

import re
from functools import partial
from pathlib import Path
from typing import Callable

from app.scripts.ingestion.archive_ingestor_core import (
    DEFAULT_OLD_PERF_ARCHIVE_ROOT,
    DEFAULT_PERF_ARCHIVE_ROOT,
    IngestorConfig,
    UnsupportedArchiveLayoutError,
)

ARCHIVE_YEAR_DIR_PATTERN = re.compile(r"^(?P<year>\d{4})-(?P<month>\d{2})$")
ARCHIVE_SNAPSHOT_DIR_PATTERN = re.compile(
    r"^performance_archive_\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2}$"
)
# When snapshot layouts use status buckets, scan only COMPLETED cases.
ARCHIVE_COMPLETED_STATUS_DIR_NAME = "COMPLETED"
KNOWN_ARCHIVE_ROOT_BASENAMES = frozenset(
    {Path(DEFAULT_PERF_ARCHIVE_ROOT).name, Path(DEFAULT_OLD_PERF_ARCHIVE_ROOT).name}
)


def _build_case_path_filter(
    config: IngestorConfig,
) -> Callable[[Path], bool] | None:
    """Return optional case-path filter for archive backfills."""
    if (
        config.scan_mode != "archive"
        or config.archive_year_start is None
        and config.archive_year_end is None
    ):
        return None

    return partial(
        _archive_case_path_matches_range,
        archive_root=config.archive_root,
        archive_start=config.archive_year_start,
        archive_end=config.archive_year_end,
    )


def _build_walk_dir_filter(
    config: IngestorConfig,
    *,
    selected_snapshot_keys: set[str] | None = None,
) -> Callable[[str, list[str]], None] | None:
    """Return optional top-level directory pruning hook."""
    if config.scan_mode != "archive":
        return None

    return partial(
        _filter_archive_walk_dirnames,
        archive_root=config.archive_root.resolve(),
        archive_start=config.archive_year_start,
        archive_end=config.archive_year_end,
        archive_year_filter_enabled=_archive_year_filter_enabled(
            config.archive_year_start,
            config.archive_year_end,
        ),
        selected_snapshot_keys=selected_snapshot_keys,
    )


def _filter_archive_walk_dirnames(
    dirpath: str,
    dirnames: list[str],
    *,
    archive_root: Path,
    archive_start: str | None,
    archive_end: str | None,
    archive_year_filter_enabled: bool,
    selected_snapshot_keys: set[str] | None = None,
) -> None:
    """Prune walked directories for supported archive layouts and ranges."""
    current_path = Path(dirpath).resolve()

    if current_path == archive_root:
        _prune_archive_root_dirnames(
            dirnames,
            archive_root=archive_root,
            archive_start=archive_start,
            archive_end=archive_end,
        )
        return

    relative_parts = _archive_relative_parts(current_path, archive_root)
    if (
        selected_snapshot_keys is not None
        and relative_parts is not None
        and len(relative_parts) == 1
        and _archive_dir_bucket(relative_parts[0]) is not None
    ):
        archive_month = relative_parts[0]
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if f"{archive_month}/{dirname}" in selected_snapshot_keys
        ]
        return

    if _is_archive_snapshot_dir(current_path.name):
        _prune_archive_snapshot_dirnames(dirnames)

    if not archive_year_filter_enabled:
        return

    relative_parts = _archive_relative_parts(current_path, archive_root)
    if relative_parts is None or _archive_parts_bucket(relative_parts) is not None:
        return

    _prune_dirnames_to_archive_range(
        dirnames,
        archive_start=archive_start,
        archive_end=archive_end,
    )


def _archive_year_filter_enabled(
    archive_start: str | None,
    archive_end: str | None,
) -> bool:
    """Return whether archive-year pruning is enabled."""
    return archive_start is not None or archive_end is not None


def _prune_archive_root_dirnames(
    dirnames: list[str],
    *,
    archive_root: Path,
    archive_start: str | None,
    archive_end: str | None,
) -> None:
    """Restrict archive-root walk to supported archive year buckets."""
    root_dirnames = _read_archive_root_dirnames(archive_root)
    archive_dirnames = [
        dirname for dirname in root_dirnames if _archive_dir_bucket(dirname) is not None
    ]
    _validate_archive_root_layout(
        archive_root,
        root_dirnames=root_dirnames,
        archive_dirnames=archive_dirnames,
        archive_start=archive_start,
        archive_end=archive_end,
    )

    selected_dirnames = archive_dirnames
    if _archive_year_filter_enabled(archive_start, archive_end):
        selected_dirnames = [
            dirname
            for dirname in archive_dirnames
            if _archive_dir_in_range(
                dirname,
                archive_start=archive_start,
                archive_end=archive_end,
            )
        ]

    dirnames[:] = [dirname for dirname in dirnames if dirname in selected_dirnames]


def _read_archive_root_dirnames(archive_root: Path) -> list[str]:
    """Return non-symlink directory names directly under archive root."""
    try:
        return [
            child.name
            for child in archive_root.iterdir()
            if child.is_dir() and not child.is_symlink()
        ]
    except OSError as exc:
        raise UnsupportedArchiveLayoutError(
            f"Unable to read archive root {archive_root}: "
            f"{exc.__class__.__name__}: {exc}"
        ) from exc


def _validate_archive_root_layout(
    archive_root: Path,
    *,
    root_dirnames: list[str],
    archive_dirnames: list[str],
    archive_start: str | None,
    archive_end: str | None,
) -> None:
    """Validate that year-filtered archive walks start at YYYY-MM bucket root."""
    if not _archive_year_filter_enabled(archive_start, archive_end):
        return

    if root_dirnames and not archive_dirnames:
        raise UnsupportedArchiveLayoutError(
            "ARCHIVE_YEAR_START and ARCHIVE_YEAR_END require archive paths to "
            f"include a YYYY-MM directory under {archive_root}"
        )


def _archive_relative_parts(
    current_path: Path,
    archive_root: Path,
) -> tuple[str, ...] | None:
    """Return path parts relative to archive root when inside that root."""
    try:
        return current_path.relative_to(archive_root).parts
    except ValueError:
        return None


def _prune_dirnames_to_archive_range(
    dirnames: list[str],
    *,
    archive_start: str | None,
    archive_end: str | None,
) -> None:
    """Keep only child dirs that fall within configured archive range."""
    dirnames[:] = [
        dirname
        for dirname in dirnames
        if _archive_dir_in_range(
            dirname,
            archive_start=archive_start,
            archive_end=archive_end,
        )
    ]


def _prune_archive_snapshot_dirnames(dirnames: list[str]) -> None:
    """Drop non-completed status buckets from snapshot-root walks."""
    if not _snapshot_uses_status_buckets(dirnames):
        return

    dirnames[:] = [
        dirname for dirname in dirnames if dirname == ARCHIVE_COMPLETED_STATUS_DIR_NAME
    ]


def _snapshot_uses_status_buckets(dirnames: list[str]) -> bool:
    """Return whether a snapshot root is bucketed by execution status."""
    if ARCHIVE_COMPLETED_STATUS_DIR_NAME not in dirnames:
        return False

    return any(dirname != ARCHIVE_COMPLETED_STATUS_DIR_NAME for dirname in dirnames)


def _archive_case_path_matches_range(
    case_path: Path,
    *,
    archive_root: Path,
    archive_start: str | None,
    archive_end: str | None,
) -> bool:
    """Return whether an archive case path belongs to selected archive buckets."""
    if archive_start is None and archive_end is None:
        return True

    try:
        relative_parts = case_path.resolve().relative_to(archive_root.resolve()).parts
    except ValueError:
        return False

    archive_bucket = _archive_parts_bucket(relative_parts)
    if archive_bucket is None:
        raise UnsupportedArchiveLayoutError(
            "ARCHIVE_YEAR_START and ARCHIVE_YEAR_END require archive paths to "
            f"include a YYYY-MM directory under {archive_root}: {case_path}"
        )

    if archive_start is not None and archive_bucket < archive_start:
        return False
    if archive_end is not None and archive_bucket > archive_end:
        return False

    return True


def _archive_parts_bucket(relative_parts: tuple[str, ...]) -> str | None:
    """Return first normalized YYYY-MM archive bucket from relative path parts."""
    for part in relative_parts:
        archive_bucket = _archive_dir_bucket(part)
        if archive_bucket is not None:
            return archive_bucket

    return None


def _archive_dir_bucket(dirname: str) -> str | None:
    """Return normalized YYYY-MM archive bucket for a valid archive dirname."""
    match = ARCHIVE_YEAR_DIR_PATTERN.fullmatch(dirname)
    if match is None:
        return None

    month = int(match.group("month"))
    if month < 1 or month > 12:
        return None

    return f"{match.group('year')}-{match.group('month')}"


def _archive_dir_in_range(
    dirname: str,
    *,
    archive_start: str | None,
    archive_end: str | None,
) -> bool:
    """Return whether a top-level archive dirname falls within archive bounds."""
    archive_bucket = _archive_dir_bucket(dirname)
    if archive_bucket is None:
        return False

    if archive_start is not None and archive_bucket < archive_start:
        return False
    if archive_end is not None and archive_bucket > archive_end:
        return False

    return True


def _case_identity_key(
    case_path: str,
    scan_mode: str,
    *,
    staging_root_basename: str = Path(DEFAULT_PERF_ARCHIVE_ROOT).name,
) -> str:
    """Return dedupe key for a discovered case path."""
    if scan_mode != "archive":
        case_parts = _staging_case_identity_parts(
            Path(case_path), staging_root_basename=staging_root_basename
        )
        if case_parts:
            return "/".join(case_parts)

        return case_path

    case_parts = _archive_case_identity_parts(Path(case_path))
    if case_parts:
        return "/".join(case_parts)

    return case_path


def _archive_case_identity_parts(case_path: Path) -> tuple[str, ...]:
    """Return logical case tail used to dedupe archive snapshots."""
    path_parts = _path_parts_without_anchor(case_path)
    if not path_parts:
        return ()

    year_index = _archive_year_part_index(path_parts)
    if year_index is not None:
        logical_parts = list(path_parts[year_index + 1 :])
        if logical_parts and _is_archive_snapshot_dir(logical_parts[0]):
            logical_parts = logical_parts[1:]
        if logical_parts and logical_parts[0] == ARCHIVE_COMPLETED_STATUS_DIR_NAME:
            logical_parts = logical_parts[1:]
        if logical_parts:
            return tuple(logical_parts)

    if path_parts[0] in KNOWN_ARCHIVE_ROOT_BASENAMES and len(path_parts) > 1:
        return tuple(path_parts[1:])

    if len(path_parts) >= 2:
        return tuple(path_parts[-2:])

    return tuple(path_parts)


def _staging_case_identity_parts(
    case_path: Path,
    *,
    staging_root_basename: str,
) -> tuple[str, ...]:
    """Return logical case tail used to dedupe staging paths across mounts."""
    path_parts = _path_parts_without_anchor(case_path)
    if not path_parts:
        return ()

    try:
        root_index = path_parts.index(staging_root_basename)
    except ValueError:
        return ()

    logical_parts = path_parts[root_index + 1 :]
    if not logical_parts:
        return ()

    return tuple(logical_parts)


def _path_parts_without_anchor(path: Path) -> tuple[str, ...]:
    """Return path parts without filesystem anchor."""
    return tuple(part for part in path.parts if part != path.anchor)


def _archive_year_part_index(path_parts: tuple[str, ...]) -> int | None:
    """Return index of first YYYY-MM archive bucket in path parts."""
    for index, part in enumerate(path_parts):
        if _archive_dir_bucket(part) is not None:
            return index

    return None


def _is_archive_snapshot_dir(dirname: str) -> bool:
    """Return whether dirname is archive-only snapshot bucket."""
    return ARCHIVE_SNAPSHOT_DIR_PATTERN.fullmatch(dirname) is not None


def _enumerate_archive_snapshot_keys(config: IngestorConfig) -> set[str]:
    """List eligible immediate ``YYYY-MM/performance_archive_*`` snapshots."""
    keys: set[str] = set()

    try:
        for month_dir in config.archive_root.iterdir():
            if (
                not month_dir.is_dir()
                or month_dir.is_symlink()
                or not _archive_dir_in_range(
                    month_dir.name,
                    archive_start=config.archive_year_start,
                    archive_end=config.archive_year_end,
                )
            ):
                continue
            for snapshot_dir in month_dir.iterdir():
                if (
                    snapshot_dir.is_dir()
                    and not snapshot_dir.is_symlink()
                    and _is_archive_snapshot_dir(snapshot_dir.name)
                ):
                    keys.add(f"{month_dir.name}/{snapshot_dir.name}")
    except OSError as exc:
        raise UnsupportedArchiveLayoutError(
            f"Unable to enumerate archive snapshots under {config.archive_root}: "
            f"{exc.__class__.__name__}: {exc}"
        ) from exc

    return keys


def _record_archive_snapshot_reference(
    case_dir: Path,
    execution_id: str,
    *,
    archive_root: Path,
    references_by_key: dict[str, set[tuple[str, str]]],
) -> None:
    """Associate a discovered execution identity with its immutable snapshot."""
    try:
        relative_parts = case_dir.resolve().relative_to(archive_root).parts
    except ValueError:
        return

    if (
        len(relative_parts) < 3
        or _archive_dir_bucket(relative_parts[0]) is None
        or not _is_archive_snapshot_dir(relative_parts[1])
    ):
        return

    snapshot_key = f"{relative_parts[0]}/{relative_parts[1]}"
    references_by_key.setdefault(snapshot_key, set()).add(
        (
            _case_identity_key(str(case_dir.resolve()), "archive"),
            execution_id,
        )
    )
