from pathlib import Path

import httpx
import pytest

from app.scripts.ingestion.diagnostics_link_scanner import (
    _request_with_retry,
    discover,
    parse_settings,
)

BASE_URL = "https://diagnostics.example.org/archive"


def _case(root: Path, path: str, *, timestamp: str = "20260811_120000_000000") -> Path:
    directory = root / path
    directory.mkdir(parents=True)
    cfg = directory / f"provenance.{timestamp}.cfg"
    cfg.write_text("cfg", encoding="utf-8")
    cfg.with_suffix(".settings").write_text(
        "case_name = case\nmachine = perlmutter\nhpc_username = user\n"
        "diagnostics_url = https://diagnostics.example.org/archive/case\n",
        encoding="utf-8",
    )
    (directory / "index.html").write_text("ready", encoding="utf-8")
    return directory


def test_newest_missing_settings_defers_without_stale_fallback(tmp_path: Path) -> None:
    directory = _case(tmp_path, "production/type/case")
    (directory / "provenance.20260812_120000_000000.cfg").write_text("cfg")
    assert discover(tmp_path, BASE_URL) == []


def test_discovery_rejects_case_and_group_mismatches(tmp_path: Path) -> None:
    directory = _case(tmp_path, "development/type/group/case")
    settings = next(directory.glob("*.settings"))
    settings.write_text(
        settings.read_text().replace("case_name = case", "case_name = wrong")
    )
    assert discover(tmp_path, BASE_URL) == []


def test_parse_settings_rejects_duplicate_required_key(tmp_path: Path) -> None:
    settings = tmp_path / "provenance.settings"
    settings.write_text("case_name = one\ncase_name = two\n", encoding="utf-8")
    with pytest.raises(ValueError):
        parse_settings(settings)


def test_discovery_rejects_settings_symlink_outside_root(tmp_path: Path) -> None:
    directory = _case(tmp_path, "production/type/case")
    settings = next(directory.glob("*.settings"))
    outside = tmp_path.parent / "outside.settings"
    outside.write_text(settings.read_text(), encoding="utf-8")
    settings.unlink()
    settings.symlink_to(outside)
    assert discover(tmp_path, BASE_URL) == []


def test_retry_helper_retries_transient_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = [httpx.Response(503), httpx.Response(204)]
    monkeypatch.setattr(
        "app.scripts.ingestion.diagnostics_link_scanner.time.sleep", lambda _: None
    )
    response = _request_with_retry(
        lambda *_args, **_kwargs: responses.pop(0), "https://x"
    )
    assert response is not None
    assert response.status_code == 204
