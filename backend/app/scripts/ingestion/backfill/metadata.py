"""Backfill observed directories without ingestion or checkpoint writes."""

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit

from app.common.utils import _normalize_hpc_username
from app.features.ingestion.ingest import _normalize_path_candidate, _parse_date_field
from app.features.ingestion.parsers.parser import (
    FILE_SPECS,
    _find_casedocs_dirs,
    _find_spec_matches,
    _parse_all_files,
)
from app.features.ingestion.schemas import SourceDirectoryObservation
from app.features.ingestion.v3_classification import (
    CHRYSALIS_MACHINE_NAME,
    V3_CASE_NAMES,
)
from app.features.machine.utils import parse_machine_name
from app.scripts.ingestion.archive_client import (
    _build_json_request,
    _http_request_error,
    _normalized_api_base_url,
    _read_json_object_response,
    _retry_backoff_seconds,
    _timeout_request_error,
    _url_request_error,
)
from app.scripts.ingestion.archive_ingestor_core import (
    DISCOVERY_PROGRESS_LOG_EVERY_DIRECTORIES,
    IngestionRequestError,
    _log_event,
    _optional_source_root,
)
from app.scripts.ingestion.archive_ingestor_core import logger as ingestion_logger
from app.scripts.ingestion.archive_layout import _filter_archive_walk_dirnames
from app.scripts.ingestion.nersc_archive_ingestor import _prune_staging_walk_dirnames
from app.scripts.ingestion.v3_data.lcrc_v3_archive_ingestor import (
    CHRYSALIS_ARCHIVE_ROOT,
    V3_ARCHIVE_YEAR_START,
)

FIELD_NAMES = {
    "simulation-dates": ("simulation_start_date", "simulation_end_date"),
    "run-script": ("run_script",),
}


class _IncompleteExecutionError(ValueError):
    """An execution lacks a required identity file for backfill."""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--machine", required=True)
    parser.add_argument(
        "--v3",
        action="store_true",
        help="Limit backfill to Chrysalis v3 production cases",
    )
    parser.add_argument(
        "--fields",
        nargs="+",
        choices=["source-directories", "simulation-dates", "run-script"],
        required=True,
    )
    parser.add_argument(
        "--sources", choices=["staging", "archive", "both"], default="both"
    )
    parser.add_argument("--staging-root", type=Path)
    parser.add_argument("--archive-root", type=Path)
    parser.add_argument("--archive-start")
    parser.add_argument("--archive-end")
    parser.add_argument("--case-name")
    parser.add_argument("--hpc-username")
    parser.add_argument("--overwrite", action="store_true")

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    _resolve_source_defaults(args)
    _validate_sources(parser, args)

    api = os.environ.get("SIMBOARD_API_BASE_URL", "")
    token = os.environ.get("SIMBOARD_API_TOKEN", "")
    if not api or not token:
        parser.error(
            "SIMBOARD_API_BASE_URL and SIMBOARD_API_TOKEN are required, including for dry runs"
        )

    api = _normalized_api_base_url(api)
    target = urlsplit(api)
    if target.username or target.password or target.query or target.fragment:
        parser.error("API_BASE_URL must not contain credentials, query, or fragment")
    if target.scheme not in ("http", "https") or not target.hostname:
        parser.error("API_BASE_URL must be an HTTP(S) URL")

    scope = {"api": api, "sources": args.sources, "dry_run": not args.apply}
    if args.v3:
        scope["v3"] = True
    if args.fields == ["source-directories"]:
        scope.update(
            staging_root=str(args.staging_root) if args.staging_root else None,
            archive_root=str(args.archive_root) if args.archive_root else None,
            archive_start=args.archive_start,
            archive_end=args.archive_end,
        )
    print(json.dumps(scope))

    return (
        _bootstrap(args, api, token)
        if args.fields == ["source-directories"]
        else _backfill_metadata(args, api, token)
    )


