"""Tests of the public ingestion log contract without live API calls."""

import io
import json
import logging
import runpy
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from app.features.ingestion.parsers.parser import (
    ArchiveValidationError,
    IncompleteArchiveError,
)
from app.scripts.ingestion import archive_logging as logs
from app.scripts.ingestion import nersc_archive_ingestor as runner
from app.scripts.ingestion.archive_ingestor_core import (
    IngestionRequestError,
    IngestorConfig,
    _log_event,
)


@pytest.fixture
def output(monkeypatch):
    """Capture the real scoped console handler, including DEBUG delivery."""
    stream = io.StringIO()
    configure = logs.configure

    def capture(logger, level_name=None):
        configure(logger, level_name)
        logs._handler.setStream(stream)

    monkeypatch.setattr(logs, "configure", capture)
    monkeypatch.delenv("SIMBOARD_INGESTION_LOG_LEVEL", raising=False)
    monkeypatch.delenv("SIMBOARD_API_TOKEN", raising=False)
    monkeypatch.delenv("SIMBOARD_ENV_FILE", raising=False)
    return stream


def records(stream):
    """Parse only canonical single-line payloads, not human summaries."""
    return [
        json.loads(line.split("event=run_metrics payload=", 1)[1])
        for line in stream.getvalue().splitlines()
        if "event=run_metrics payload=" in line
    ]


def assert_case_first_summary(stream):
    """Verify the rendered hierarchy, including serialized JSON key order."""
    lines = [
        line.split("RUN_SUMMARY ", 1)[1]
        for line in stream.getvalue().splitlines()
        if "RUN_SUMMARY " in line
    ]
    labels = [line.split(":", 1)[0] for line in lines[:-2]]
    assert labels == [
        "Cases found",
        "Cases eligible",
        "  Selected",
        "  Deferred",
        "Selected case outcomes",
        "  Succeeded",
        "  Failed",
        "  Not attempted",
        "Executions found",
        "  Selected",
        "  Skipped",
        "  Incomplete",
        "  Invalid",
        "  Unreadable",
        "  Deferred",
    ]
    assert lines[-2].startswith("status=")
    assert lines[-1].startswith("event=run_metrics payload=")
    assert len(records(stream)) == 1
    record = records(stream)[0]
    assert list(record).index("cases") < list(record).index("executions")
    assert lines[-1].index('"cases":') < lines[-1].index('"executions":')


def case_fields(case, **counts):
    return {
        "case": case,
        **{
            key: counts.get(outcome, 0)
            for outcome, key in zip(logs.OUTCOMES, logs.OUTCOME_FIELDS, strict=True)
        },
    }


def test_invocation_reenables_disabled_logger_and_restores_state(output, monkeypatch):
    logger = logging.getLogger("app.scripts.ingestion.archive_ingestor_core")
    # Alembic's fileConfig disables existing loggers during full-suite setup.
    monkeypatch.setattr(logger, "disabled", True)
    previous_handlers = logger.handlers[:]
    previous_level = logger.level
    previous_propagate = logger.propagate

    @logs.logged_main
    def main():
        assert not logger.disabled
        _log_event("state_fetch_failed", {"error": "unavailable"})
        return 1

    assert main() == 1
    assert "ERROR CONFIG" in output.getvalue()
    assert records(output)[0]["status"] == "failure"
    assert logger.disabled
    assert logger.handlers == previous_handlers
    assert logger.level == previous_level
    assert logger.propagate == previous_propagate


@pytest.mark.parametrize("level", ["INFO", "DEBUG", "WARNING", "ERROR", "CRITICAL"])
def test_levels_categories_and_metrics_delivery(output, monkeypatch, level):
    monkeypatch.setenv("SIMBOARD_INGESTION_LOG_LEVEL", level.lower())

    @logs.logged_main
    def main():
        _log_event(
            "execution_collection_decision",
            {
                "case": "a",
                "execution_id": "e1",
                "decision": "rejected",
                "reason": "already_processed",
            },
        )
        _log_event("archive_scan_progress", {"directories_visited": 250})
        _log_event("case_collection_summary", case_fields("a", skipped=1))
        _log_event("state_fetch_failed", {"error": "unavailable"})
        return 1

    assert main() == 1
    text = output.getvalue()
    assert ("event=execution_decision" in text) == (level == "DEBUG")
    assert ("event=archive_scan_progress" in text) == (level == "DEBUG")
    assert ("event=case_discovered" in text) == (level in {"DEBUG", "INFO"})
    assert len(records(output)) == (1 if level in {"DEBUG", "INFO"} else 0)
    assert ("ERROR CONFIG" in text) == (level != "CRITICAL")
    if records(output):
        record = records(output)[0]
        assert f"Run ID: {record['run_id']}" in text
        assert "run_id=" not in text
        assert text.count(record["run_id"]) == 2
        assert record["executions"]["total"] is None


