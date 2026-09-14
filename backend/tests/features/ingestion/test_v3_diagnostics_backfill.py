from pathlib import Path

import httpx

from app.scripts.ingestion.v3_data import diagnostics_backfill as backfill


def test_dry_run_defaults_to_true_and_matches_scanner_values(monkeypatch) -> None:
    monkeypatch.delenv("DRY_RUN", raising=False)
    assert backfill._dry_run_requested(False) is True

    monkeypatch.setenv("DRY_RUN", "false")
    assert backfill._dry_run_requested(False) is False

    monkeypatch.setenv("DRY_RUN", "yes")
    assert backfill._dry_run_requested(False) is True
    assert backfill._dry_run_requested(True) is True


def test_diagnostics_source_root_is_parent_of_reviewed_archive() -> None:
    assert backfill._diagnostics_source_root(
        "/lcrc/group/e3sm/public_html/diagnostic_output/diagnostics_archive"
    ) == Path("/lcrc/group/e3sm/public_html/diagnostic_output")


def test_api_base_url_accepts_host_or_versioned_api_url() -> None:
    assert (
        backfill._api_base_url("https://simboard.example") == "https://simboard.example"
    )


def test_reconciliation_fields_include_counts_and_case_lists() -> None:
    report = {
        "copied": ["copied"],
        "linked": [],
        "missing": [],
        "unmapped": ["unmapped"],
        "zero_matches": [],
        "ambiguous": ["duplicate-a", "duplicate-b"],
        "machine_skipped": ["other-machine"],
        "failed": [],
    }

    fields = backfill._reconciliation_fields(report, 4)

    assert fields["selected_target_count"] == 4
    assert fields["copied_count"] == "1/4"
    assert fields["ambiguous_count"] == "2/4"
    assert fields["ambiguous_cases"] == ["duplicate-a", "duplicate-b"]
    assert fields["machine_skipped_count"] == f"1/{len(backfill.V3_DIAGNOSTIC_TARGETS)}"
    assert (
        backfill._api_base_url("https://simboard.example/api/v1/")
        == "https://simboard.example"
    )


def test_manifest_covers_v3_cases_and_bonus_target() -> None:
    targets = {target.case_name: target for target in backfill.V3_DIAGNOSTIC_TARGETS}

    assert "LR_ensemble" not in targets
    assert "RRM_ensemble" not in targets
    assert targets["v3.LR.piControl"].source == "ac.golaz/E3SMv3/v3.LR.piControl"
    assert targets["v3.LR.amip_bonus_0101"] == backfill.Target(
        "v3.LR.amip_bonus_0101",
        "ac.wlin/E3SMv3/v3.LR.amip_0101",
        "perlmutter",
        True,
    )
    assert targets["v3.LR.piClim-histGHG_0101"].source == "ac.kzhang/E3SMv3"


def test_latest_cfg_selects_newest_valid_timestamp(tmp_path: Path) -> None:
    older = tmp_path / "provenance.20260810_120000_000000.cfg"
    newer = tmp_path / "provenance.20260811_120000_000000.cfg"
    older.write_text("old")
    newer.write_text("new")
    (tmp_path / "provenance.invalid.cfg").write_text("invalid")

    assert backfill._latest_cfg(tmp_path) == newer


def test_copy_omits_source_settings_and_write_settings_preserves_cfg(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    cfg = source / "provenance.20260811_120000_000000.cfg"
    cfg.write_text("immutable cfg")
    cfg.with_suffix(".settings").write_text("old settings")
    (source / "index.html").write_text("output")

    backfill._copy_diagnostics(source, destination)
    copied_cfg = backfill._latest_cfg(destination)
    assert copied_cfg is not None
    assert copied_cfg.read_text() == "immutable cfg"
    assert not copied_cfg.with_suffix(".settings").exists()

    settings = backfill._write_settings(
        copied_cfg,
        {"name": "case", "hpcUsername": "user", "caseGroup": None},
        "perlmutter",
        "http://portal.nersc.gov/cfs/e3sm/diagnostics_archive",
    )

    assert copied_cfg.read_text() == "immutable cfg"
    assert settings.read_text() == (
        "case_name = case\n"
        "machine = perlmutter\n"
        "hpc_username = user\n"
        "diagnostics_url = http://portal.nersc.gov/cfs/e3sm/diagnostics_archive/production/case\n"
    )


def test_write_settings_includes_case_group_and_refuses_replacement(
    tmp_path: Path,
) -> None:
    cfg = tmp_path / "provenance.20260811_120000_000000.cfg"
    cfg.write_text("cfg")
    backfill._write_settings(
        cfg,
        {"name": "case", "hpcUsername": "user", "caseGroup": "v3.LR"},
        "chrysalis",
        "https://web.lcrc.anl.gov/public/e3sm/diagnostic_output/diagnostics_archive",
    )

    assert "case_group = v3.LR\n" in cfg.with_suffix(".settings").read_text()
    try:
        backfill._write_settings(
            cfg,
            {"name": "case", "hpcUsername": "user"},
            "chrysalis",
            "https://example.org",
        )
    except FileExistsError:
        pass
    else:
        raise AssertionError("settings replacement must be rejected")


def test_case_resolution_filters_by_exact_name_and_machine_id() -> None:
    request = httpx.Request("GET", "https://api.example/api/v1/cases")

    class Client:
        def __init__(self) -> None:
            self.params: dict | None = None

        def get(self, _url: str, **kwargs) -> httpx.Response:
            self.params = kwargs["params"]
            return httpx.Response(
                200,
                json={"items": [{"name": "case"}], "total": 1},
                request=request,
            )

    client = Client()
    result = backfill._resolve_cases(
        client,  # type: ignore[arg-type]
        "https://api.example",
        backfill.Target("case", "source", "chrysalis"),
        "machine-id",
    )

    assert result == ([{"name": "case"}], 1)
    assert client.params == {
        "name": "case",
        "machine_id": "machine-id",
        "page_size": 100,
    }


def test_backfill_uses_explicit_bonus_source_directory(
    tmp_path: Path, monkeypatch
) -> None:
    source_root = tmp_path / "source-root"
    source = source_root / "ac.wlin/E3SMv3/v3.LR.amip_0101"
    source.mkdir(parents=True)
    (source / "provenance.20260811_120000_000000.cfg").write_text("cfg")
    (source / "index.html").write_text("output")
    target = next(
        target
        for target in backfill.V3_DIAGNOSTIC_TARGETS
        if target.case_name == "v3.LR.amip_bonus_0101"
    )
    monkeypatch.setattr(
        backfill,
        "_resolve_cases",
        lambda *_args: (
            [
                {
                    "name": target.case_name,
                    "hpcUsername": "ac.wlin",
                    "caseGroup": "v3.LR",
                }
            ],
            1,
        ),
    )

    assert (
        backfill._backfill_target(
            client=None,  # type: ignore[arg-type]
            api_base="https://api.example",
            archive_root=tmp_path / "archive",
            public_base_url="https://archive.example",
            source_root=source_root,
            target=target,
            machine="perlmutter",
            machine_id="machine-id",
            dry_run=False,
        )
        == "copied"
    )
    destination = tmp_path / "archive/production/v3.LR/v3.LR.amip_bonus_0101"
    assert (destination / "index.html").is_file()
    assert (
        "case_name = v3.LR.amip_bonus_0101\n"
        in (destination / "provenance.20260811_120000_000000.settings").read_text()
    )
