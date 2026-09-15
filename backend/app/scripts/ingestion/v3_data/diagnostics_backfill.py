"""One-time backfill of E3SM v3 diagnostics into the reviewed archives."""

from __future__ import annotations

import argparse
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.scripts.ingestion.archive_ingestor_core import _log_event, _log_multiline_event
from app.scripts.ingestion.diagnostics_archives import DIAGNOSTICS_ARCHIVES_BY_MACHINE
from app.scripts.ingestion.diagnostics_link_scanner import (
    TIMESTAMP_RE,
)
from app.scripts.ingestion.diagnostics_link_scanner import (
    run as run_scanner,
)
from app.scripts.ingestion.v3_data.lcrc_v3_archive_ingestor import V3_CASE_NAMES

SUPPORTED_MACHINES = frozenset({"chrysalis", "perlmutter"})
RECONCILIATION_STATUSES = (
    "copied",
    "linked",
    "skipped_existing",
    "missing",
    "unmapped",
    "zero_matches",
    "owner_mismatch",
    "ambiguous",
    "failed",
)
SIMBOARD_HPC_USERNAME_BY_DIAGNOSTICS_PUBLISHER = {
    "ac.kzhang": "ac.kai.zhang",
}


@dataclass(frozen=True)
class Target:
    case_name: str
    source: str | None
    machine: str
    source_is_case_dir: bool = False


def _targets(
    names: tuple[str, ...], source: str | None, machine: str = "chrysalis"
) -> tuple[Target, ...]:
    targets = tuple(Target(name, source, machine) for name in names)
    return targets


# Paths are relative to the diagnostic-output root, rather than inferred from a
# case name. This preserves the source choices documented on issue #302.
V3_DIAGNOSTIC_TARGETS = (
    Target("v3.LR.piControl", "ac.golaz/E3SMv3/v3.LR.piControl", "chrysalis", True),
    *_targets(
        (
            "v3.LR.historical_0051",
            "v3.LR.historical_0101",
            "v3.LR.historical_0151",
            "v3.LR.historical_0201",
            "v3.LR.historical_0251",
            "v3.LR.amip_0101",
            "v3.LR.amip_0151",
            "v3.LR.amip_0201",
            "v3.LR.1pctCO2_0101_bcdt15m",
            "v3.LR.abrupt-4xCO2_0101_bcdt15m",
            "v3.LR.hist-xGHG-xaer_0101",
            "v3.LR.hist-xGHG-xaer_0151",
            "v3.LR.hist-xGHG-xaer_0201",
        ),
        "ac.wlin/E3SMv3",
    ),
    *_targets(
        ("v3.LR.hist-GHG_0101", "v3.LR.hist-GHG_0151", "v3.LR.hist-GHG_0201"),
        "ac.golaz/E3SMv3",
    ),
    *_targets(
        (
            "v3.LR.hist-aer_0101",
            "v3.LR.hist-aer_0151",
            "v3.LR.hist-aer_0201",
            "v3.LR.piClim-histall_0151",
            "v3.LR.piClim-histall_0201",
            "v3.LR.piClim-histGHG_0201",
            "v3.LR.piClim-histaer_0101",
            "v3.LR.piClim-histaer_0151",
            "v3.LR.piClim-histaer_0201",
            "v3.LR.piClim-control-iceini",
            "v3.LR.piClim-histall_0101",
            "v3.LR.piClim-histGHG_0101",
            "v3.LR.piClim-histGHG_0151",
        ),
        "ac.kzhang/E3SMv3",
    ),
    *_targets(
        (
            "v3.NARRM.amip_0101",
            "v3.NARRM_r0125.amip_0101",
            "v3.AMZRRM.amip_0101",
            "v3.EARRM.amip_0101",
        ),
        "ac.qtang/E3SMv3",
    ),
    Target(
        "v3.LR.amip_bonus_0101",
        "ac.wlin/E3SMv3/v3.LR.amip_0101",
        "perlmutter",
        True,
    ),
)

if {target.case_name for target in V3_DIAGNOSTIC_TARGETS} != (
    V3_CASE_NAMES - {"LR_ensemble", "RRM_ensemble"}
) | {"v3.LR.amip_bonus_0101"}:
    raise RuntimeError("V3 diagnostic targets must cover every physical v3 case")