def _read_execution(path: Path, machine: str | None, fields: list[str]):
    """Read only identity files and requested metadata, not full ingestion input.

    Enforce the expected machine when provided; bootstrap accepts any source machine.
    """
    keys = ["case_docs_env_case", "e3sm_timing"]

    if "simulation-dates" in fields:
        keys.extend(["case_docs_env_run", "cpl_log"])

    files = {}
    directories = _find_casedocs_dirs(str(path))
    watched = [path, *(Path(directory) for directory in directories)]
    watched.extend(
        child
        for directory in list(watched)
        for child in directory.iterdir()
        if child.is_file()
    )
    before = [(item.stat().st_mtime_ns, item.stat().st_size) for item in watched]

    for key in keys:
        matches = _find_spec_matches(str(path), directories, FILE_SPECS[key])
        if len(matches) > 1:
            raise ValueError(f"Ambiguous {key}: {path}")
        if not matches and key in ("case_docs_env_case", "e3sm_timing"):
            raise _IncompleteExecutionError(f"Missing identity file {key}: {path}")
        files[key] = matches[0] if matches else None

    timing_identity = FILE_SPECS["e3sm_timing"]["parser"](files["e3sm_timing"])
    if timing_identity.get("execution_id") != path.name:
        raise ValueError(f"Timing identity does not match execution directory: {path}")

    parsed = _parse_all_files(str(path), files)

    if before != [(item.stat().st_mtime_ns, item.stat().st_size) for item in watched]:
        raise ValueError(f"Source changed while reading: {path}")
    source_machine, _ = parse_machine_name(parsed.machine or "")
    if not source_machine:
        raise ValueError(f"Source machine is missing: {path}")
    if machine is not None and source_machine != parse_machine_name(machine)[0]:
        raise ValueError(f"Machine mismatch: {path}")
    if not parsed.case_name or not _normalize_hpc_username(parsed.hpc_username):
        raise ValueError(f"Missing case identity: {path}")

    return parsed


def _request(
    api: str, token: str, route: str, payload: dict[str, Any] | None = None
) -> dict:
    """Use the ingestion client's error classification and retry policy."""
    req = (
        _build_json_request(f"{api}/{route}", token, payload)
        if payload is not None
        else urllib.request.Request(
            f"{api}/{route}", headers={"Authorization": f"Bearer {token}"}
        )
    )

    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return _read_json_object_response(response)
        except urllib.error.HTTPError as exc:
            error = _http_request_error(exc)
        except urllib.error.URLError as exc:
            error = _url_request_error(exc)
        except TimeoutError:
            error = _timeout_request_error()

        if not error.transient or attempt == 3:
            raise error

        delay = _retry_backoff_seconds(attempt)
        _log_event(
            "backfill_api_retry",
            {
                "attempt": attempt,
                "status_code": error.status_code,
                "delay_seconds": delay,
            },
        )
        time.sleep(delay)

    raise RuntimeError("Unreachable request retry state")


def _raise_walk_error(error: OSError) -> None:
    raise error


def _execution_paths(root: Path, kind: str, args: argparse.Namespace):
    """Traverse supported layouts without reading ingestion skip state."""
    started_at = time.monotonic()
    progress = {
        "source": kind,
        "root": str(root),
        "current_dir": str(root),
        "directories_visited": 0,
        "matching_executions": 0,
        "case_name": args.case_name,
        "hpc_username": args.hpc_username,
    }
    traversal_complete = False
    _log_scan_progress("backfill_scan_started", progress, started_at)

    try:
        if not root.is_dir():
            raise ValueError(f"Source root is not a directory: {root}")

        for current, dirs, _ in os.walk(root, onerror=_raise_walk_error):
            path = Path(current)
            progress["current_dir"] = current
            progress["directories_visited"] += 1
            dirs[:] = sorted(name for name in dirs if not (path / name).is_symlink())

            if kind == "staging":
                _prune_staging_walk_dirnames(current, dirs, archive_root=root)
            elif kind == "archive":
                _filter_archive_walk_dirnames(
                    current,
                    dirs,
                    archive_root=root,
                    archive_start=args.archive_start,
                    archive_end=args.archive_end,
                    archive_year_filter_enabled=bool(
                        args.archive_start or args.archive_end
                    ),
                )

            if (
                progress["directories_visited"]
                % DISCOVERY_PROGRESS_LOG_EVERY_DIRECTORIES
                == 0
            ):
                _log_scan_progress("backfill_scan_progress", progress, started_at)

            if re.fullmatch(r"\d+\.\d{6}-\d{6}", path.name):
                dirs.clear()
                if (args.v3 and path.parent.name not in V3_CASE_NAMES) or (
                    args.case_name and path.parent.name != args.case_name
                ):
                    continue
                if args.hpc_username and path.parent.parent.name != args.hpc_username:
                    continue

                progress["matching_executions"] += 1
                yield path

        traversal_complete = True
    finally:
        _log_scan_progress(
            "backfill_scan_completed",
            {**progress, "traversal_complete": traversal_complete},
            started_at,
        )
        if traversal_complete and progress["matching_executions"] == 0:
            _log_scan_progress("backfill_scan_no_matches", progress, started_at)


