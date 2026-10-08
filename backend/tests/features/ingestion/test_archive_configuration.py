"""Shared policy defaults and required deployment configuration."""

from pathlib import Path

import pytest

from app.scripts.ingestion.archive_ingestor_core import _build_config_from_env
from app.scripts.ingestion.archive_layout import _build_case_path_filter
from app.scripts.ingestion.v3_data import lcrc_v3_archive_ingestor as v3_ingestor


@pytest.fixture(autouse=True)
def site_environment(monkeypatch, tmp_path: Path) -> None:
    for name in (
        "SCAN_MODE",
        "ARCHIVE_YEAR_START",
        "ARCHIVE_YEAR_END",
        "PERF_ARCHIVE_ROOT",
        "OLD_PERF_ARCHIVE_ROOT",
        "MACHINE_NAME",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SCAN_MODE", "archive")
    monkeypatch.setenv("OLD_PERF_ARCHIVE_ROOT", str(tmp_path / "OLD_PERF"))
    monkeypatch.setenv("MACHINE_NAME", "perlmutter")


@pytest.mark.parametrize("lower_bound", [None, "", " \t "])
def test_archive_default_excludes_old_snapshots(monkeypatch, lower_bound) -> None:
    if lower_bound is not None:
        monkeypatch.setenv("ARCHIVE_YEAR_START", lower_bound)
    config = _build_config_from_env()
    assert config.archive_year_start == "2025-01"
    assert config.archive_year_end is None
    case_filter = _build_case_path_filter(config)
    assert case_filter is not None
    for month, included in (("2024-12", False), ("2025-01", True), ("2026-01", True)):
        case_path = (
            config.archive_root
            / month
            / f"performance_archive_{month.replace('-', '_')}_01_00_00_00"
            / "COMPLETED"
            / "user"
            / "case"
        )
        case_path.mkdir(parents=True)
        assert case_filter(case_path) is included


def test_explicit_historical_bound_includes_old_snapshot(monkeypatch) -> None:
    monkeypatch.setenv("ARCHIVE_YEAR_START", "2024")
    config = _build_config_from_env()
    assert config.archive_year_start == "2024-01"
    case_filter = _build_case_path_filter(config)
    assert case_filter is not None
    case_path = (
        config.archive_root
        / "2024-01"
        / "performance_archive_2024_01_01_00_00_00"
        / "COMPLETED"
        / "user"
        / "case"
    )
    case_path.mkdir(parents=True)
    assert case_filter(case_path)


@pytest.mark.parametrize("mode", ["staging", "archive"])
@pytest.mark.parametrize("missing_value", [None, "", " \t "])
@pytest.mark.parametrize("missing_setting", ["root", "machine"])
def test_required_site_values_fail_clearly(
    monkeypatch, tmp_path: Path, mode, missing_value, missing_setting
) -> None:
    monkeypatch.setenv("SCAN_MODE", mode)
    root_name = "PERF_ARCHIVE_ROOT" if mode == "staging" else "OLD_PERF_ARCHIVE_ROOT"
    monkeypatch.setenv(root_name, str(tmp_path / "root"))
    name = root_name if missing_setting == "root" else "MACHINE_NAME"
    if missing_value is None:
        monkeypatch.delenv(name, raising=False)
    else:
        monkeypatch.setenv(name, missing_value)
    with pytest.raises(ValueError, match=f"{name} is required"):
        _build_config_from_env()


@pytest.mark.parametrize("mode", ["staging", "archive"])
def test_only_active_root_is_required(monkeypatch, tmp_path: Path, mode) -> None:
    monkeypatch.setenv("SCAN_MODE", mode)
    root_name = "PERF_ARCHIVE_ROOT" if mode == "staging" else "OLD_PERF_ARCHIVE_ROOT"
    unused_name = "OLD_PERF_ARCHIVE_ROOT" if mode == "staging" else "PERF_ARCHIVE_ROOT"
    monkeypatch.setenv(root_name, str(tmp_path / "active"))
    monkeypatch.delenv(unused_name, raising=False)
    config = _build_config_from_env()
    assert config.archive_root == (tmp_path / "active").resolve()
    assert config.archive_year_start == ("2025-01" if mode == "archive" else None)


def test_spin_paths_are_explicit_and_independent_of_host_config(monkeypatch) -> None:
    monkeypatch.setenv("OLD_PERF_ARCHIVE_ROOT", "/OLD_PERF")
    config = _build_config_from_env()
    assert config.archive_root == Path("/OLD_PERF")
    assert config.machine_name == "perlmutter"
    assert config.archive_year_start == "2025-01"


def test_v3_supplies_site_values_before_shared_validation(monkeypatch) -> None:
    monkeypatch.setenv("SIMBOARD_API_BASE_URL", "https://simboard.example")
    monkeypatch.setenv("ARCHIVE_YEAR_START", "2025-01")
    monkeypatch.delenv("OLD_PERF_ARCHIVE_ROOT")
    monkeypatch.delenv("MACHINE_NAME")
    config = v3_ingestor._build_v3_config_from_env()
    assert config.archive_root == Path(v3_ingestor.CHRYSALIS_ARCHIVE_ROOT)
    assert config.machine_name == "chrysalis"
    assert config.archive_year_start == "2024-01"