def main() -> int:
    """Backfill diagnostics for one supported machine."""
    args = _parse_args()
    dry_run = _dry_run_requested(args.dry_run)
    machine = args.machine
    archive = DIAGNOSTICS_ARCHIVES_BY_MACHINE[machine]
    source_root = _diagnostics_source_root(archive.root)
    api_base = _api_base_url(os.environ["SIMBOARD_API_BASE_URL"])

    if not api_base:
        raise ValueError("SIMBOARD_API_BASE_URL is required")

    # The scanner appends /api/v1 to this host-level base URL itself.
    os.environ["SIMBOARD_API_BASE_URL"] = api_base

    if not dry_run and not os.environ.get("SIMBOARD_API_TOKEN", "").strip():
        raise ValueError("SIMBOARD_API_TOKEN is required when --dry-run is not set")

    selected = [target for target in V3_DIAGNOSTIC_TARGETS if target.machine == machine]
    report = _new_report(machine)

    if not source_root.is_dir():
        raise ValueError(f"Diagnostics source root is not readable: {source_root}")

    _log_startup_configuration(
        archive_root=archive.root,
        api_base=api_base,
        dry_run=dry_run,
        machine=machine,
        public_base_url=archive.public_base_url,
        selected_target_count=len(selected),
        source_root=source_root,
    )

    with httpx.Client(timeout=30) as client:
        machine_id = _resolve_machine_id(client, api_base, machine)

        for target in selected:
            if target.source is None:
                continue

            status = _backfill_target(
                client=client,
                api_base=api_base,
                archive_root=Path(archive.root),
                public_base_url=archive.public_base_url,
                source_root=source_root,
                target=target,
                machine=machine,
                machine_id=machine_id,
                dry_run=dry_run,
            )
            report[status].append(target.case_name)

    _run_scanner_if_reconciled(report, machine, dry_run)
    _log_reconciliation(report, machine, dry_run, len(selected))

    if any(
        report[key]
        for key in (
            "missing",
            "zero_matches",
            "owner_mismatch",
            "ambiguous",
            "failed",
        )
    ):
        return 1

    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--machine", required=True, choices=sorted(SUPPORTED_MACHINES))
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report actions without writing or scanning, overriding DRY_RUN.",
    )

    return parser.parse_args()


def _dry_run_requested(command_line_dry_run: bool) -> bool:
    """Use the diagnostics-scanner DRY_RUN contract unless CLI opts in."""
    if command_line_dry_run:
        return True

    return os.environ.get("DRY_RUN", "true").lower() in {
        "1",
        "true",
        "yes",
    }


def _api_headers() -> dict[str, str]:
    token = os.environ.get("SIMBOARD_API_TOKEN", "").strip()
    if not token:
        return {}

    return {"Authorization": f"Bearer {token}"}


def _diagnostics_source_root(archive_root: str) -> Path:
    """Return the diagnostic-output root containing the reviewed archive root."""
    return Path(archive_root).parent


def _api_base_url(value: str) -> str:
    """Normalize a deployment URL with or without the API version prefix."""
    return value.strip().rstrip("/").removesuffix("/api/v1")


def _new_report(machine: str) -> dict[str, list[str]]:
    """Initialize reconciliation categories for the selected machine."""
    report: dict[str, list[str]] = {
        status: [] for status in (*RECONCILIATION_STATUSES, "machine_skipped")
    }
    report["machine_skipped"] = [
        target.case_name
        for target in V3_DIAGNOSTIC_TARGETS
        if target.machine != machine
    ]
    report["unmapped"] = [
        target.case_name
        for target in V3_DIAGNOSTIC_TARGETS
        if target.machine == machine and target.source is None
    ]
    return report


def _log_startup_configuration(
    *,
    archive_root: str,
    api_base: str,
    dry_run: bool,
    machine: str,
    public_base_url: str,
    selected_target_count: int,
    source_root: Path,
) -> None:
    """Log effective configuration without exposing the API token."""
    _log_multiline_event(
        "v3_diagnostics_backfill_startup_configuration",
        {
            "machine": machine,
            "dry_run": dry_run,
            "simboard_api_base_url": api_base,
            "has_api_token": bool(os.environ.get("SIMBOARD_API_TOKEN", "").strip()),
            "diagnostics_source_root": str(source_root),
            "diagnostics_archive_root": archive_root,
            "diagnostics_public_base_url": public_base_url,
            "selected_target_count": selected_target_count,
        },
    )