def _log_scan_progress(event: str, progress: dict, started_at: float) -> None:
    _log_event(
        event,
        {**progress, "duration_seconds": round(time.monotonic() - started_at, 3)},
    )


def _bootstrap(args: argparse.Namespace, api: str, token: str) -> int:
    started_at = time.monotonic()
    failures = 0
    matched = 0
    skipped_no_owner = 0
    skipped_incomplete = 0

    for kind in ("staging", "archive"):
        if args.sources not in (kind, "both"):
            continue

        root = getattr(args, f"{kind}_root")

        if root is None:
            raise ValueError(f"--{kind}-root is required")

        try:
            for path in _execution_paths(root.resolve(), kind, args):
                try:
                    source = _bootstrap_observation(path, kind, args)
                    if source is None:
                        continue

                    machine_name, observation = source
                    result = _request(
                        api,
                        token,
                        "ingestions/source-directories",
                        {
                            "machine_name": machine_name,
                            "dry_run": not args.apply,
                            "directories": [observation.model_dump(mode="json")],
                        },
                    )
                    unresolved = bool(result["unresolved"])
                    matched += not unresolved
                    skipped_no_owner += unresolved

                    print(
                        json.dumps(
                            {
                                "path": str(path),
                                "outcome": "skipped_no_owner"
                                if unresolved
                                else "matched",
                                "dry_run": not args.apply,
                            }
                        )
                    )
                except _IncompleteExecutionError as exc:
                    skipped_incomplete += 1
                    print(
                        json.dumps(
                            {
                                "path": str(path),
                                "outcome": "skipped_incomplete",
                                "dry_run": not args.apply,
                                "error": str(exc),
                            }
                        )
                    )
                except (ValueError, OSError, IngestionRequestError) as exc:
                    failures += 1
                    print(
                        json.dumps(
                            {"path": str(path), "outcome": "failed", "error": str(exc)}
                        )
                    )
        except (ValueError, OSError) as exc:
            failures += 1
            print(
                json.dumps({"root": str(root), "outcome": "failed", "error": str(exc)})
            )

    print(
        json.dumps(
            {
                "matched": matched,
                "skipped_no_owner": skipped_no_owner,
                "skipped_incomplete": skipped_incomplete,
                "failed": failures,
            }
        )
    )
    _log_backfill_summary(
        args,
        [
            ("Existing owners matched", matched),
            ("Skipped without existing owner", skipped_no_owner),
            ("Skipped incomplete executions", skipped_incomplete),
            ("Read/parse/API/scan failures", failures),
        ],
        failures,
        started_at,
    )

    return int(bool(failures))


def _bootstrap_observation(
    path: Path, kind: str, args: argparse.Namespace
) -> tuple[str, SourceDirectoryObservation] | None:
    parsed = _read_execution(path, args.machine if args.v3 else None, [])

    if args.v3 and parsed.case_name not in V3_CASE_NAMES:
        return None

    if args.case_name and parsed.case_name != args.case_name:
        return None

    username = _normalize_hpc_username(parsed.hpc_username)

    if username is None:
        raise ValueError(f"Missing HPC username: {path}")
    if args.hpc_username and username != args.hpc_username:
        return None

    machine_name, _ = parse_machine_name(parsed.machine)

    return machine_name, SourceDirectoryObservation(
        case_name=parsed.case_name,
        hpc_username=username,
        execution_id=parsed.execution_id,
        kind=kind,
        case_path=str(path.parent),
        execution_path=str(path),
    )


