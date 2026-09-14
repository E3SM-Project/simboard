"""One-time backfill of E3SM v3 diagnostics into the reviewed archives."""

from __future__ import annotations

import argparse
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.scripts.ingestion.archive_ingestor_core import _log_event
from app.scripts.ingestion.diagnostics_archives import DIAGNOSTICS_ARCHIVES_BY_MACHINE
from app.scripts.ingestion.diagnostics_link_scanner import (
    TIMESTAMP_RE,
)
from app.scripts.ingestion.diagnostics_link_scanner import (
    run as run_scanner,
)
from app.scripts.ingestion.v3_data.lcrc_v3_archive_ingestor import V3_CASE_NAMES

SUPPORTED_MACHINES = frozenset({"chrysalis", "perlmutter"})
SOURCE_ROOT_ENV = "V3_DIAGNOSTICS_SOURCE_ROOT"


@dataclass(frozen=True)
class Target:
    case_name: str
    source: str | None
    machine: str
    source_is_case_dir: bool = False


def _targets(
    names: tuple[str, ...], source: str | None, machine: str = "chrysalis"
) -> tuple[Target, ...]:
    return tuple(Target(name, source, machine) for name in names)


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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--machine", required=True, choices=sorted(SUPPORTED_MACHINES))
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report actions without writing or scanning.",
    )
    return parser.parse_args()


def _api_headers() -> dict[str, str]:
    token = os.environ.get("SIMBOARD_API_TOKEN", "").strip()
    return {"Authorization": f"Bearer {token}"} if token else {}


def _resolve_machine_id(client: httpx.Client, api_base: str, machine: str) -> str:
    response = client.get(f"{api_base}/api/v1/machines", headers=_api_headers())
    response.raise_for_status()
    matches = [item for item in response.json() if item["name"] == machine]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one SimBoard machine named {machine}")
    return str(matches[0]["id"])


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


def _latest_cfg(directory: Path) -> Path | None:
    candidates = []
    for path in directory.glob("provenance.*.cfg"):
        if path.is_file() and TIMESTAMP_RE.match(path.name):
            candidates.append(path)
    return max(candidates, key=lambda path: path.name) if candidates else None


def _copy_diagnostics(source: Path, destination: Path) -> None:
    """Copy output and cfg provenance, never source-generated settings files."""
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns("provenance.*.settings"),
        dirs_exist_ok=False,
    )


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
    matches, total = _resolve_cases(client, api_base, target, machine_id)
    if total == 0:
        return "zero_matches"
    if total != 1 or len(matches) != 1:
        return "ambiguous"
    case = matches[0]
    source = source_root / target.source
    if not target.source_is_case_dir:
        source /= target.case_name
    if not source.is_dir():
        return "missing"
    if dry_run:
        return "copied"

    destination = archive_root / "production"
    if group := case.get("caseGroup"):
        destination /= group
    destination /= target.case_name
    try:
        _copy_diagnostics(source, destination)
        cfg = _latest_cfg(destination)
        if cfg is None:
            return "failed"
        _write_settings(cfg, case, machine, public_base_url)
    except (OSError, shutil.Error) as exc:
        _log_event(
            "v3_diagnostics_backfill_target_failed",
            {"case_name": target.case_name, "error": str(exc)},
        )
        return "failed"
    return "copied"


def _run_scanner_if_reconciled(
    report: dict[str, list[str]], machine: str, dry_run: bool
) -> None:
    if dry_run or any(
        report[status] for status in ("missing", "zero_matches", "ambiguous", "failed")
    ):
        return
    os.environ["MACHINE_NAME"] = machine
    os.environ["DRY_RUN"] = "false"
    if run_scanner() != 0:
        report["failed"].extend(report["copied"])
    else:
        report["linked"] = report["copied"].copy()


def main() -> int:
    args = _parse_args()
    machine = args.machine
    archive = DIAGNOSTICS_ARCHIVES_BY_MACHINE[machine]
    source_root = Path(os.environ[SOURCE_ROOT_ENV]).resolve()
    api_base = os.environ["SIMBOARD_API_BASE_URL"].rstrip("/")
    if not args.dry_run and not os.environ.get("SIMBOARD_API_TOKEN", "").strip():
        raise ValueError("SIMBOARD_API_TOKEN is required when --dry-run is not set")
    report: dict[str, list[str]] = {
        key: []
        for key in (
            "copied",
            "linked",
            "missing",
            "unmapped",
            "zero_matches",
            "ambiguous",
            "machine_skipped",
            "failed",
        )
    }
    selected = [target for target in V3_DIAGNOSTIC_TARGETS if target.machine == machine]
    report["machine_skipped"] = [
        target.case_name
        for target in V3_DIAGNOSTIC_TARGETS
        if target.machine != machine
    ]
    report["unmapped"] = [
        target.case_name for target in selected if target.source is None
    ]

    if not source_root.is_dir():
        raise ValueError(
            f"{SOURCE_ROOT_ENV} is not a readable directory: {source_root}"
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
                dry_run=args.dry_run,
            )
            report[status].append(target.case_name)

    _run_scanner_if_reconciled(report, machine, args.dry_run)

    _log_event(
        "v3_diagnostics_backfill_reconciliation",
        {
            "machine": machine,
            "dry_run": args.dry_run,
            "targets": [target.case_name for target in selected],
            **report,
        },
    )
    return (
        1
        if any(
            report[key] for key in ("missing", "zero_matches", "ambiguous", "failed")
        )
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
