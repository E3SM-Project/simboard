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
    assert (
        archive.root
        == "/lcrc/group/e3sm/public_html/diagnostic_output/diagnostics_archive"
    )
    assert (
        archive.public_base_url
        == "https://web.lcrc.anl.gov/public/e3sm/diagnostic_output/diagnostics_archive"
    )


@pytest.mark.parametrize("machine_name", [None, "   "])
def test_run_requires_machine_name_before_archive_resolution(
    monkeypatch: pytest.MonkeyPatch, machine_name: str | None
) -> None:
    def resolve_archive(_machine: str) -> DiagnosticsArchive:
        pytest.fail("archive resolution must not be called without MACHINE_NAME")
        raise AssertionError("unreachable")

    monkeypatch.setattr(
        "app.scripts.ingestion.diagnostics_link_scanner._resolve_archive",
        resolve_archive,
    )
    if machine_name is None:
        monkeypatch.delenv("MACHINE_NAME", raising=False)
    else:
        monkeypatch.setenv("MACHINE_NAME", machine_name)

    with pytest.raises(ValueError, match="MACHINE_NAME is required"):
        run()


def _case(root: Path, path: str, *, timestamp: str = "20260811_120000_000000") -> Path:
    directory = root / path
    directory.mkdir(parents=True)
    cfg = directory / f"provenance.{timestamp}.cfg"
    cfg.write_text("cfg", encoding="utf-8")
    case_group = (
        f"case_group = {directory.parent.name}\n"
        if len(directory.relative_to(root).parts) == 3
        else ""
    )
    cfg.with_suffix(".settings").write_text(
        f"case_name = {directory.name}\nmachine = perlmutter\nhpc_username = user\n"
        f"{case_group}"
        "diagnostics_url = https://diagnostics.example.org/archive/case\n",
        encoding="utf-8",
    )
    (directory / "index.html").write_text("ready", encoding="utf-8")
    return directory


def test_newest_missing_settings_defers_without_stale_fallback(tmp_path: Path) -> None:
    directory = _case(tmp_path, "production/type/case")
    (directory / "provenance.20260812_120000_000000.cfg").write_text("cfg")
    assert _discover(tmp_path, BASE_URL, "perlmutter") == []


@pytest.mark.parametrize(
    ("path", "expected_group"),
    [("development/case", None), ("development/group/case", "group")],
)
def test_discovery_accepts_supported_archive_layouts(
    tmp_path: Path, path: str, expected_group: str | None
) -> None:
    directory = _case(tmp_path, path)
    candidates = _discover(tmp_path, BASE_URL, "perlmutter")

    assert [candidate.path.parent for candidate in candidates] == [directory]
    assert candidates[0].values.get("case_group") == expected_group


def test_discovery_requires_machine_matching_configured_archive(tmp_path: Path) -> None:
    directory = _case(tmp_path, "development/case")

    matching = _discover(tmp_path, BASE_URL, "perlmutter")
    mismatching = _discover(tmp_path, BASE_URL, "chrysalis")

    assert [candidate.path.parent for candidate in matching] == [directory]
    assert mismatching == []


@pytest.mark.parametrize("path", ["development", "development/group/extra/case"])
def test_discovery_rejects_unsupported_archive_layouts(
    tmp_path: Path, path: str
) -> None:
    _case(tmp_path, path)
    assert _discover(tmp_path, BASE_URL, "perlmutter") == []


def test_discovery_rejects_case_name_mismatch(tmp_path: Path) -> None:
    directory = _case(tmp_path, "development/group/case")
    settings = next(directory.glob("*.settings"))
    settings.write_text(
        settings.read_text().replace("case_name = case", "case_name = wrong")
    )
    assert _discover(tmp_path, BASE_URL, "perlmutter") == []


@pytest.mark.parametrize("replacement", ["case_group = wrong", ""])
def test_discovery_rejects_case_group_mismatch(
    tmp_path: Path, replacement: str
) -> None:
    directory = _case(tmp_path, "development/group/case")
    settings = next(directory.glob("*.settings"))
    settings.write_text(settings.read_text().replace("case_group = group", replacement))
    assert _discover(tmp_path, BASE_URL, "perlmutter") == []