def _observed_values(record: dict, args: argparse.Namespace) -> dict:
    if record["error"]:
        raise ValueError(record["error"])

    observations = []
    paths = sorted(
        {
            d["path"]
            for d in record["directories"]
            if args.sources in (d["kind"], "both")
        }
    )

    for path in paths:
        try:
            parsed = _read_execution(_source_path(path), args.machine, args.fields)

            if (
                parsed.case_name,
                _normalize_hpc_username(parsed.hpc_username),
                parsed.execution_id,
            ) != (record["case_name"], record["hpc_username"], record["execution_id"]):
                raise ValueError("Source identity does not match database owner")

            observations.append(
                {
                    "simulation_start_date": _normalized_date(
                        parsed.simulation_start_date
                    ),
                    "simulation_end_date": _normalized_date(parsed.simulation_end_date),
                    "run_script": _normalize_path_candidate(parsed.run_script_path),
                }
            )
        except (ValueError, OSError) as exc:
            raise ValueError(f"Cannot safely backfill from {path}: {exc}") from exc

    values = {}
    names = [name for group in args.fields for name in FIELD_NAMES[group]]

    for name in names:
        distinct = {o[name] for o in observations if o[name] is not None}
        if len(distinct) > 1:
            raise ValueError(f"Conflicting source values for {name}")
        if distinct:
            values[name] = distinct.pop()

    if not values:
        raise ValueError("No requested metadata from available mapped directories")

    return values


def _source_path(value: str) -> Path:
    """Translate legacy Spin mount prefixes to configured host source roots."""
    path = Path(value)
    for mount, env_name in (
        ("/performance_archive", "PERF_SOURCE_ROOT"),
        ("/OLD_PERF", "OLD_PERF_SOURCE_ROOT"),
    ):
        if not path.is_relative_to(mount):
            continue

        root = _optional_source_root(env_name)
        if root is not None:
            relative = path.relative_to(mount)
            if ".." in relative.parts:
                raise ValueError(f"Source path escapes configured root: {path}")

            return root / relative

    return path


def _normalized_date(value: str | None) -> str | None:
    parsed = _parse_date_field(value)
    if value and parsed is None:
        raise ValueError(f"Invalid source date: {value}")

    return parsed.isoformat() if parsed else None


def _backfill_metadata(args: argparse.Namespace, api: str, token: str) -> int:
    """Select database owners first, then read their observed source paths."""
    started_at = time.monotonic()
    failures = 0
    outcomes: dict[str, int] = {}
    offset = 0

    while True:
        query = {"machine_name": args.machine, "offset": offset, "limit": 100}
        if args.case_name:
            query["case_name"] = args.case_name
        if args.hpc_username:
            query["hpc_username"] = args.hpc_username

        try:
            records = _request(
                api, token, "ingestions/metadata-backfill?" + urlencode(query)
            )["records"]
        except IngestionRequestError as exc:
            print(json.dumps({"outcome": "failed", "error": str(exc)}))
            _log_metadata_summary(args, outcomes, failures + 1, started_at)

            return 1

        _log_event(
            "backfill_page_started",
            {"offset": offset, "records": len(records)},
        )

        for record in records:
            if args.v3 and record["case_name"] not in V3_CASE_NAMES:
                continue
            try:
                values = _observed_values(record, args)
                payload = {
                    name: record[name]
                    for name in (
                        "record_id",
                        "case_name",
                        "hpc_username",
                        "execution_id",
                    )
                }
                payload.update(
                    {
                        "machine_name": args.machine,
                        "fields": args.fields,
                        "values": values,
                        "expected": record["values"],
                        "overwrite": args.overwrite,
                        "dry_run": not args.apply,
                    }
                )
                result = _request(api, token, "ingestions/metadata-backfill", payload)
                outcomes[result["outcome"]] = outcomes.get(result["outcome"], 0) + 1
                print(json.dumps(result))
            except (ValueError, OSError, IngestionRequestError) as exc:
                failures += 1
                print(
                    json.dumps(
                        {
                            "record_id": record["record_id"],
                            "outcome": "failed",
                            "error": str(exc),
                        }
                    )
                )

        _log_event(
            "backfill_page_completed",
            {"offset": offset, "records": len(records), "failed_total": failures},
        )

        if len(records) < 100:
            break

        offset += len(records)

    print(json.dumps({**outcomes, "failed": failures}))
    _log_metadata_summary(args, outcomes, failures, started_at)

    return int(bool(failures))


