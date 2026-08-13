"""Discover published zppy provenance and submit case diagnostics links."""

from __future__ import annotations

import hashlib
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import httpx

from app.scripts.ingestion.archive_ingestor_core import _log_event
from app.scripts.ingestion.diagnostics_archives import (
    DIAGNOSTICS_ARCHIVES_BY_MACHINE,
    DiagnosticsArchive,
)

TIMESTAMP_RE = re.compile(r"^provenance\.(\d{8}_\d{6}_\d{6})\.cfg$")
REQUIRED_SETTINGS = {"case_name", "machine", "hpc_username", "diagnostics_url"}
MAX_SETTINGS_BYTES = 64 * 1024
MAX_SETTINGS_LINES = 200


@dataclass(frozen=True)
class Candidate:
    path: Path
    settings: Path
    timestamp: datetime
    values: dict[str, str]
    fingerprint: str


def run() -> int:
    machine = os.environ.get("MACHINE_NAME", "perlmutter")
    archive = _resolve_archive(machine)
    root = Path(archive.root)
    dry_run = os.environ.get("DRY_RUN", "true").lower() in {"1", "true", "yes"}
    summary = {
        "discovered_candidates": 0,
        "dry_run_candidates": 0,
        "unchanged_candidates": 0,
        "deferred_state_lookups": 0,
        "submitted_links": 0,
        "failed_link_submissions": 0,
    }
    _log_event(
        "diagnostics_scanner_startup_configuration",
        {
            "machine_name": machine,
            "archive_root": str(root),
            "public_base_url": _sanitize_url(archive.public_base_url),
            "dry_run": dry_run,
            "has_api_base_url": bool(os.environ.get("SIMBOARD_API_BASE_URL")),
            "has_api_token": bool(os.environ.get("SIMBOARD_API_TOKEN")),
        },
    )
    candidates = _discover(root, archive.public_base_url)
    summary["discovered_candidates"] = len(candidates)
    _log_event("diagnostics_scanner_discovery_completed", summary.copy())

    if dry_run:
        for candidate in candidates:
            relative = candidate.path.parent.relative_to(root).as_posix()
            summary["dry_run_candidates"] += 1
            _log_event(
                "diagnostics_scanner_dry_run_candidate",
                {
                    "archive_relative_case_path": relative,
                    "settings_filename": candidate.settings.name,
                    "fingerprint": candidate.fingerprint,
                },
            )
        _log_event("diagnostics_scanner_dry_run_completed", summary.copy())
        _log_event("diagnostics_scanner_completed", summary.copy())
        return 0

    api_base = os.environ["SIMBOARD_API_BASE_URL"].rstrip("/")
    token = os.environ["SIMBOARD_API_TOKEN"]
    headers = {"Authorization": f"Bearer {token}"}

    with httpx.Client(timeout=30) as client:
        for candidate in candidates:
            relative = candidate.path.parent.relative_to(root).as_posix()

            state = _request_with_retry(
                client.get,
                f"{api_base}/api/v1/diagnostics/scanner-state",
                params={"machine": machine, "archive_relative_case_path": relative},
                headers=headers,
            )
            _log_event(
                "diagnostics_scanner_state_lookup_result",
                {
                    "archive_relative_case_path": relative,
                    "status_code": None if state is None else state.status_code,
                },
            )

            if state is None or state.status_code != 200:
                summary["deferred_state_lookups"] += 1
                _log_event(
                    "diagnostics_scanner_state_lookup_deferred",
                    {
                        "archive_relative_case_path": relative,
                        "status_code": None if state is None else state.status_code,
                    },
                )
                continue

            state_payload = state.json()
            if state_payload and (
                state_payload.get("settingsFilename") == candidate.settings.name
                and state_payload.get("fingerprint") == candidate.fingerprint
            ):
                summary["unchanged_candidates"] += 1
                _log_event(
                    "diagnostics_scanner_skipped_unchanged",
                    {
                        "archive_relative_case_path": relative,
                        "settings_filename": candidate.settings.name,
                        "fingerprint": candidate.fingerprint,
                    },
                )
                continue

            payload = {
                "caseName": candidate.values["case_name"],
                "machine": candidate.values["machine"],
                "hpcUsername": candidate.values["hpc_username"],
                "diagnostics": [
                    {
                        "name": "zppy diagnostics",
                        "url": candidate.values["diagnostics_url"],
                        "kind": "diagnostic",
                    }
                ],
                "provenance": {
                    "archiveRelativeCasePath": relative,
                    "settingsFilename": candidate.settings.name,
                    "provenanceTimestamp": candidate.timestamp.isoformat(),
                    "fingerprint": candidate.fingerprint,
                },
            }

            response = _request_with_retry(
                client.post,
                f"{api_base}/api/v1/diagnostics/scanner/link",
                json=payload,
                headers=headers,
            )

            if response is None or response.status_code != 204:
                summary["failed_link_submissions"] += 1
                _log_event(
                    "diagnostics_scanner_link_submission_failed",
                    {
                        "archive_relative_case_path": relative,
                        "status_code": None
                        if response is None
                        else response.status_code,
                    },
                )
            else:
                summary["submitted_links"] += 1
                _log_event(
                    "diagnostics_scanner_link_submitted",
                    {
                        "archive_relative_case_path": relative,
                        "status_code": response.status_code,
                    },
                )

    _log_event("diagnostics_scanner_completed", summary)
    return 0


