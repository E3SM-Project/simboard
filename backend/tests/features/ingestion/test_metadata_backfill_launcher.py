"""Exercise config loading and argument forwarding without API requests."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]


@pytest.mark.parametrize("machine", ["perlmutter", "chrysalis"])
@pytest.mark.parametrize("api_env", ["dev", "prod"])
def test_make_loads_operations_environment_and_site_config(tmp_path, machine, api_env):
    root = tmp_path / "deployment with spaces"
    operations = root / "operations"
    operations.mkdir(parents=True)
    environment = operations / f"env.{api_env}.sh"
    environment.write_text(
        f"SIMBOARD_API_BASE_URL=https://{api_env}.example.test\n"
        "SIMBOARD_API_TOKEN=hidden-token\n"
        "printf '%s\\n' hidden-token\n"
        "MACHINE_NAME=wrong-machine\n"
        "PERF_ARCHIVE_ROOT=/configured/staging\n"
        "OLD_PERF_ARCHIVE_ROOT=/configured/archive\n"
    )
    python = _fake_python(tmp_path)
    result = _run_make(
        [
            f"machine={machine}",
            f"env={api_env}",
            f"SIMBOARD_ROOT={root}",
            "args=--fields source-directories --sources both --case-name 'case with spaces' --dry-run",
        ],
        python,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "-m",
        "app.scripts.ingestion.backfill.metadata",
        "--machine",
        machine,
        "--fields",
        "source-directories",
        "--sources",
        "both",
        "--case-name",
        "case with spaces",
        "--dry-run",
        machine,
        f"https://{api_env}.example.test",
        "/configured/staging",
        "/configured/archive",
        "2025-01",
    ]
    assert "hidden-token" not in result.stdout + result.stderr


def test_explicit_environment_file_needs_no_root_and_preserves_exit_status(tmp_path):
    environment = tmp_path / "alternate env.sh"
    environment.write_text(
        "SIMBOARD_API_BASE_URL=https://override.example.test\nSIMBOARD_API_TOKEN=hidden-token\n"
    )
    python = _fake_python(tmp_path, exit_code=7)
    result = _run_make(
        [
            "machine=perlmutter",
            "env=dev",
            f"env_file={environment}",
            "SIMBOARD_ROOT=/missing",
            "args=--fields simulation-dates --dry-run",
        ],
        python,
    )

    assert result.returncode != 0
    assert "https://override.example.test" in result.stdout
    assert "Error 7" in result.stderr
    assert "hidden-token" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "arguments,message",
    [
        (["env=dev"], "machine must"),
        (["machine=invalid", "env=dev"], "machine must"),
        (["machine=perlmutter", "env=invalid"], "env must"),
        (["machine=perlmutter", "env=dev"], "SIMBOARD_ROOT must"),
        (
            ["machine=perlmutter", "env=dev", "env_file=/missing"],
            "missing or unreadable",
        ),
        (
            ["machine=perlmutter", "env=dev", "args=--machine chrysalis"],
            "instead of --machine",
        ),
    ],
)
def test_launcher_rejects_invalid_configuration_before_python(
    tmp_path, arguments, message
):
    result = _run_make(arguments, _fake_python(tmp_path))

    assert result.returncode != 0
    assert message in result.stderr
    assert "app.scripts.ingestion.backfill.metadata" not in result.stdout


@pytest.mark.parametrize(
    "failure", ["false", 'printf "%s" "$UNSET_BACKFILL_VARIABLE"', "exit 0"]
)
def test_environment_loading_failure_does_not_expose_credentials(tmp_path, failure):
    environment = tmp_path / "broken.sh"
    environment.write_text(
        "SIMBOARD_API_TOKEN=hidden-token\nset -x\nprintf '%s' hidden-token\n"
        "unset UNSET_BACKFILL_VARIABLE\n" + failure + "\n"
    )
    result = _run_make(
        ["machine=perlmutter", "env=dev", f"env_file={environment}"],
        _fake_python(tmp_path),
    )

    assert result.returncode != 0
    assert "Failed to load API environment file" in result.stderr
    assert "hidden-token" not in result.stdout + result.stderr


def test_empty_environment_cannot_reuse_exported_credentials(tmp_path):
    environment = tmp_path / "empty.sh"
    environment.write_text("")
    result = _run_make(
        ["machine=perlmutter", "env=dev", f"env_file={environment}"],
        _fake_python(tmp_path),
    )

    assert result.returncode != 0
    assert "SIMBOARD_API_BASE_URL must be set" in result.stderr


def test_exported_source_settings_override_site_defaults(tmp_path):
    environment = tmp_path / "env.sh"
    environment.write_text(
        "SIMBOARD_API_BASE_URL=https://example.test\nSIMBOARD_API_TOKEN=hidden-token\n"
    )
    result = _run_make(
        [
            "machine=perlmutter",
            "env=dev",
            f"env_file={environment}",
            "args=--fields source-directories --dry-run",
        ],
        _fake_python(tmp_path),
        {
            "PERF_ARCHIVE_ROOT": "/exported/staging",
            "OLD_PERF_ARCHIVE_ROOT": "/exported/archive",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "/exported/staging" in result.stdout
    assert "/exported/archive" in result.stdout


def _run_make(arguments, python, overrides=None):
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("SIMBOARD_")
        and key
        not in (
            "PERF_ARCHIVE_ROOT",
            "OLD_PERF_ARCHIVE_ROOT",
            "MACHINE_NAME",
            "ARCHIVE_YEAR_START",
            "ARCHIVE_YEAR_END",
            "SIMBOARD_ROOT",
            "env_file",
            "machine",
            "env",
            "args",
        )
    }
    environment.update(
        PYTHON_BIN=str(python),
        SIMBOARD_API_BASE_URL="https://stale.example.test",
        SIMBOARD_API_TOKEN="stale-token",
    )
    environment.update(overrides or {})

    return subprocess.run(
        ["make", "metadata-backfill", *arguments],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def _fake_python(tmp_path, exit_code=0):
    python = tmp_path / "fake python"
    python.write_text(
        '#!/bin/bash\nprintf "%s\\n" "$@" "$MACHINE_NAME" '
        '"$SIMBOARD_API_BASE_URL" "$PERF_ARCHIVE_ROOT" "$OLD_PERF_ARCHIVE_ROOT" '
        '"$SIMBOARD_DEFAULT_ARCHIVE_YEAR_START"\n'
        f"exit {exit_code}\n"
    )
    python.chmod(0o755)

    return python
