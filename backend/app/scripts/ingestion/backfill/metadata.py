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
from app.scripts.ingestion.archive_ingestor_core import IngestionRequestError
from app.scripts.ingestion.archive_layout import _filter_archive_walk_dirnames

FIELD_NAMES = {
    "simulation-dates": ("simulation_start_date", "simulation_end_date"),
    "run-script": ("run_script",),
}


def _read_execution(path: Path, machine: str, fields: list[str]):
    """Read only identity files and requested metadata, not full ingestion input."""
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
            raise ValueError(f"Missing identity file {key}: {path}")
        files[key] = matches[0] if matches else None

    timing_identity = FILE_SPECS["e3sm_timing"]["parser"](files["e3sm_timing"])
    if timing_identity.get("execution_id") != path.name:
        raise ValueError(f"Timing identity does not match execution directory: {path}")

    parsed = _parse_all_files(str(path), files)

    if before != [(item.stat().st_mtime_ns, item.stat().st_size) for item in watched]:
        raise ValueError(f"Source changed while reading: {path}")
    if (
        not parsed.machine
        or parse_machine_name(parsed.machine)[0] != parse_machine_name(machine)[0]
    ):
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

        time.sleep(_retry_backoff_seconds(attempt))

    raise RuntimeError("Unreachable request retry state")


def _raise_walk_error(error: OSError) -> None:
    raise error


def _execution_paths(root: Path, kind: str, args: argparse.Namespace):
    """Traverse supported layouts without reading ingestion skip state."""
    if not root.is_dir():
        raise ValueError(f"Source root is not a directory: {root}")

    for current, dirs, _ in os.walk(root, onerror=_raise_walk_error):
        path = Path(current)
        dirs[:] = sorted(name for name in dirs if not (path / name).is_symlink())

        if kind == "archive":
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

        if re.fullmatch(r"\d+\.\d{6}-\d{6}", path.name):
            dirs.clear()
            if args.case_name and path.parent.name != args.case_name:
                continue
            if args.hpc_username and path.parent.parent.name != args.hpc_username:
                continue

            yield path


def _bootstrap(args: argparse.Namespace, api: str, token: str) -> int:
    failures = 0
    matched = 0

    for kind in ("staging", "archive"):
        if args.sources not in (kind, "both"):
            continue

        root = getattr(args, f"{kind}_root")

        if root is None:
            raise ValueError(f"--{kind}-root is required")

        try:
            for path in _execution_paths(root.resolve(), kind, args):
                try:
                    parsed = _read_execution(path, args.machine, [])

                    if args.case_name and parsed.case_name != args.case_name:
                        continue

                    username = _normalize_hpc_username(parsed.hpc_username)

                    if username is None:
                        raise ValueError(f"Missing HPC username: {path}")
                    if args.hpc_username and username != args.hpc_username:
                        continue

                    observation = SourceDirectoryObservation(
                        case_name=parsed.case_name,
                        hpc_username=username,
                        execution_id=parsed.execution_id,
                        kind=kind,
                        case_path=str(path.parent),
                        execution_path=str(path),
                    )

                    result = _request(
                        api,
                        token,
                        "ingestions/source-directories",
                        {
                            "machine_name": args.machine,
                            "dry_run": not args.apply,
                            "directories": [observation.model_dump(mode="json")],
                        },
                    )
                    unresolved = bool(result["unresolved"])
                    failures += unresolved
                    matched += not unresolved

                    print(
                        json.dumps(
                            {
                                "path": str(path),
                                "outcome": "unresolved" if unresolved else "matched",
                                "dry_run": not args.apply,
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

    print(json.dumps({"matched": matched, "failed": failures}))

    return int(bool(failures))


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
            parsed = _read_execution(Path(path), args.machine, args.fields)

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


def _normalized_date(value: str | None) -> str | None:
    parsed = _parse_date_field(value)
    if value and parsed is None:
        raise ValueError(f"Invalid source date: {value}")

    return parsed.isoformat() if parsed else None


def _backfill_metadata(args: argparse.Namespace, api: str, token: str) -> int:
    """Select database owners first, then read their observed source paths."""
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

            return 1

        for record in records:
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

        if len(records) < 100:
            break

        offset += len(records)

    print(json.dumps({**outcomes, "failed": failures}))

    return int(bool(failures))


def _validate_sources(
    parser: argparse.ArgumentParser, args: argparse.Namespace
) -> None:
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--machine", required=True)
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

    print(json.dumps({"api": api, "sources": args.sources, "dry_run": not args.apply}))

    return (
        _bootstrap(args, api, token)
        if args.fields == ["source-directories"]
        else _backfill_metadata(args, api, token)
    )


if __name__ == "__main__":
    raise SystemExit(main())