def _resolve_machine_id(client: httpx.Client, api_base: str, machine: str) -> str:
    response = client.get(f"{api_base}/api/v1/machines", headers=_api_headers())

    response.raise_for_status()
    matches = [item for item in response.json() if item["name"] == machine]

    if len(matches) != 1:
        raise ValueError(f"Expected exactly one SimBoard machine named {machine}")

    return str(matches[0]["id"])


def _backfill_target(
    *,
    client: httpx.Client,
    api_base: str,
    archive_root: Path,
    public_base_url: str,
    source_root: Path,
    target: Target,
    machine: str,
    machine_id: str,
    dry_run: bool,
) -> str:
    """Copy one target and return its reconciliation outcome."""
    assert target.source is not None
    source = source_root / target.source
    if not target.source_is_case_dir:
        source /= target.case_name

    case, resolution_status = _resolve_owner_case(
        client,
        api_base,
        target,
        machine_id,
        source,
    )
    if resolution_status:
        return resolution_status

    assert case is not None

    destination = archive_root / "production"
    if group := case.get("caseGroup"):
        destination /= group
    destination /= target.case_name

    if destination.is_dir():
        return "skipped_existing"
    if destination.exists():
        return "failed"

    if not source.is_dir():
        return "missing"

    if dry_run:
        return "copied"

    try:
        _copy_diagnostics(source, destination)
        cfg = _latest_cfg(destination) or _create_provenance_cfg(destination)
        _write_settings(cfg, case, machine, public_base_url)
    except (OSError, shutil.Error) as exc:
        _log_event(
            "v3_diagnostics_backfill_target_failed",
            {"case_name": target.case_name, "error": str(exc)},
        )
        return "failed"

    return "copied"


def _resolve_owner_case(
    client: httpx.Client,
    api_base: str,
    target: Target,
    machine_id: str,
    source: Path,
) -> tuple[dict[str, Any] | None, str | None]:
    """Resolve the one case owned by the mapped diagnostics publisher."""
    matches, total = _resolve_cases(client, api_base, target, machine_id)
    if total == 0:
        return None, "zero_matches"

    diagnostics_publisher = _diagnostics_publisher(target)
    hpc_username = _diagnostics_hpc_username(diagnostics_publisher)
    if total > 1:
        _log_multiple_case_matches(
            target, diagnostics_publisher, hpc_username, source, matches
        )

    owner_matches = _matching_owner_cases(matches, hpc_username)
    if not owner_matches:
        return None, "owner_mismatch"

    if len(owner_matches) != 1:
        return None, "ambiguous"

    return owner_matches[0], None


def _resolve_cases(
    client: httpx.Client, api_base: str, target: Target, machine_id: str
) -> tuple[list[dict[str, Any]], int]:
    response = client.get(
        f"{api_base}/api/v1/cases",
        params={"name": target.case_name, "machine_id": machine_id, "page_size": 100},
        headers=_api_headers(),
    )
    response.raise_for_status()
    payload = response.json()

    return payload["items"], payload["total"]


def _diagnostics_publisher(target: Target) -> str:
    """Extract the production diagnostics owner from the mapped source path."""
    assert target.source is not None
    publisher = target.source.split("/", maxsplit=1)[0]

    if not publisher:
        raise ValueError(f"Missing diagnostics owner for {target.case_name}")

    return publisher


def _diagnostics_hpc_username(diagnostics_publisher: str) -> str:
    """Return the SimBoard username corresponding to the diagnostics publisher."""
    return SIMBOARD_HPC_USERNAME_BY_DIAGNOSTICS_PUBLISHER.get(
        diagnostics_publisher,
        diagnostics_publisher,
    )


def _matching_owner_cases(
    cases: list[dict[str, Any]], hpc_username: str
) -> list[dict[str, Any]]:
    """Return case records owned by the user who published the diagnostics."""
    return [case for case in cases if case["hpcUsername"] == hpc_username]