def test_invalid_level_stops_before_ingestion_and_has_failure_metrics(
    output, monkeypatch
):
    monkeypatch.setenv("SIMBOARD_INGESTION_LOG_LEVEL", "verbose")

    @logs.logged_main
    def main():
        pytest.fail("invalid logging configuration must not start ingestion")

    assert main() == 1
    assert "SIMBOARD_INGESTION_LOG_LEVEL must be" in output.getvalue()
    assert records(output)[0]["status"] == "failure"


@pytest.mark.parametrize("level", ["INFO", "DEBUG", "WARNING", "ERROR", "CRITICAL"])
@pytest.mark.parametrize("scan_mode", ["staging", "archive"])
@pytest.mark.parametrize("remote_state", [True, False])
def test_readable_configuration(
    output, monkeypatch, tmp_path, level, scan_mode, remote_state
):
    from app.scripts.ingestion.archive_workflow import _log_startup_configuration

    monkeypatch.setenv("SIMBOARD_INGESTION_LOG_LEVEL", level)
    monkeypatch.setenv("SIMBOARD_API_TOKEN", "secret-token")
    config = IngestorConfig(
        "https://user:pass@example.test/api?token=secret-token",
        "secret-token",
        tmp_path,
        "chrysalis",
        True,
        None,
        3,
        60,
        scan_mode=scan_mode,
        archive_year_start="2025-01" if scan_mode == "archive" else None,
        dry_run_use_remote_state=remote_state,
    )

    @logs.logged_main
    def main():
        logs.record_config(config)
        _log_event("run_started", {"mode": "dry-run", "scan_mode": scan_mode})
        _log_startup_configuration(config)
        _log_event("case_collection_summary", case_fields("a", incomplete=1))
        return 0

    assert main() == 0
    text = output.getvalue()
    if level not in {"INFO", "DEBUG"}:
        assert text == ""
        return
    assert text.count("Run ID:") == 1
    assert text.count("CONFIG Machine: chrysalis") == 1
    assert "CONFIG Mode: dry run" in text
    assert f"CONFIG Scan: {scan_mode}" in text
    assert "CONFIG Maximum cases: unlimited" in text
    assert "CONFIG Maximum attempts: 3" in text
    assert "CONFIG Request timeout: 60 seconds" in text
    assert "CONFIG API token: configured" in text
    assert (
        "CONFIG Archive range: "
        + (
            "2025-01 to unbounded"
            if scan_mode == "archive"
            else "not applicable (staging)"
        )
        in text
    )
    assert (
        "CONFIG Remote state: "
        + ("enabled (read-only)" if remote_state else "disabled (offline)")
        in text
    )
    assert text.index("CONFIG Machine:") < text.index("event=case_discovered")
    assert "event=run_started" not in text
    assert "startup_configuration_" not in text
    assert "secret-token" not in text and "user:pass" not in text
    assert text.count(records(output)[0]["run_id"]) == 2