def _log_metadata_summary(
    args: argparse.Namespace, outcomes: dict[str, int], failures: int, started_at: float
) -> None:
    _log_backfill_summary(
        args,
        [
            (
                "Records changed" if args.apply else "Records with planned changes",
                outcomes.get("changed", 0),
            ),
            ("Records unchanged", outcomes.get("unchanged", 0)),
            ("Record/request failures", failures),
        ],
        failures,
        started_at,
    )


def _log_backfill_summary(
    args: argparse.Namespace,
    counts: list[tuple[str, int]],
    failures: int,
    started_at: float,
) -> None:
    """Render readable totals alongside the existing machine-readable output."""
    ingestion_logger.info("RUN_SUMMARY Metadata backfill")
    ingestion_logger.info("RUN_SUMMARY Mode: %s", "apply" if args.apply else "dry run")
    for label, value in counts:
        ingestion_logger.info("RUN_SUMMARY %s: %s", label, value)
    if not args.apply:
        ingestion_logger.info("RUN_SUMMARY Database writes: disabled (dry run)")
    ingestion_logger.info(
        "RUN_SUMMARY Status: %s", "failure" if failures else "success"
    )
    ingestion_logger.info("RUN_SUMMARY Exit code: %s", int(bool(failures)))
    ingestion_logger.info(
        "RUN_SUMMARY Elapsed seconds: %.3f", time.monotonic() - started_at
    )


def _validate_sources(
    parser: argparse.ArgumentParser, args: argparse.Namespace
) -> None:
    _validate_v3_scope(parser, args)
    if "source-directories" in args.fields and len(args.fields) != 1:
        parser.error("Run source-directories separately before other metadata fields")

    for bound in (args.archive_start, args.archive_end):
        if bound and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", bound):
            parser.error("Archive bounds must use YYYY-MM")

    if (
        args.archive_start
        and args.archive_end
        and args.archive_start > args.archive_end
    ):
        parser.error("Archive start must not exceed end")

    if args.fields == ["source-directories"]:
        for kind in ("staging", "archive"):
            if args.sources in (kind, "both") and getattr(args, f"{kind}_root") is None:
                parser.error(f"--{kind}-root is required")
    elif (
        args.archive_start or args.archive_end or args.staging_root or args.archive_root
    ):
        parser.error(
            "Roots and archive bounds apply only to source-directories bootstrap"
        )


def _validate_v3_scope(
    parser: argparse.ArgumentParser, args: argparse.Namespace
) -> None:
    if not args.v3:
        return
    if args.machine != CHRYSALIS_MACHINE_NAME:
        parser.error("--v3 requires --machine chrysalis")
    if args.case_name and args.case_name not in V3_CASE_NAMES:
        parser.error("--case-name must be a documented v3 case when using --v3")


def _resolve_source_defaults(args: argparse.Namespace) -> None:
    """Use site defaults only for selected directory-bootstrap sources."""
    if args.fields != ["source-directories"]:
        return

    if args.sources in ("staging", "both") and args.staging_root is None:
        root = os.environ.get("PERF_ARCHIVE_ROOT", "").strip()
        args.staging_root = Path(root) if root else None

    if args.sources in ("archive", "both"):
        if args.archive_root is None:
            root = os.environ.get("OLD_PERF_ARCHIVE_ROOT", "").strip()
            if not root and args.v3:
                root = CHRYSALIS_ARCHIVE_ROOT
            args.archive_root = Path(root) if root else None
        if args.archive_start is None:
            args.archive_start = (
                os.environ.get("ARCHIVE_YEAR_START", "").strip()
                or (
                    V3_ARCHIVE_YEAR_START
                    if args.v3
                    else os.environ.get(
                        "SIMBOARD_DEFAULT_ARCHIVE_YEAR_START", ""
                    ).strip()
                )
                or None
            )
        if args.archive_end is None:
            args.archive_end = os.environ.get("ARCHIVE_YEAR_END", "").strip() or None


if __name__ == "__main__":
    raise SystemExit(main())