def _log_multiple_case_matches(
    target: Target,
    diagnostics_publisher: str,
    hpc_username: str,
    source: Path,
    cases: list[dict[str, Any]],
) -> None:
    """Log every candidate identity before owner-based case selection."""
    _log_multiline_event(
        "v3_diagnostics_backfill_multiple_case_matches",
        {
            "case_name": target.case_name,
            "diagnostics_publisher": diagnostics_publisher,
            "diagnostics_source_path": str(source),
            "selected_hpc_username": hpc_username,
            "matching_cases": [
                f"case_name:{case['name']}/hpc_username:{case['hpcUsername']}"
                for case in cases
            ],
        },
    )


def _latest_cfg(directory: Path) -> Path | None:
    candidates: list[tuple[datetime, Path]] = []
    for path in directory.glob("provenance.*.cfg"):
        match = TIMESTAMP_RE.match(path.name)
        if not path.is_file() or match is None:
            continue

        try:
            timestamp = datetime.strptime(match.group(1), "%Y%m%d_%H%M%S_%f")
        except ValueError:
            continue

        candidates.append((timestamp, path))

    if not candidates:
        return None

    return max(candidates, key=lambda candidate: candidate[0])[1]


def _copy_diagnostics(source: Path, destination: Path) -> None:
    """Copy output and cfg provenance, never source-generated settings files."""
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns("provenance.*.settings"),
        dirs_exist_ok=False,
    )


def _create_provenance_cfg(directory: Path) -> Path:
    """Create provenance for historic diagnostics that predate zppy provenance."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    cfg = directory / f"provenance.{timestamp}.cfg"
    cfg.touch(exist_ok=False)

    return cfg


def _write_settings(
    cfg: Path, case: dict[str, Any], machine: str, public_base_url: str
) -> Path:
    case_group = case.get("caseGroup")
    relative_parts = (
        ["production"] + ([case_group] if case_group else []) + [case["name"]]
    )
    diagnostics_url = f"{public_base_url}/{'/'.join(relative_parts)}"
    lines = [
        f"case_name = {case['name']}",
        f"machine = {machine}",
        f"hpc_username = {case['hpcUsername']}",
    ]

    if case_group:
        lines.append(f"case_group = {case_group}")
    lines.append(f"diagnostics_url = {diagnostics_url}")

    settings = cfg.with_suffix(".settings")
    if settings.exists():
        raise FileExistsError(f"Refusing to replace existing settings: {settings}")

    settings.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return settings


def _run_scanner_if_reconciled(
    report: dict[str, list[str]], machine: str, dry_run: bool
) -> None:
    if dry_run or any(
        report[status]
        for status in (
            "missing",
            "zero_matches",
            "owner_mismatch",
            "ambiguous",
            "failed",
        )
    ):
        return

    os.environ["MACHINE_NAME"] = machine
    os.environ["DRY_RUN"] = "false"

    if run_scanner() != 0:
        report["failed"].extend(report["copied"] + report["skipped_existing"])
    else:
        report["linked"] = report["copied"].copy()


def _reconciliation_fields(
    report: dict[str, list[str]], selected_target_count: int, dry_run: bool
) -> dict[str, object]:
    """Return count-qualified, per-outcome reconciliation fields for logs."""
    fields: dict[str, object] = {
        "selected_target_count": selected_target_count,
        "machine_skipped_count": f"{len(report['machine_skipped'])}/{len(V3_DIAGNOSTIC_TARGETS)}",
        "machine_skipped_cases": report["machine_skipped"],
    }

    for status in RECONCILIATION_STATUSES:
        label = "ready_to_copy" if dry_run and status == "copied" else status
        fields[f"{label}_count"] = f"{len(report[status])}/{selected_target_count}"
        fields[f"{label}_cases"] = report[status]

    return fields


def _log_reconciliation(
    report: dict[str, list[str]],
    machine: str,
    dry_run: bool,
    selected_target_count: int,
) -> None:
    """Log the completed reconciliation with counts before case lists."""
    _log_multiline_event(
        "v3_diagnostics_backfill_reconciliation",
        {
            "machine": machine,
            "dry_run": dry_run,
            **_reconciliation_fields(report, selected_target_count, dry_run),
        },
    )


if __name__ == "__main__":
    raise SystemExit(main())