@pytest.mark.parametrize("kind", ["hpc", "nersc", "v3"])
def test_runner_configuration_precedes_work(output, monkeypatch, tmp_path, kind):
    from app.scripts.ingestion import hpc_upload_archive_ingestor as hpc
    from app.scripts.ingestion.v3_data import lcrc_v3_archive_ingestor as v3

    module = {"hpc": hpc, "nersc": runner, "v3": v3}[kind]
    config = IngestorConfig(
        "https://example.test",
        "token",
        tmp_path,
        "chrysalis",
        True,
        2,
        3,
        60,
        scan_mode="archive" if kind == "v3" else "staging",
    )
    monkeypatch.setattr(
        module,
        "_build_v3_config_from_env" if kind == "v3" else "_build_config_from_env",
        lambda: config,
    )

    def work(config, **kwargs):
        text = output.getvalue()
        assert text.count("CONFIG Machine: chrysalis") == 1
        assert "CONFIG Maximum cases: 2" in text
        if kind == "v3":
            assert f"CONFIG Source URL: {v3.V3_SIMULATION_TABLE_URL}" in text
        return 0

    monkeypatch.setattr(
        module, "_run_upload_ingestor" if kind == "v3" else "_run_ingestor", work
    )
    assert module.main() == 0
    assert len(records(output)) == 1


def test_invalid_configuration_has_identity_without_config_block(output, monkeypatch):
    def invalid():
        raise ValueError("invalid configuration")

    monkeypatch.setattr(runner, "_build_config_from_env", invalid)
    assert runner.main() == 1
    text = output.getvalue()
    assert f"Run ID: {records(output)[0]['run_id']}" in text
    assert "event=configuration_error" in text
    assert "CONFIG Machine:" not in text


def test_logging_failures_do_not_change_result_or_exception(output, monkeypatch):
    logger = logging.getLogger("app.scripts.ingestion.archive_ingestor_core")
    original = (logger.level, logger.propagate, logger.handlers[:])

    def broken(*args, **kwargs):
        raise OSError("broken output")

    monkeypatch.setattr(logger, "info", broken)

    @logs.logged_main
    def main():
        _log_event("configuration_error", {"error": "handled"})
        return 7

    assert main() == 7
    assert (logger.level, logger.propagate, logger.handlers) == original

    @logs.logged_main
    def unexpected():
        raise RuntimeError("operational exception")

    with pytest.raises(RuntimeError, match="operational exception"):
        unexpected()
    assert logs._context.get() is None


def test_repeated_configuration_no_duplicates_and_redaction(output, monkeypatch):
    monkeypatch.setenv("SIMBOARD_API_TOKEN", "secret-token")
    monkeypatch.setenv("SIMBOARD_ENV_FILE", "/private/env.dev.sh")

    @logs.logged_main
    def main():
        logger = logging.getLogger("app.scripts.ingestion.archive_ingestor_core")
        logs.configure(logger)
        logs.configure(logger)
        _log_event(
            "configuration_error",
            {
                "error": "secret-token\nhttps://user:pass@example.test/a?token=other",
                "authorization": "Bearer hidden",
            },
        )
        return 1

    main()
    main()
    text = output.getvalue()
    assert len(records(output)) == 2
    assert records(output)[0]["run_id"] != records(output)[1]["run_id"]
    assert records(output)[0]["environment"] == "env.dev.sh"
    assert (
        "secret-token" not in text
        and "user:pass" not in text
        and "token=other" not in text
    )
    assert "Bearer hidden" not in text
    assert text.count("event=configuration_error") == 2


