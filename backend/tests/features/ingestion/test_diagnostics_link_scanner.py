from pathlib import Path

import httpx
import pytest

from app.scripts.ingestion.diagnostics_archives import (
    DIAGNOSTICS_ARCHIVES_BY_MACHINE,
    DiagnosticsArchive,
)
from app.scripts.ingestion.diagnostics_link_scanner import (
    _discover,
    _parse_settings_bytes,
    _read_settings_bytes,
    _request_with_retry,
    run,
)

BASE_URL = "https://diagnostics.example.org/archive"


def test_chrysalis_diagnostics_archive_settings() -> None:
    archive = DIAGNOSTICS_ARCHIVES_BY_MACHINE["chrysalis"]
    assert archive.root == "/lcrc/group/e3sm/diagnostic_output"
    assert (
        archive.public_base_url
        == "https://web.lcrc.anl.gov/public/e3sm/diagnostic_output"
    )


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
    assert _discover(tmp_path, BASE_URL) == []


def test_discovery_rejects_case_and_group_mismatches(tmp_path: Path) -> None:
    directory = _case(tmp_path, "development/type/group/case")
    settings = next(directory.glob("*.settings"))
    settings.write_text(
        settings.read_text().replace("case_name = case", "case_name = wrong")
    )
    assert _discover(tmp_path, BASE_URL) == []


def test_parse_settings_rejects_duplicate_required_key(tmp_path: Path) -> None:
    settings = tmp_path / "provenance.settings"
    settings.write_text("case_name = one\ncase_name = two\n", encoding="utf-8")
    with pytest.raises(ValueError):
        _parse_settings_bytes(settings.read_bytes())


def test_settings_reader_rejects_oversized_file(tmp_path: Path) -> None:
    settings = tmp_path / "provenance.settings"
    settings.write_bytes(b"x" * (64 * 1024 + 1))
    with pytest.raises(ValueError):
        _read_settings_bytes(settings)


def test_discovery_rejects_settings_symlink_outside_root(tmp_path: Path) -> None:
    directory = _case(tmp_path, "production/type/case")
    settings = next(directory.glob("*.settings"))
    outside = tmp_path.parent / "outside.settings"
    outside.write_text(settings.read_text(), encoding="utf-8")
    settings.unlink()
    settings.symlink_to(outside)
    assert _discover(tmp_path, BASE_URL) == []


def test_discovery_rejects_external_output_directory_symlink(tmp_path: Path) -> None:
    directory = _case(tmp_path, "production/type/case")
    (directory / "index.html").unlink()
    outside = tmp_path.parent / "outside-output"
    outside.mkdir(exist_ok=True)
    (outside / "index.html").write_text("ready")
    (directory / "output").symlink_to(outside, target_is_directory=True)
    assert _discover(tmp_path, BASE_URL) == []


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


class _Client:
    def __init__(self, get_response: httpx.Response) -> None:
        self.get_response = get_response
        self.get_calls: list[dict] = []
        self.post_calls: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def get(self, *_args, **kwargs):
        self.get_calls.append(kwargs)
        return self.get_response

    def post(self, *_args, **kwargs):
        self.post_calls.append(kwargs)
        return httpx.Response(204)


def test_run_submits_exact_payload_and_bearer_auth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _case(tmp_path, "production/type/case")
    client = _Client(httpx.Response(200, json=None))
    monkeypatch.setattr(
        "app.scripts.ingestion.diagnostics_link_scanner._resolve_archive",
        lambda _machine: DiagnosticsArchive(str(tmp_path), BASE_URL),
    )
    monkeypatch.setattr(
        "app.scripts.ingestion.diagnostics_link_scanner.httpx.Client",
        lambda **_kwargs: client,
    )
    monkeypatch.setenv("SIMBOARD_API_BASE_URL", "https://api.example.org")
    monkeypatch.setenv("SIMBOARD_API_TOKEN", "token")
    monkeypatch.setenv("DRY_RUN", "false")
    assert run() == 0
    assert client.get_calls[0]["params"] == {
        "machine": "perlmutter",
        "archive_relative_case_path": "production/type/case",
    }
    assert client.post_calls[0]["headers"] == {"Authorization": "Bearer token"}
    assert client.post_calls[0]["json"]["diagnostics"][0]["name"] == "zppy diagnostics"


def test_dry_run_requires_no_api_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _case(tmp_path, "production/type/case")
    monkeypatch.setattr(
        "app.scripts.ingestion.diagnostics_link_scanner._resolve_archive",
        lambda _machine: DiagnosticsArchive(str(tmp_path), BASE_URL),
    )
    monkeypatch.delenv("SIMBOARD_API_BASE_URL", raising=False)
    monkeypatch.delenv("SIMBOARD_API_TOKEN", raising=False)
    monkeypatch.setenv("DRY_RUN", "true")
    assert run() == 0
    assert (
        "Dry run complete: 1 diagnostics candidate(s) found." in capsys.readouterr().out
    )


def test_run_defers_after_exhausted_state_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _case(tmp_path, "production/type/case")
    client = _Client(httpx.Response(503))
    monkeypatch.setattr(
        "app.scripts.ingestion.diagnostics_link_scanner.time.sleep", lambda _: None
    )
    monkeypatch.setattr(
        "app.scripts.ingestion.diagnostics_link_scanner._resolve_archive",
        lambda _machine: DiagnosticsArchive(str(tmp_path), BASE_URL),
    )
    monkeypatch.setattr(
        "app.scripts.ingestion.diagnostics_link_scanner.httpx.Client",
        lambda **_kwargs: client,
    )
    monkeypatch.setenv("SIMBOARD_API_BASE_URL", "https://api.example.org")
    monkeypatch.setenv("SIMBOARD_API_TOKEN", "token")
    monkeypatch.setenv("DRY_RUN", "false")
    run()
    assert client.post_calls == []