def _resolve_archive(machine_name: str) -> DiagnosticsArchive:
    archive = DIAGNOSTICS_ARCHIVES_BY_MACHINE.get(machine_name.lower())
    if archive is None:
        raise ValueError(f"Unsupported diagnostics scanner machine: {machine_name}")

    root = Path(archive.root)
    parsed = urlparse(archive.public_base_url)
    if not root.is_absolute() or not root.is_dir() or not os.access(root, os.R_OK):
        raise ValueError(f"Diagnostics archive is not readable: {root}")

    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Diagnostics archive public URL must be absolute HTTP(S)")

    return archive


def _sanitize_url(url: str) -> str:
    """Return a URL safe to include in structured logs."""
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    netloc = hostname
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"
    return urlunparse((parsed.scheme, netloc, parsed.path, "", "", ""))


def _discover(root: Path, public_base_url: str) -> list[Candidate]:  # noqa: C901
    base = urlparse(public_base_url)
    candidates: list[Candidate] = []

    for tier in ("production", "development"):
        tier_root = root / tier

        if not tier_root.is_dir():
            continue

        newest_by_case: dict[Path, tuple[Path, datetime]] = {}

        for cfg in tier_root.rglob("provenance.*.cfg"):
            try:
                if cfg.is_symlink() or root not in cfg.resolve().parents:
                    continue
            except OSError as exc:
                _log_invalid_provenance(root, cfg, exc)
                continue

            timestamp = _timestamp(cfg)
            if timestamp is None:
                continue

            case_dir = cfg.parent
            prior = newest_by_case.get(case_dir)

            if prior is None or timestamp > prior[1]:
                newest_by_case[case_dir] = (cfg, timestamp)

        for case_dir, (cfg, timestamp) in newest_by_case.items():
            settings = cfg.with_suffix(".settings")
            try:
                if (
                    settings.is_symlink()
                    or root not in settings.resolve().parents
                    or not settings.is_file()
                    or not _published_output(case_dir, root)
                ):
                    continue
                settings_bytes = _read_settings_bytes(settings)
                values = _parse_settings_bytes(settings_bytes)
                url = urlparse(values["diagnostics_url"])

                if (url.scheme, url.netloc) != (
                    base.scheme,
                    base.netloc,
                ) or not url.path.startswith(base.path.rstrip("/") + "/"):
                    raise ValueError(
                        "Diagnostics URL outside configured public archive"
                    )
                _validate_layout(case_dir, root, values)

                digest = hashlib.sha256(settings_bytes).hexdigest()
                candidates.append(Candidate(cfg, settings, timestamp, values, digest))
            except (OSError, UnicodeError, ValueError) as exc:
                _log_invalid_provenance(root, cfg, exc)

    return candidates