@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize("level", ["INFO", "DEBUG"])
def test_real_discovery_partitions_and_submission_results(
    tmp_path, monkeypatch, output, dry_run, level
):
    root = tmp_path / "performance_archive"
    for case, ids in {
        "a": ["100.1-1", "101.1-1"],
        "b": ["200.1-1"],
        "c": ["300.1-1"],
        "d": ["400.1-1"],
        "e": ["500.1-1"],
        "f": ["600.1-1"],
    }.items():
        for execution in ids:
            (root / case / execution).mkdir(parents=True)
    config = IngestorConfig(
        "https://example.test", "token", root, "chrysalis", dry_run, 1, 1, 30
    )
    state = {"cases": {str(root / "a"): {"processed_execution_ids": ["100.1-1"]}}}
    monkeypatch.setenv("SIMBOARD_INGESTION_LOG_LEVEL", level)
    monkeypatch.setattr(runner, "_build_config_from_env", lambda: config)
    monkeypatch.setattr(
        runner,
        "_prepare_run_state",
        lambda config: (state, set(), "https://example.test"),
    )
    calls = []

    def locate(path):
        case = Path(path).parent.name
        if case == "c":
            raise IncompleteArchiveError([{"message": "missing"}])
        if case == "d":
            raise ArchiveValidationError([{"message": "invalid"}])
        if case == "e":
            raise OSError("unreadable")
        return {}

    def post(*args, **kwargs):
        calls.append(args[2])
        raise IngestionRequestError("failed", 400, False)

    run = runner._run_ingestor
    monkeypatch.setattr(
        runner,
        "_run_ingestor",
        lambda config: run(
            config,
            metadata_locator=locate,
            post_request_fn=post,
            discovery_post_request_fn=lambda *a, **kw: {"status_code": 201, "body": {}},
        ),
    )
    assert runner.main() == (0 if dry_run else 1)
    assert_case_first_summary(output)
    record = records(output)[0]
    assert record["executions"] == {
        "total": 7,
        "selected": 1,
        "skipped": 1,
        "incomplete": 1,
        "invalid": 1,
        "unreadable": 1,
        "deferred": 2,
    }
    assert record["cases"] == {
        "found": 6,
        "eligible": 3,
        "selected": 1,
        "deferred": 2,
        "succeeded": 0,
        "failed": 0 if dry_run else 1,
        "not_attempted": 1 if dry_run else 0,
    }
    assert record["discovery_complete"] is True
    assert record["submission_complete"] is (not dry_run)
    assert len(calls) == (0 if dry_run else 1)
    assert record["duration_seconds"] >= 0
    assert record["started_at"].endswith("+00:00")
    assert len(records(output)) == 1
    for removed in (
        "run_summary_counts",
        "run_summary_outcomes",
        "dry_run_summary_counts",
        "dry_run_summary_candidates",
        "case_collection_begin",
        "dry_run_candidate",
        "dry_run_completed",
        "run_finished",
        "case_ingestion_retry_completed",
    ):
        assert f"event={removed}" not in output.getvalue()
    # The rendered case summaries are the exact contributors to run totals.
    lines = [
        line
        for line in output.getvalue().splitlines()
        if "event=case_discovered" in line
    ]
    for key, value in record["executions"].items():
        assert (
            sum(
                int(line.split(f"executions.{key}=", 1)[1].split()[0]) for line in lines
            )
            == value
        )


@pytest.mark.parametrize(
    "kind",
    ["empty", "before_scan", "before_submission", "before_empty_submission", "partial"],
)
def test_completeness_and_missing_counts(output, kind):
    @logs.logged_main
    def main():
        _log_event("run_started", {"mode": "ingest", "scan_mode": "staging"})
        if kind == "before_scan":
            return 1
        selected = 0 if kind in {"empty", "before_empty_submission"} else 2
        if selected:
            _log_event("case_collection_summary", case_fields("a", selected=2))
        logs.scan_finished(kind != "partial")
        _log_event(
            "scan_completed",
            {
                "submission_qualified_cases": selected,
                "selected_submission_cases": selected,
            },
        )
        if kind == "partial":
            _log_event("case_ingested", {"case_path": "a"})
        if kind == "empty":
            _log_event("run_completed", {})
        return 0 if kind == "empty" else 1

    main()
    assert_case_first_summary(output)
    record = records(output)[0]
    if kind == "before_scan":
        assert record["cases"]["selected"] is None
        assert record["executions"]["total"] is None
    else:
        cases = record["cases"]
        assert (
            cases["selected"]
            == cases["succeeded"] + cases["failed"] + cases["not_attempted"]
        )
        assert cases["eligible"] == cases["selected"] + cases["deferred"]
        assert record["submission_complete"] is (kind == "empty")
    assert record["discovery_complete"] is (kind not in {"before_scan", "partial"})