def test_discovery_skips_malformed_timestamp_without_aborting(tmp_path: Path) -> None:
    directory = _case(tmp_path, "production/group/valid")
    (directory / "provenance.20261311_120000_000000.cfg").write_text("cfg")

    candidates = _discover(tmp_path, BASE_URL, "perlmutter")

    assert [candidate.path.parent for candidate in candidates] == [directory]


@pytest.mark.parametrize(
    "diagnostics_path",
    [
        "/archive/../outside",
        "/archive/%2e%2e/outside",
        "/archive%2f..%2foutside",
        "/archive/%252e%252e%252foutside",
    ],
)
def test_discovery_rejects_diagnostics_url_path_traversal(
    tmp_path: Path, diagnostics_path: str
) -> None:
    directory = _case(tmp_path, "production/group/case")
    settings = next(directory.glob("*.settings"))
    settings.write_text(
        settings.read_text().replace(
            "https://diagnostics.example.org/archive/case",
            f"https://diagnostics.example.org{diagnostics_path}",
        )
    )

    assert _discover(tmp_path, BASE_URL, "perlmutter") == []


def test_discovery_accepts_normalized_diagnostics_url_within_archive(
    tmp_path: Path,
) -> None:
    directory = _case(tmp_path, "production/group/case")
    settings = next(directory.glob("*.settings"))
    settings.write_text(
        settings.read_text().replace(
            "https://diagnostics.example.org/archive/case",
            "https://diagnostics.example.org/archive/group/../case",
        )
    )

    assert [
        candidate.path.parent
        for candidate in _discover(tmp_path, BASE_URL, "perlmutter")
    ] == [directory]


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
    assert _discover(tmp_path, BASE_URL, "perlmutter") == []


def test_discovery_rejects_external_output_directory_symlink(tmp_path: Path) -> None:
    directory = _case(tmp_path, "production/type/case")
    (directory / "index.html").unlink()
    outside = tmp_path.parent / "outside-output"
    outside.mkdir(exist_ok=True)
    (outside / "index.html").write_text("ready")
    (directory / "output").symlink_to(outside, target_is_directory=True)
    assert _discover(tmp_path, BASE_URL, "perlmutter") == []


def test_discovery_continues_after_published_output_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    failing_case = _case(tmp_path, "production/type/failing")
    valid_case = _case(tmp_path, "production/type/valid")
    for case_dir, case_name in ((failing_case, "failing"), (valid_case, "valid")):
        settings = next(case_dir.glob("*.settings"))
        settings.write_text(
            settings.read_text().replace("case_name = case", f"case_name = {case_name}")
        )
    events: list[tuple[str, dict | None]] = []

    def published_output(case_dir: Path, _root: Path) -> bool:
        if case_dir == failing_case:
            raise OSError("output unavailable")
        return True

    monkeypatch.setattr(
        "app.scripts.ingestion.diagnostics_link_scanner._published_output",
        published_output,
    )
    monkeypatch.setattr(
        "app.scripts.ingestion.diagnostics_link_scanner._log_event",
        lambda event, fields=None: events.append((event, fields)),
    )

    candidates = _discover(tmp_path, BASE_URL, "perlmutter")

    assert [candidate.path.parent for candidate in candidates] == [valid_case]
    assert (
        "diagnostics_scanner_invalid_provenance",
        {
            "provenance_path": "production/type/failing/"
            "provenance.20260811_120000_000000.cfg",
            "reason": "output unavailable",
        },
    ) in events


