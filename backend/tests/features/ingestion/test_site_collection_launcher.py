"""Tests for the config-driven host-side site collection launcher."""

import os
import shlex
import subprocess
from pathlib import Path


def _launcher_path() -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / "app/scripts/ingestion/sites/site_ingestion_launcher.sh"
    )


def _write_executable(path: Path, contents: str) -> Path:
    path.write_text(contents, encoding="utf-8")
    path.chmod(0o755)
    return path


def test_launcher_runs_configured_ingestor_offline(tmp_path: Path) -> None:
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    capture_path = tmp_path / "environment.txt"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_python = _write_executable(
        bin_dir / "python",
        "#!/usr/bin/env bash\n"
        'printf "%s\\n" "${SCAN_MODE}" "${ARCHIVE_YEAR_START-unset}" '
        '"${MACHINE_NAME}" "$*" > "${CAPTURE_PATH}"\n',
    )
    _write_executable(bin_dir / "flock", "#!/usr/bin/env bash\nexit 0\n")
    backend_dir = Path(__file__).resolve().parents[3]
    site_config = tmp_path / "test.config"
    site_config.write_text(
        "\n".join(
            [
                f"export SIMBOARD_REPODIR={shlex.quote(str(backend_dir))}",
                f"export SIMBOARD_WORKDIR={shlex.quote(str(work_dir))}",
                "export SIMBOARD_INGESTOR_MODULE=app.scripts.ingestion.nersc_archive_ingestor",
                "export SIMBOARD_DEFAULT_ARCHIVE_YEAR_START=2024-01",
                "export MACHINE_NAME=test-machine",
                "export DRY_RUN=true",
                "export DRY_RUN_USE_REMOTE_STATE=false",
                f"export PYTHON_BIN={shlex.quote(str(fake_python))}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.pop("SIMBOARD_API_BASE_URL", None)
    env.pop("SIMBOARD_API_TOKEN", None)
    env["CAPTURE_PATH"] = str(capture_path)
    env["SIMBOARD_SITE_CONFIG"] = str(site_config)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"

    result = subprocess.run(
        [_launcher_path(), "test", "archive"],
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert capture_path.read_text(encoding="utf-8").splitlines() == [
        "archive",
        "2024-01",
        "test-machine",
        "-m app.scripts.ingestion.nersc_archive_ingestor",
    ]


def test_launcher_loads_credentials_for_default_remote_state_dry_run(
    tmp_path: Path,
) -> None:
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_python = _write_executable(bin_dir / "python", "#!/usr/bin/env bash\nexit 0\n")
    _write_executable(bin_dir / "flock", "#!/usr/bin/env bash\nexit 0\n")
    environment_file = tmp_path / "environment.sh"
    environment_file.write_text(
        "export SIMBOARD_API_BASE_URL=https://example.test\n", encoding="utf-8"
    )
    token_file = tmp_path / "token.sh"
    token_file.write_text("export SIMBOARD_API_TOKEN=test-token\n", encoding="utf-8")
    backend_dir = Path(__file__).resolve().parents[3]
    site_config = tmp_path / "test.config"
    site_config.write_text(
        "\n".join(
            [
                f"export SIMBOARD_REPODIR={shlex.quote(str(backend_dir))}",
                f"export SIMBOARD_WORKDIR={shlex.quote(str(work_dir))}",
                "export SIMBOARD_INGESTOR_MODULE=app.scripts.ingestion.nersc_archive_ingestor",
                "export SIMBOARD_DEFAULT_ARCHIVE_YEAR_START=2024-01",
                f"export SIMBOARD_ENV_FILE={shlex.quote(str(environment_file))}",
                f"export SIMBOARD_API_TOKEN_FILE={shlex.quote(str(token_file))}",
                "export DRY_RUN=true",
                f"export PYTHON_BIN={shlex.quote(str(fake_python))}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.pop("SIMBOARD_API_BASE_URL", None)
    env.pop("SIMBOARD_API_TOKEN", None)
    env["SIMBOARD_SITE_CONFIG"] = str(site_config)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"

    result = subprocess.run(
        [_launcher_path(), "test", "archive"],
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_site_configs_define_their_ingestors() -> None:
    sites_dir = _launcher_path().parent

    for config_name, expected_module, expected_machine in (
        (
            "nersc.config",
            "app.scripts.ingestion.nersc_archive_ingestor",
            "perlmutter",
        ),
        (
            "chrysalis.config",
            "app.scripts.ingestion.hpc_upload_archive_ingestor",
            "chrysalis",
        ),
    ):
        result = subprocess.run(
            [
                "bash",
                "-c",
                'source "$1"; printf "%s\\n%s\\n" "$SIMBOARD_INGESTOR_MODULE" "$MACHINE_NAME"',
                "bash",
                str(sites_dir / config_name),
            ],
            capture_output=True,
            check=False,
            text=True,
        )

        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines() == [expected_module, expected_machine]