def _log_invalid_provenance(root: Path, cfg: Path, exc: Exception) -> None:
    """Log a malformed or inaccessible provenance file without halting discovery."""
    _log_event(
        "diagnostics_scanner_invalid_provenance",
        {
            "provenance_path": cfg.relative_to(root).as_posix(),
            "reason": str(exc),
        },
    )


def _request_with_retry(method, url: str, **kwargs) -> httpx.Response | None:
    for attempt in range(3):
        try:
            response = method(url, **kwargs)
        except httpx.RequestError:
            response = None
        if (
            response is not None
            and response.status_code not in {408, 429}
            and response.status_code < 500
        ):
            return response

        if attempt < 2:
            _log_event(
                "diagnostics_scanner_request_retry_scheduled",
                {
                    "attempt": attempt + 1,
                    "max_attempts": 3,
                    "status_code": None if response is None else response.status_code,
                    "request_error": response is None,
                },
            )
            time.sleep(2**attempt)

    _log_event(
        "diagnostics_scanner_request_retry_exhausted",
        {
            "attempts": 3,
            "status_code": None if response is None else response.status_code,
            "request_error": response is None,
        },
    )
    return response


def _read_settings_bytes(path: Path) -> bytes:
    with path.open("rb") as settings_file:
        content = settings_file.read(MAX_SETTINGS_BYTES + 1)
    if len(content) > MAX_SETTINGS_BYTES:
        raise ValueError("Provenance settings file is too large")
    return content


def _parse_settings_bytes(content: bytes) -> dict[str, str]:
    values: dict[str, str] = {}

    for line_number, line in enumerate(content.decode("utf-8").splitlines(), start=1):
        if line_number > MAX_SETTINGS_LINES:
            raise ValueError("Provenance settings file has too many lines")
        if not line.strip() or line.lstrip().startswith("#"):
            continue

        if "=" not in line:
            raise ValueError("Malformed provenance settings line")

        key, value = (part.strip() for part in line.split("=", 1))

        if not key or not value or key in values:
            raise ValueError("Malformed or duplicate provenance setting")

        values[key] = value

    if REQUIRED_SETTINGS - values.keys():
        raise ValueError("Missing required provenance settings")

    return values


def _published_output(case_dir: Path, root: Path) -> bool:
    for entry in case_dir.iterdir():
        if entry.name.startswith("provenance."):
            continue

        if entry.is_symlink() or root not in entry.resolve().parents:
            continue

        if entry.is_file() or (entry.is_dir() and any(entry.iterdir())):
            return True

    return False


def _validate_layout(case_dir: Path, root: Path, values: dict[str, str]) -> None:
    parts = case_dir.relative_to(root).parts

    if len(parts) not in {3, 4} or parts[0] not in {"production", "development"}:
        raise ValueError("Invalid diagnostics archive case layout")

    if values["case_name"] != parts[-1]:
        raise ValueError("Provenance case_name does not match archive layout")

    expected_group = parts[-2] if len(parts) == 4 else None

    if values.get("case_group") != expected_group:
        raise ValueError("Provenance case_group does not match archive layout")


def _timestamp(cfg: Path) -> datetime | None:
    match = TIMESTAMP_RE.match(cfg.name)

    if match is None:
        return None

    return datetime.strptime(match.group(1), "%Y%m%d_%H%M%S_%f").replace(
        tzinfo=timezone.utc
    )


if __name__ == "__main__":
    raise SystemExit(run())
