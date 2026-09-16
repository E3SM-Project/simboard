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
    simboard_root = tmp_path / "simboard-root"
    work_dir = simboard_root / "operations"
    work_dir.mkdir(parents=True)
    modules_dir = simboard_root / "repository/simboard/backend"
    modules_dir.parent.mkdir(parents=True)
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
    modules_dir.symlink_to(backend_dir, target_is_directory=True)
    site_config = tmp_path / "test.config"
    site_config.write_text(
        "\n".join(
            [
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
    env["SIMBOARD_ROOT"] = str(simboard_root)
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


def test_launcher_requires_root_or_explicit_paths(tmp_path: Path) -> None:
    site_config = tmp_path / "test.config"
    site_config.write_text(
        "\n".join(
            [
                "export SIMBOARD_INGESTOR_MODULE=app.scripts.ingestion.nersc_archive_ingestor",
                "export SIMBOARD_DEFAULT_ARCHIVE_YEAR_START=2024-01",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.pop("SIMBOARD_ROOT", None)
    env["SIMBOARD_SITE_CONFIG"] = str(site_config)

    result = subprocess.run(
        [_launcher_path(), "test", "archive"],
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )

    assert result.returncode == 1
    assert (
        "SIMBOARD_WORKDIR must be set by SIMBOARD_ROOT or a nonstandard deployment override"
        in result.stderr
    )


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
        "export SIMBOARD_API_BASE_URL=https://example.test\n"
        "export SIMBOARD_API_TOKEN=test-token\n",
        encoding="utf-8",
    )
    backend_dir = Path(__file__).resolve().parents[3]
    site_config = tmp_path / "test.config"
    site_config.write_text(
        "\n".join(
            [
                f"export SIMBOARD_MODULES={shlex.quote(str(backend_dir))}",
                f"export SIMBOARD_WORKDIR={shlex.quote(str(work_dir))}",
                "export SIMBOARD_INGESTOR_MODULE=app.scripts.ingestion.nersc_archive_ingestor",
                "export SIMBOARD_DEFAULT_ARCHIVE_YEAR_START=2024-01",
                f"export SIMBOARD_ENV_FILE={shlex.quote(str(environment_file))}",
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

    environment_file.write_text(
        "export SIMBOARD_API_BASE_URL=https://example.test\n", encoding="utf-8"
    )
    result = subprocess.run(
        [_launcher_path(), "test", "archive"],
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )

    assert result.returncode == 1
    assert "SIMBOARD_API_TOKEN failed to be set" in result.stderr


def test_site_configs_define_their_ingestors() -> None:
    sites_dir = _launcher_path().parent
    env = os.environ.copy()
    env.pop("SIMBOARD_ENV_FILE", None)

    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; printf "%s\\n%s\\n%s\\n%s\\n" "$SIMBOARD_INGESTOR_MODULE" "$MACHINE_NAME" "$DRY_RUN" "$SIMBOARD_ENV_FILE"',
            "bash",
            str(sites_dir / "chrysalis.config"),
        ],
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "app.scripts.ingestion.hpc_upload_archive_ingestor",
        "chrysalis",
        "true",
        "/lcrc/group/e3sm2/simboard/operations/environment.sh",
    ]


def test_chrysalis_config_preserves_environment_file_override() -> None:
    sites_dir = _launcher_path().parent
    override = "/tmp/simboard-production-environment.sh"
    env = os.environ.copy()
    env["SIMBOARD_ENV_FILE"] = override

    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; printf "%s\\n" "$SIMBOARD_ENV_FILE"',
            "bash",
            str(sites_dir / "chrysalis.config"),
        ],
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == f"{override}\n"


def test_chrysalis_environment_initializer_creates_non_overwritable_template(
    tmp_path: Path,
) -> None:
    repository_root = Path(__file__).resolve().parents[4]
    missing_file = tmp_path / "missing" / "environment.sh"
    result = subprocess.run(
        ["make", "chrysalis-init-environment", f"ENV_FILE={missing_file}"],
        capture_output=True,
        check=False,
        cwd=repository_root,
        text=True,
    )

    assert result.returncode != 0
    assert "Destination directory does not exist" in result.stderr

    destination_dir = tmp_path / "operations"
    destination_dir.mkdir()
    environment_file = destination_dir / "environment.sh"

    result = subprocess.run(
        ["make", "chrysalis-init-environment", f"ENV_FILE={environment_file}"],
        capture_output=True,
        check=False,
        cwd=repository_root,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert environment_file.read_text(encoding="utf-8") == (
        repository_root / "backend/app/scripts/ingestion/sites/environment.sh.example"
    ).read_text(encoding="utf-8")
    assert environment_file.stat().st_mode & 0o777 == 0o640

    result = subprocess.run(
        ["make", "chrysalis-init-environment", f"ENV_FILE={environment_file}"],
        capture_output=True,
        check=False,
        cwd=repository_root,
        text=True,
    )

    assert result.returncode != 0
    assert "refusing to overwrite it" in result.stderr
