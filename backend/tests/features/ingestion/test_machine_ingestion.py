"""Exercise real Make dispatch without API calls or archive ingestion."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]


def run_make(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["make", *args], cwd=ROOT, env=env, capture_output=True, text=True, check=False
    )


@pytest.mark.parametrize("machine", ["chrysalis", "perlmutter"])
@pytest.mark.parametrize("mode", ["archive", "staging"])
@pytest.mark.parametrize(
    "target,dry", [("ingest-dry-run", "true"), ("ingest-apply", "false")]
)
@pytest.mark.parametrize("api_env", ["dev", "prod"])
def test_machine_dispatch(
    tmp_path: Path, machine: str, mode: str, target: str, dry: str, api_env: str
) -> None:
    root = tmp_path / "deployment with spaces"
    backend = root / "repository/simboard/backend"
    (backend / ".venv").mkdir(parents=True)
    operations = root / "operations"
    operations.mkdir()
    environment = operations / f"env.{api_env}.sh"
    environment.write_text(
        "export SIMBOARD_API_BASE_URL=https://example.test\n"
        "export SIMBOARD_API_TOKEN=hidden-token\n"
        f"export DRY_RUN={'false' if dry == 'true' else 'true'}\n"
        "export SCAN_MODE=invalid\n"
    )
    capture = tmp_path / "capture"
    python = tmp_path / "fake python"
    python.write_text(
        '#!/bin/bash\nprintf "%s\\n" "$*" "$DRY_RUN" "$SCAN_MODE" '
        '"$MACHINE_NAME" "$ARCHIVE_YEAR_START" "$ARCHIVE_YEAR_END" '
        '"$MAX_CASES_PER_RUN" "$SIMBOARD_INGESTION_LOG_LEVEL" '
        '"$PERF_ARCHIVE_ROOT" "$OLD_PERF_ARCHIVE_ROOT" > "$CAPTURE"\n'
        'exit "${FAKE_EXIT:-0}"\n'
    )
    python.chmod(0o755)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    flock = bin_dir / "flock"
    flock.write_text("#!/bin/sh\nexit 0\n")
    flock.chmod(0o755)
    env = {
        **os.environ,
        "PYTHON_BIN": str(python),
        "CAPTURE": str(capture),
        "PERF_ARCHIVE_ROOT": "/custom/staging",
        "OLD_PERF_ARCHIVE_ROOT": "/custom/archive",
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
    }
    result = run_make(
        [
            target,
            f"machine={machine}",
            f"env={api_env}",
            f"scan_mode={mode}",
            f"SIMBOARD_ROOT={root}",
            *([f"env_file={environment}"] if machine == "perlmutter" else []),
            "ARCHIVE_YEAR_START=2025-01",
            "ARCHIVE_YEAR_END=2025-03",
            "MAX_CASES_PER_RUN=5",
            "SIMBOARD_INGESTION_LOG_LEVEL=DEBUG",
        ],
        env,
    )
    assert result.returncode == 0, result.stderr
    module = (
        "hpc_upload_archive_ingestor"
        if machine == "chrysalis"
        else "nersc_archive_ingestor"
    )
    assert capture.read_text().splitlines() == [
        f"-m app.scripts.ingestion.{module}",
        dry,
        mode,
        machine,
        "2025-01",
        "2025-03",
        "5",
        "DEBUG",
        "/custom/staging",
        "/custom/archive",
    ]
    assert "hidden-token" not in result.stdout + result.stderr
    if machine == "chrysalis":
        assert list((operations / "raw_logs").glob("*.log"))
        assert (
            operations / f"simboard-ingestion-{mode}-chrysalis-env.{api_env}.sh.lock"
        ).exists()


@pytest.mark.parametrize(
    "args,message",
    [
        (["env=dev"], "machine must"),
        (["machine=nersc", "env=dev"], "machine must"),
        (["machine=perlmutter", "env=invalid"], "env must"),
        (["machine=perlmutter", "env=dev", "scan_mode=invalid"], "scan_mode must"),
        (
            ["machine=chrysalis", "env=dev", "scan_mode=archive", "SIMBOARD_ROOT="],
            "SIMBOARD_ROOT must",
        ),
        (
            [
                "machine=perlmutter",
                "env=dev",
                "scan_mode=archive",
                "env_file=/nonexistent",
            ],
            "not readable",
        ),
        (
            ["machine=perlmutter", "env=dev", "scan_mode=archive"],
            "SIMBOARD_API_BASE_URL must",
        ),
    ],
)
def test_invalid_machine_inputs(args: list[str], message: str) -> None:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("SIMBOARD_")
    }
    env["DRY_RUN_USE_REMOTE_STATE"] = "true"
    result = run_make(["ingest-dry-run", *args], env)
    assert result.returncode != 0
    assert message in result.stderr


@pytest.mark.parametrize("target", ["ingest-dry-run", "ingest-apply"])
@pytest.mark.parametrize("machine", ["chrysalis", "perlmutter"])
@pytest.mark.parametrize("mode_args", [[], ["scan_mode="], ["scan_mode=invalid"]])
def test_scan_mode_required(target: str, machine: str, mode_args: list[str]) -> None:
    env = os.environ.copy()
    env.pop("scan_mode", None)
    env["SCAN_MODE"] = "archive"
    result = run_make([target, f"machine={machine}", "env=dev", *mode_args], env)
    assert result.returncode != 0
    assert "scan_mode must be archive or staging (required)" in result.stderr


def test_perlmutter_offline_defaults_and_exit_status(tmp_path: Path) -> None:
    python = tmp_path / "python"
    python.write_text(
        '#!/bin/bash\nprintf "%s\\n" "$MACHINE_NAME" "$PERF_ARCHIVE_ROOT" '
        '"$OLD_PERF_ARCHIVE_ROOT" "${ARCHIVE_YEAR_START:-unbounded}"\nexit 7\n'
    )
    python.chmod(0o755)
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("SIMBOARD_")
    }
    for key in ("PERF_ARCHIVE_ROOT", "OLD_PERF_ARCHIVE_ROOT", "ARCHIVE_YEAR_START"):
        env.pop(key, None)
    env.update(PYTHON_BIN=str(python), DRY_RUN_USE_REMOTE_STATE=" false ")
    result = run_make(
        ["ingest-dry-run", "machine=perlmutter", "env=dev", "scan_mode=archive"], env
    )
    assert result.returncode != 0
    assert (
        "perlmutter\n/global/cfs/cdirs/e3sm/performance_archive\n"
        "/global/cfs/cdirs/e3sm/OLD_PERF\nunbounded"
    ) in result.stdout
    assert "Error 7" in result.stderr


def test_malformed_environment_does_not_leak_token(tmp_path: Path) -> None:
    environment = tmp_path / "broken.env"
    environment.write_text("SIMBOARD_API_TOKEN= hidden-token\n")
    result = run_make(
        [
            "ingest-dry-run",
            "machine=perlmutter",
            "env=dev",
            "scan_mode=archive",
            f"env_file={environment}",
        ],
        os.environ.copy(),
    )
    assert result.returncode != 0
    assert "Failed to load API environment file" in result.stderr
    assert "hidden-token" not in result.stderr + result.stdout