def test_retry_helper_retries_transient_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = [httpx.Response(503), httpx.Response(204)]
    events: list[tuple[str, dict | None]] = []
    monkeypatch.setattr(
        "app.scripts.ingestion.diagnostics_link_scanner.time.sleep", lambda _: None
    )
    monkeypatch.setattr(
        "app.scripts.ingestion.diagnostics_link_scanner._log_event",
        lambda event, fields=None: events.append((event, fields)),
    )
    response = _request_with_retry(
        lambda *_args, **_kwargs: responses.pop(0), "https://x"
    )
    assert response is not None
    assert response.status_code == 204
    retry_fields = next(
        fields
        for event, fields in events
        if event == "diagnostics_scanner_request_retry_scheduled"
    )
    assert retry_fields == {
        "attempt": 1,
        "max_attempts": 3,
        "status_code": 503,
        "request_error": False,
    }


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
    events: list[tuple[str, dict | None]] = []
    monkeypatch.setattr(
        "app.scripts.ingestion.diagnostics_link_scanner._resolve_archive",
        lambda _machine: DiagnosticsArchive(str(tmp_path), BASE_URL),
    )
    monkeypatch.setattr(
        "app.scripts.ingestion.diagnostics_link_scanner.httpx.Client",
        lambda **_kwargs: client,
    )
    monkeypatch.setattr(
        "app.scripts.ingestion.diagnostics_link_scanner._log_event",
        lambda event, fields=None: events.append((event, fields)),
    )
    monkeypatch.setenv("SIMBOARD_API_BASE_URL", "https://api.example.org")
    monkeypatch.setenv("SIMBOARD_API_TOKEN", "token")
    monkeypatch.setenv("MACHINE_NAME", "pm-gpu")
    monkeypatch.setenv("DRY_RUN", "false")
    assert run() == 0
    assert client.get_calls[0]["params"] == {
        "machine": "perlmutter",
        "archive_relative_case_path": "production/type/case",
    }
    assert client.post_calls[0]["headers"] == {"Authorization": "Bearer token"}
    assert client.post_calls[0]["json"]["machine"] == "perlmutter"
    assert client.post_calls[0]["json"]["diagnostics"][0]["name"] == "zppy diagnostics"
    startup_fields = next(
        fields
        for event, fields in events
        if event == "diagnostics_scanner_startup_configuration"
    )
    assert startup_fields is not None
    assert startup_fields["has_api_token"] is True
    assert "token" not in startup_fields
    assert (
        "diagnostics_scanner_link_submitted",
        {"archive_relative_case_path": "production/type/case", "status_code": 204},
    ) in events


def test_dry_run_requires_no_api_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _case(tmp_path, "production/type/case")
    monkeypatch.setattr(
        "app.scripts.ingestion.diagnostics_link_scanner._resolve_archive",
        lambda _machine: DiagnosticsArchive(str(tmp_path), BASE_URL),
    )
    monkeypatch.delenv("SIMBOARD_API_BASE_URL", raising=False)
    monkeypatch.delenv("SIMBOARD_API_TOKEN", raising=False)
    monkeypatch.setenv("MACHINE_NAME", "perlmutter")
    monkeypatch.setenv("DRY_RUN", "true")
    events: list[tuple[str, dict | None]] = []
    monkeypatch.setattr(
        "app.scripts.ingestion.diagnostics_link_scanner._log_event",
        lambda event, fields=None: events.append((event, fields)),
    )
    assert run() == 0
    candidate_events = [
        fields
        for event, fields in events
        if event == "diagnostics_scanner_dry_run_candidate"
    ]
    assert len(candidate_events) == 1
    candidate_event = candidate_events[0]
    assert candidate_event is not None
    assert candidate_event["archive_relative_case_path"] == "production/type/case"
    assert (
        candidate_event["settings_filename"]
        == "provenance.20260811_120000_000000.settings"
    )
    assert isinstance(candidate_event["fingerprint"], str)
    assert events[-1] == (
        "diagnostics_scanner_completed",
        {
            "discovered_candidates": 1,
            "dry_run_candidates": 1,
            "unchanged_candidates": 0,
            "deferred_state_lookups": 0,
            "submitted_links": 0,
            "failed_link_submissions": 0,
        },
    )


def test_run_defers_after_exhausted_state_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _case(tmp_path, "production/type/case")
    client = _Client(httpx.Response(503))
    events: list[tuple[str, dict | None]] = []
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
    monkeypatch.setattr(
        "app.scripts.ingestion.diagnostics_link_scanner._log_event",
        lambda event, fields=None: events.append((event, fields)),
    )
    monkeypatch.setenv("SIMBOARD_API_BASE_URL", "https://api.example.org")
    monkeypatch.setenv("SIMBOARD_API_TOKEN", "token")
    monkeypatch.setenv("MACHINE_NAME", "perlmutter")
    monkeypatch.setenv("DRY_RUN", "false")
    run()
    assert client.post_calls == []
    assert (
        "diagnostics_scanner_request_retry_exhausted",
        {"attempts": 3, "status_code": 503, "request_error": False},
    ) in events
    assert (
        "diagnostics_scanner_state_lookup_deferred",
        {"archive_relative_case_path": "production/type/case", "status_code": 503},
    ) in events