def test_test_only_consumer_deduplicates_and_reports_coverage():
    base = logs.metrics(logs.RunLog("test", selected=1, eligible=1), 1)
    complete = {
        **base,
        "run_id": "a",
        "environment": "dev",
        "dry_run": False,
        "discovery_complete": True,
        "executions": {"selected": 2},
    }
    partial = {
        **complete,
        "run_id": "b",
        "discovery_complete": False,
        "executions": {"selected": None},
    }
    other = {**complete, "run_id": "c", "environment": "prod"}
    dry = {**complete, "run_id": "d", "dry_run": True}
    lines = ["INFO event=run_summary_outcomes selected=999"] + [
        "prefix event=run_metrics payload=" + json.dumps(record)
        for record in (complete, complete, partial, other, dry)
    ]
    unique = {
        record["run_id"]: record for record in records(io.StringIO("\n".join(lines)))
    }
    groups = {}
    for record in unique.values():
        if record["dry_run"]:
            continue
        group = groups.setdefault(
            record["environment"],
            {"total": 0, "contributing": 0, "unavailable": 0, "incomplete": 0},
        )
        group["incomplete"] += not record["discovery_complete"]
        count = record["executions"]["selected"]
        if count is None:
            group["unavailable"] += 1
        else:
            group["total"] += count
            group["contributing"] += 1
    assert groups == {
        "dev": {"total": 2, "contributing": 1, "unavailable": 1, "incomplete": 1},
        "prod": {"total": 2, "contributing": 1, "unavailable": 0, "incomplete": 0},
    }


def test_cached_archive_observations_and_processed_staging_are_skipped(
    tmp_path, monkeypatch, output
):
    from app.scripts.ingestion.archive_discovery import _scan_archive
    from app.scripts.ingestion.archive_workflow import _log_scan_completed

    root = tmp_path / "OLD_PERF"
    paths = [
        root / "2025-01/performance_archive_2025_01_01_00_00_00/user/case-a",
        root / "2025-02/performance_archive_2025_02_01_00_00_00/user/case-a",
    ]
    for path in paths:
        for execution in ("100.1-1", "101.1-1", "102.1-1"):
            (path / execution).mkdir(parents=True)
    config = IngestorConfig(
        "https://example.test",
        "token",
        root,
        "chrysalis",
        True,
        None,
        1,
        30,
        scan_mode="archive",
    )
    state = {
        "cases": {},
        "discovery_results": {
            "user/case-a": [
                {"execution_id": "100.1-1", "outcome": "accepted"},
                {"execution_id": "101.1-1", "outcome": "rejected_incomplete"},
                {"execution_id": "102.1-1", "outcome": "rejected_invalid"},
            ]
        },
    }

    @logs.logged_main
    def main():
        logs.record_config(config)
        result = _scan_archive(
            config,
            state,
            metadata_locator=lambda path: pytest.fail("cached result revalidated"),
        )
        _, candidates, eligible, stats, _ = result
        _log_scan_completed(candidates, eligible, stats)
        return 0

    assert main() == 0
    record = records(output)[0]
    assert record["executions"] == {
        "total": 6,
        "selected": 1,
        "skipped": 1,
        "incomplete": 2,
        "invalid": 2,
        "unreadable": 0,
        "deferred": 0,
    }
    assert record["cases"]["found"] == 2
    assert record["cases"]["selected"] == 1

    # Persisted processed IDs skip validation even while files remain in staging.
    staging = tmp_path / "performance_archive"
    (staging / "user/case-a/100.1-1").mkdir(parents=True)
    config = replace(config, archive_root=staging, scan_mode="staging")
    state = {
        "cases": {
            str(staging / "user/case-a"): {"processed_execution_ids": ["100.1-1"]}
        }
    }
    assert main() == 0
    record = records(output)[1]
    assert record["executions"]["skipped"] == 1
    assert record["executions"]["selected"] == 0


def test_observation_failure_still_emits_raw_event(output):
    @logs.logged_main
    def main():
        _log_event("case_collection_summary", {"case": "malformed"})
        return 0

    assert main() == 0
    assert "event=case_collection_summary case=malformed" in output.getvalue()
    assert len(records(output)) == 1


