"""Discover published zppy provenance and submit case diagnostics links."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.scripts.ingestion.diagnostics_archives import (
    DIAGNOSTICS_ARCHIVES_BY_MACHINE,
    DiagnosticsArchive,
)

LOGGER = logging.getLogger(__name__)
TIMESTAMP_RE = re.compile(r"^provenance\.(\d{8}_\d{6}_\d{6})\.cfg$")
REQUIRED_SETTINGS = {"case_name", "machine", "hpc_username", "diagnostics_url"}


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
    api_base = os.environ["SIMBOARD_API_BASE_URL"].rstrip("/")
    token = os.environ["SIMBOARD_API_TOKEN"]
    headers = {"Authorization": f"Bearer {token}"}

    with httpx.Client(timeout=30) as client:
        for candidate in _discover(root, archive.public_base_url):
            relative = candidate.path.parent.relative_to(root).as_posix()

            if dry_run:
                LOGGER.info("Would link diagnostics for %s", relative)
                continue

            state = _request_with_retry(
                client.get,
                f"{api_base}/api/v1/diagnostics/scanner-state",
                params={"machine": machine, "archive_relative_case_path": relative},
                headers=headers,
            )

            if state is None or state.status_code != 200:
                LOGGER.warning("State lookup failed for %s; deferring", relative)
                continue

            if (
                state.status_code == 200
                and state.json()
                and (
                    state.json().get("settingsFilename") == candidate.settings.name
                    and state.json().get("fingerprint") == candidate.fingerprint
                )
            ):
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
                LOGGER.warning("Diagnostics link submission failed for %s", relative)

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


def _discover(root: Path, public_base_url: str) -> list[Candidate]:  # noqa: C901
    base = urlparse(public_base_url)
    candidates: list[Candidate] = []

    for tier in ("production", "development"):
        tier_root = root / tier

        if not tier_root.is_dir():
            continue

        newest_by_case: dict[Path, tuple[Path, datetime]] = {}

        for cfg in tier_root.rglob("provenance.*.cfg"):
            if cfg.is_symlink() or root not in cfg.resolve().parents:
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
            if (
                settings.is_symlink()
                or root not in settings.resolve().parents
                or not settings.is_file()
                or not _published_output(case_dir)
            ):
                continue
            try:
                values = _parse_settings(settings)
                url = urlparse(values["diagnostics_url"])

                if (url.scheme, url.netloc) != (
                    base.scheme,
                    base.netloc,
                ) or not url.path.startswith(base.path.rstrip("/") + "/"):
                    raise ValueError(
                        "Diagnostics URL outside configured public archive"
                    )
                _validate_layout(case_dir, root, values)

                digest = hashlib.sha256(settings.read_bytes()).hexdigest()
                candidates.append(Candidate(cfg, settings, timestamp, values, digest))
            except (OSError, UnicodeError, ValueError) as exc:
                LOGGER.warning("Skipping invalid provenance %s: %s", cfg, exc)

    return candidates


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
            time.sleep(2**attempt)

    return response


def _parse_settings(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}

    for line in path.read_text(encoding="utf-8").splitlines():
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


def _published_output(case_dir: Path) -> bool:
    for entry in case_dir.iterdir():
        if entry.name.startswith("provenance."):
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