@pytest.mark.parametrize("level", ["INFO", "DEBUG"])
def test_successful_submission_is_compact_with_debug_response_details(
    tmp_path, monkeypatch, output, level
):
    from app.scripts.ingestion.archive_ingestor_core import IngestionCandidate
    from app.scripts.ingestion.archive_workflow import _handle_ingest_run

    monkeypatch.setenv("SIMBOARD_INGESTION_LOG_LEVEL", level)
    config = IngestorConfig(
        "https://example.test", "token", tmp_path, "pm", False, None, 1, 30
    )
    candidate = IngestionCandidate(str(tmp_path / "a"), ["100.1-1"], ["100.1-1"], "fp")

    @logs.logged_main
    def main():
        logs.record_config(config)
        _log_event("case_collection_summary", case_fields("a", selected=1))
        _log_event(
            "scan_completed",
            {"submission_qualified_cases": 1, "selected_submission_cases": 1},
        )
        logs.scan_finished(True)
        return _handle_ingest_run(
            [candidate],
            config,
            "https://example.test/ingest",
            {"cases": {}},
            sleep_fn=lambda _: None,
            post_request_fn=lambda *args, **kwargs: {
                "status_code": 201,
                "body": {"created_count": 1, "duplicate_count": 0, "errors": []},
            },
        )

    assert main() == 0
    lines = output.getvalue().splitlines()
    submission = next(line for line in lines if "event=case_submission " in line)
    assert submission.endswith("event=case_submission case=a outcome=succeeded")
    details = [line for line in lines if "event=case_submission_details " in line]
    assert bool(details) == (level == "DEBUG")
    if details:
        assert (
            "attempts=1 created_count=1 duplicate_count=0 error_count=0" in details[0]
        )
    record = records(output)[0]
    assert len(records(output)) == 1
    assert record["cases"]["succeeded"] == 1
    assert record["cases"]["not_attempted"] == 0
    assert record["submission_complete"] is True


def test_public_execution_decision_order(output, monkeypatch):
    monkeypatch.setenv("SIMBOARD_INGESTION_LOG_LEVEL", "DEBUG")

    @logs.logged_main
    def main():
        _log_event(
            "execution_collection_decision",
            {
                "reason": "already_processed",
                "decision": "rejected",
                "execution_id": "e1",
                "case": "a",
            },
        )
        return 0

    assert main() == 0
    line = next(
        line
        for line in output.getvalue().splitlines()
        if "event=execution_decision" in line
    )
    assert line.endswith(
        "case=a execution_id=e1 outcome=skipped reason=already_processed"
    )


def test_unregistered_event_is_not_classified_by_substring():
    assert logs.presentation("example_attempt_progress", {}) == (
        "CONFIG",
        "example_attempt_progress",
        logging.INFO,
        {},
    )


@pytest.mark.parametrize(
    "event,fields,severity",
    [
        ("configuration_error", {}, "ERROR"),
        ("archive_root_missing", {}, "ERROR"),
        ("state_fetch_failed", {}, "ERROR"),
        ("archive_checkpoint_fetch_failed", {}, "ERROR"),
        ("archive_checkpoint_persistence_failed", {}, "ERROR"),
        ("discovery_results_persistence_failed", {}, "ERROR"),
        ("case_ingestion_request_failed", {"retrying": False}, "ERROR"),
        ("archive_scan_failed", {"recoverable": True}, "WARNING"),
        ("archive_scan_failed", {}, "ERROR"),
        ("v3_case_missing", {}, "ERROR"),
        ("case_ingestion_request_failed", {"retrying": True}, "WARNING"),
    ],
)
def test_operational_severity(output, event, fields, severity):
    @logs.logged_main
    def main():
        _log_event(event, fields)
        return 1

    main()
    assert any(
        f"{severity} CONFIG" in line and f"event={event}" in line
        for line in output.getvalue().splitlines()
    )


def test_shared_scanner_keeps_existing_output_without_cli_context(monkeypatch):
    messages = []
    logger = logging.getLogger("app.scripts.ingestion.archive_ingestor_core")
    monkeypatch.setattr(logger, "info", messages.append)
    _log_event("diagnostics_scanner_progress", {"count": 1})
    assert messages == ["event=diagnostics_scanner_progress count=1"]


def test_module_invocation_preserves_runner_identity(output, monkeypatch):
    monkeypatch.setenv("MAX_ATTEMPTS", "0")
    monkeypatch.delitem(sys.modules, "app.scripts.ingestion.nersc_archive_ingestor")
    with pytest.raises(SystemExit) as exc:
        runpy.run_module(
            "app.scripts.ingestion.nersc_archive_ingestor", run_name="__main__"
        )
    assert exc.value.code == 1
    assert (
        records(output)[0]["runner"] == "app.scripts.ingestion.nersc_archive_ingestor"
    )
