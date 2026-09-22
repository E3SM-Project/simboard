"""Tests for the config-driven host-side site collection launcher."""

import os
import shlex
import subprocess
from pathlib import Path

import pytest


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
    flock_capture_path = tmp_path / "flock-commands.txt"
    _write_executable(
        bin_dir / "flock",
        '#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "${FLOCK_CAPTURE_PATH}"\nexit 0\n',
    )
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
    env.pop("SIMBOARD_ROOT", None)
    env["CAPTURE_PATH"] = str(capture_path)
    env["FLOCK_CAPTURE_PATH"] = str(flock_capture_path)
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
    lock_file = work_dir / "simboard-ingestion-archive-test-offline.lock"
    assert lock_file.exists()
    assert lock_file.stat().st_mode & 0o777 == 0o640
    raw_logs = list(
        (work_dir / "raw_logs").glob("simboard-ingestion-archive-test-offline-*.log")
    )
    assert len(raw_logs) == 1
    assert raw_logs[0].stat().st_mode & 0o777 == 0o640
    raw_log_contents = raw_logs[0].read_text(encoding="utf-8")
    assert f"site_config={site_config}" in raw_log_contents
    assert "scan_mode=archive" in raw_log_contents
    assert "dry_run=true" in raw_log_contents
    assert "dry_run_use_remote_state=false" in raw_log_contents
    assert "ingestor_module=app.scripts.ingestion.nersc_archive_ingestor" in (
        raw_log_contents
    )
    assert "invoking ingestor: module=app.scripts.ingestion.nersc_archive_ingestor" in (
        raw_log_contents
    )
    assert flock_capture_path.read_text(encoding="utf-8").splitlines() == ["-n 200"]


@pytest.mark.parametrize(
    ("scan_mode", "expected_returncode"),
    [("staging", 0), ("archive", 1)],
)
def test_launcher_reports_mode_specific_lock_contention(
    tmp_path: Path, scan_mode: str, expected_returncode: int
) -> None:
    simboard_root = tmp_path / "simboard-root"
    work_dir = simboard_root / "operations"
    work_dir.mkdir(parents=True)
    modules_dir = simboard_root / "repository/simboard/backend"
    modules_dir.parent.mkdir(parents=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_python = _write_executable(
        bin_dir / "python", "#!/usr/bin/env bash\nexit 99\n"
    )
    flock_capture_path = tmp_path / "flock-commands.txt"
    _write_executable(
        bin_dir / "flock",
        "#!/usr/bin/env bash\n"
        'printf "%s\\n" "$*" >> "${FLOCK_CAPTURE_PATH}"\n'
        '[[ "$*" == "-n 200" ]] && exit 1\n'
        "exit 0\n",
    )
    backend_dir = Path(__file__).resolve().parents[3]
    modules_dir.symlink_to(backend_dir, target_is_directory=True)
    site_config = tmp_path / "test.config"
    site_config.write_text(
        "\n".join(
            [
                "export SIMBOARD_INGESTOR_MODULE=app.scripts.ingestion.nersc_archive_ingestor",
                "export SIMBOARD_DEFAULT_ARCHIVE_YEAR_START=2024-01",
                "export DRY_RUN=true",
                "export DRY_RUN_USE_REMOTE_STATE=false",
                f"export PYTHON_BIN={shlex.quote(str(fake_python))}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["FLOCK_CAPTURE_PATH"] = str(flock_capture_path)
    env["SIMBOARD_ROOT"] = str(simboard_root)
    env["SIMBOARD_SITE_CONFIG"] = str(site_config)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"

    result = subprocess.run(
        [_launcher_path(), "test", scan_mode],
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )

    assert result.returncode == expected_returncode
    assert flock_capture_path.read_text(encoding="utf-8").splitlines() == ["-n 200"]
    raw_logs = list(
        (work_dir / "raw_logs").glob(
            f"simboard-ingestion-{scan_mode}-test-offline-*.log"
        )
    )
    assert len(raw_logs) == 1
    assert "lock already held; ingestion was not started" in raw_logs[0].read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize(
    ("scan_mode", "legacy_lock_contended", "expected_returncode"),
    [
        ("archive", False, 0),
        ("staging", True, 0),
        ("archive", True, 1),
    ],
)
def test_launcher_holds_existing_legacy_lock_during_migration(
    tmp_path: Path,
    scan_mode: str,
    legacy_lock_contended: bool,
    expected_returncode: int,
) -> None:
    simboard_root = tmp_path / "simboard-root"
    work_dir = simboard_root / "operations"
    work_dir.mkdir(parents=True)
    (work_dir / "SBCS-test-offline.lock").touch()
    modules_dir = simboard_root / "repository/simboard/backend"
    modules_dir.parent.mkdir(parents=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    flock_capture_path = tmp_path / "flock-commands.txt"
    fake_python = _write_executable(bin_dir / "python", "#!/usr/bin/env bash\nexit 0\n")
    _write_executable(
        bin_dir / "flock",
        "#!/usr/bin/env bash\n"
        'printf "%s\\n" "$*" >> "${FLOCK_CAPTURE_PATH}"\n'
        '[[ "${FLOCK_FAIL_FD:-}" == "201" && "$*" == "-n 201" ]] && exit 1\n'
        "exit 0\n",
    )
    backend_dir = Path(__file__).resolve().parents[3]
    modules_dir.symlink_to(backend_dir, target_is_directory=True)
    site_config = tmp_path / "test.config"
    site_config.write_text(
        "\n".join(
            [
                "export SIMBOARD_INGESTOR_MODULE=app.scripts.ingestion.nersc_archive_ingestor",
                "export SIMBOARD_DEFAULT_ARCHIVE_YEAR_START=2024-01",
                "export DRY_RUN=true",
                "export DRY_RUN_USE_REMOTE_STATE=false",
                f"export PYTHON_BIN={shlex.quote(str(fake_python))}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["FLOCK_CAPTURE_PATH"] = str(flock_capture_path)
    env["SIMBOARD_ROOT"] = str(simboard_root)
    env["SIMBOARD_SITE_CONFIG"] = str(site_config)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    if legacy_lock_contended:
        env["FLOCK_FAIL_FD"] = "201"

    result = subprocess.run(
        [_launcher_path(), "test", scan_mode],
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )

    assert result.returncode == expected_returncode, result.stderr
    assert flock_capture_path.read_text(encoding="utf-8").splitlines() == [
        "-n 200",
        "-n 201",
    ]


def test_launcher_requires_scheduler_root(tmp_path: Path) -> None:
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
    assert "SIMBOARD_ROOT must be set by the scheduler environment" in result.stderr


def test_launcher_loads_credentials_for_default_remote_state_dry_run(
    tmp_path: Path,
) -> None:
    simboard_root = tmp_path / "simboard-root"
    work_dir = simboard_root / "operations"
    work_dir.mkdir(parents=True)
    modules_dir = simboard_root / "repository/simboard/backend"
    modules_dir.parent.mkdir(parents=True)
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
    modules_dir.symlink_to(backend_dir, target_is_directory=True)
    site_config = tmp_path / "test.config"
    site_config.write_text(
        "\n".join(
            [
                "export SIMBOARD_INGESTOR_MODULE=app.scripts.ingestion.nersc_archive_ingestor",
                "export SIMBOARD_DEFAULT_ARCHIVE_YEAR_START=2024-01",
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
    env["SIMBOARD_ROOT"] = str(simboard_root)
    env["SIMBOARD_ENV_FILE"] = str(environment_file)
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
    raw_logs = list(
        (work_dir / "raw_logs").glob(
            "simboard-ingestion-archive-test-environment.sh-*.log"
        )
    )
    assert len(raw_logs) == 1

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
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; printf "%s\\n%s\\n" "$SIMBOARD_INGESTOR_MODULE" "$MACHINE_NAME"',
            "bash",
            str(sites_dir / "configs/chrysalis.config"),
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
    ]


def test_ingestion_initializers_create_non_overwritable_site_files(
    tmp_path: Path,
) -> None:
    repository_root = Path(__file__).resolve().parents[4]
    missing_root = tmp_path / "missing"
    result = subprocess.run(
        [
            "make",
            "operations-init-env",
            "site=chrysalis",
            f"SIMBOARD_ROOT={missing_root}",
        ],
        capture_output=True,
        check=False,
        cwd=repository_root,
        text=True,
    )

    assert result.returncode != 0
    assert "Destination directory does not exist" in result.stderr

    simboard_root = tmp_path / "simboard"
    destination_dir = simboard_root / "operations"
    destination_dir.mkdir(parents=True)
    development_file = destination_dir / "env.dev.sh"
    production_file = destination_dir / "env.prod.sh"

    result = subprocess.run(
        [
            "make",
            "operations-init-env",
            "site=chrysalis",
            f"SIMBOARD_ROOT={simboard_root}",
        ],
        capture_output=True,
        check=False,
        cwd=repository_root,
        input="\n\n\n\n",
        text=True,
    )

    assert result.returncode != 0
    assert (
        "dev SIMBOARD_API_BASE_URL and SIMBOARD_API_TOKEN must be set" in result.stderr
    )
    assert not development_file.exists()
    assert not production_file.exists()

    result = subprocess.run(
        [
            "make",
            "operations-init-env",
            "site=chrysalis",
            f"SIMBOARD_ROOT={simboard_root}",
        ],
        capture_output=True,
        check=False,
        cwd=repository_root,
        input=(
            "https://dev-api.example.test\ntest-dev-token\n"
            "https://prod-api.example.test\ntest-prod-token\n"
        ),
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert development_file.read_text(encoding="utf-8") == (
        "#!/usr/bin/env bash\n"
        "# Development SimBoard API configuration. Keep this file outside the repository.\n"
        "export SIMBOARD_API_BASE_URL=https://dev-api.example.test\n"
        "export SIMBOARD_API_TOKEN=test-dev-token\n"
    )
    assert "test-dev-token" not in result.stdout
    assert "test-dev-token" not in result.stderr
    assert development_file.stat().st_mode & 0o777 == 0o640
    assert production_file.read_text(encoding="utf-8") == (
        "#!/usr/bin/env bash\n"
        "# Production SimBoard API configuration. Keep this file outside the repository.\n"
        "export SIMBOARD_API_BASE_URL=https://prod-api.example.test\n"
        "export SIMBOARD_API_TOKEN=test-prod-token\n"
    )
    assert production_file.stat().st_mode & 0o777 == 0o640

    crontab_file = destination_dir / "chrysalis.crontab"
    result = subprocess.run(
        [
            "make",
            "operations-init-cron",
            "site=chrysalis",
            f"SIMBOARD_ROOT={simboard_root}",
        ],
        capture_output=True,
        check=False,
        cwd=repository_root,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert crontab_file.read_text(encoding="utf-8") == (
        repository_root
        / "backend/app/scripts/ingestion/sites/templates/crontab.example"
    ).read_text(encoding="utf-8")
    assert crontab_file.stat().st_mode & 0o777 == 0o640

    result = subprocess.run(
        [
            "make",
            "operations-init-env",
            "site=chrysalis",
            f"SIMBOARD_ROOT={simboard_root}",
        ],
        capture_output=True,
        check=False,
        cwd=repository_root,
        text=True,
    )

    assert result.returncode != 0
    assert "refusing to overwrite either file" in result.stderr

    result = subprocess.run(
        [
            "make",
            "operations-init-cron",
            "site=chrysalis",
            f"SIMBOARD_ROOT={simboard_root}",
        ],
        capture_output=True,
        check=False,
        cwd=repository_root,
        text=True,
    )

    assert result.returncode != 0
    assert "refusing to overwrite it" in result.stderr


def test_operations_provisioning_creates_and_preserves_operations_directory(
    tmp_path: Path,
) -> None:
    repository_root = Path(__file__).resolve().parents[4]
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    git_capture_path = tmp_path / "git-commands.txt"
    _write_executable(
        bin_dir / "git",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'printf "%s\\n" "$*" >> "${GIT_CAPTURE_PATH}"\n'
        'if [[ "$1" == "clone" ]]; then\n'
        '  mkdir -p "${!#}/.git"\n'
        '  printf \'backend-install:\\n\\t@touch "$$BACKEND_INSTALL_CAPTURE_PATH"\\n\' > "${!#}/Makefile"\n'
        "fi\n"
        'if [[ "$*" == *"status --porcelain" ]] && [[ -n "${GIT_STATUS_OUTPUT:-}" ]]; then\n'
        '  printf "%s\\n" "${GIT_STATUS_OUTPUT}"\n'
        "fi\n",
    )
    _write_executable(
        bin_dir / "flock",
        "#!/usr/bin/env bash\n"
        'if [[ -n "${FLOCK_CAPTURE_PATH:-}" ]]; then\n'
        '  printf "%s\\n" "$*" >> "${FLOCK_CAPTURE_PATH}"\n'
        "fi\n"
        "exit 0\n",
    )
    _write_executable(
        bin_dir / "getent",
        "#!/usr/bin/env bash\n"
        '[[ "$*" == "group simboard" && "${SIMBOARD_GROUP_EXISTS:-false}" == "true" ]]\n',
    )
    chgrp_capture_path = tmp_path / "chgrp-commands.txt"
    _write_executable(
        bin_dir / "chgrp",
        "#!/usr/bin/env bash\n"
        'if [[ "${CHGRP_FAIL:-false}" == "true" ]]; then\n'
        "  exit 1\n"
        "fi\n"
        'printf "%s\\n" "$*" >> "${CHGRP_CAPTURE_PATH}"\n',
    )
    chmod_capture_path = tmp_path / "chmod-commands.txt"
    _write_executable(
        bin_dir / "chmod",
        '#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "${CHMOD_CAPTURE_PATH}"\n',
    )
    env = os.environ.copy()
    backend_install_capture_path = tmp_path / "backend-install.txt"
    env["BACKEND_INSTALL_CAPTURE_PATH"] = str(backend_install_capture_path)
    env["CHGRP_CAPTURE_PATH"] = str(chgrp_capture_path)
    env["CHMOD_CAPTURE_PATH"] = str(chmod_capture_path)
    env["GIT_CAPTURE_PATH"] = str(git_capture_path)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["SIMBOARD_GROUP_EXISTS"] = "true"
    invalid_root = tmp_path / "invalid-root"
    invalid_root.write_text("not a directory", encoding="utf-8")

    result = subprocess.run(
        [
            "make",
            "operations-provision",
            f"SIMBOARD_ROOT={invalid_root}",
        ],
        capture_output=True,
        check=False,
        cwd=repository_root,
        env=env,
        text=True,
    )

    assert result.returncode != 0
    assert "SIMBOARD_ROOT exists but is not a directory" in result.stderr

    simboard_root = tmp_path / "simboard"
    operations_dir = simboard_root / "operations"
    env["SIMBOARD_ROOT"] = str(simboard_root)
    result = subprocess.run(
        [
            "make",
            "operations-provision",
        ],
        capture_output=True,
        check=False,
        cwd=repository_root,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Created SimBoard deployment root" in result.stdout
    assert "Created operations directory" in result.stdout
    assert "Cloned SimBoard checkout" in result.stdout
    assert "Installed SimBoard backend runtime" in result.stdout
    assert operations_dir.is_dir()
    assert operations_dir.stat().st_mode & 0o777 == 0o750
    assert (operations_dir / "raw_logs").stat().st_mode & 0o777 == 0o750
    assert (operations_dir / "quality_assurance").stat().st_mode & 0o777 == 0o750
    assert "Configured simboard group access for operations artifacts" in result.stdout
    assert chgrp_capture_path.read_text(encoding="utf-8").splitlines() == [
        f"simboard {operations_dir}",
        f"simboard {operations_dir / 'raw_logs'}",
        f"simboard {operations_dir / 'quality_assurance'}",
    ]
    assert chmod_capture_path.read_text(encoding="utf-8").splitlines() == [
        f"2750 {operations_dir}",
        f"2750 {operations_dir / 'raw_logs'}",
        f"2750 {operations_dir / 'quality_assurance'}",
    ]
    env["CHGRP_FAIL"] = "true"
    result = subprocess.run(
        ["make", "operations-provision"],
        capture_output=True,
        check=False,
        cwd=repository_root,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "WARNING: Unable to set simboard group ownership" in result.stderr
    env.pop("CHGRP_FAIL")
    assert not (operations_dir / "summarized_logs").exists()
    assert simboard_root.stat().st_mode & 0o777 == 0o750
    checkout_dir = simboard_root / "repository/simboard"
    assert (checkout_dir / ".git").is_dir()
    assert backend_install_capture_path.exists()
    assert git_capture_path.read_text(encoding="utf-8").splitlines()[0] == (
        "clone --branch main --single-branch --depth 1 "
        f"https://github.com/E3SM-Project/simboard.git {checkout_dir}"
    )

    operations_dir.chmod(0o700)
    result = subprocess.run(
        [
            "make",
            "operations-provision",
            f"SIMBOARD_ROOT={simboard_root}",
        ],
        capture_output=True,
        check=False,
        cwd=repository_root,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Verified existing operations directory" in result.stdout
    assert "Updated SimBoard checkout" in result.stdout
    assert operations_dir.stat().st_mode & 0o777 == 0o700
    assert git_capture_path.read_text(encoding="utf-8").splitlines()[-3:] == [
        f"-C {checkout_dir} status --porcelain",
        f"-C {checkout_dir} fetch --depth 1 origin main",
        f"-C {checkout_dir} checkout --detach --force FETCH_HEAD",
    ]

    env["GIT_STATUS_OUTPUT"] = " M deployment-change"
    result = subprocess.run(
        [
            "make",
            "operations-provision",
            f"SIMBOARD_ROOT={simboard_root}",
        ],
        capture_output=True,
        check=False,
        cwd=repository_root,
        env=env,
        text=True,
    )

    assert result.returncode != 0
    assert "SimBoard checkout has uncommitted changes" in result.stderr
    assert git_capture_path.read_text(encoding="utf-8").splitlines()[-1] == (
        f"-C {checkout_dir} status --porcelain"
    )
    env.pop("GIT_STATUS_OUTPUT")

    collision_root = tmp_path / "collision"
    collision_root.mkdir()
    (collision_root / "operations").write_text("not a directory", encoding="utf-8")
    result = subprocess.run(
        [
            "make",
            "operations-provision",
            f"SIMBOARD_ROOT={collision_root}",
        ],
        capture_output=True,
        check=False,
        cwd=repository_root,
        env=env,
        text=True,
    )

    assert result.returncode != 0
    assert "Operations path exists but is not a directory" in result.stderr

    checkout_collision_root = tmp_path / "checkout-collision"
    (checkout_collision_root / "repository").mkdir(parents=True)
    (checkout_collision_root / "repository/simboard").write_text(
        "not a Git checkout", encoding="utf-8"
    )
    result = subprocess.run(
        [
            "make",
            "operations-provision",
            f"SIMBOARD_ROOT={checkout_collision_root}",
        ],
        capture_output=True,
        check=False,
        cwd=repository_root,
        env=env,
        text=True,
    )

    assert result.returncode != 0
    assert "SimBoard checkout is not a Git repository" in result.stderr


def test_operations_refresh_updates_only_changed_clean_checkout(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[4]
    simboard_root = tmp_path / "simboard"
    operations_dir = simboard_root / "operations"
    operations_dir.mkdir(parents=True)
    checkout_dir = simboard_root / "repository/simboard"
    (checkout_dir / ".git").mkdir(parents=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    backend_install_capture_path = tmp_path / "backend-install.txt"
    _write_executable(
        bin_dir / "git",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'if [[ "$*" == *"status --porcelain" ]]; then\n'
        '  printf "%s\\n" "${GIT_STATUS_OUTPUT:-}"\n'
        'elif [[ "$*" == *"rev-parse HEAD" ]]; then\n'
        '  printf "%s\\n" "${GIT_CURRENT_REVISION}"\n'
        'elif [[ "$*" == *"rev-parse FETCH_HEAD" ]]; then\n'
        '  printf "%s\\n" "${GIT_FETCHED_REVISION}"\n'
        "fi\n",
    )
    _write_executable(
        bin_dir / "flock",
        "#!/usr/bin/env bash\n"
        'if [[ -n "${FLOCK_CAPTURE_PATH:-}" ]]; then\n'
        '  printf "%s\\n" "$*" >> "${FLOCK_CAPTURE_PATH}"\n'
        "fi\n"
        "exit 0\n",
    )
    (checkout_dir / "Makefile").write_text(
        'backend-install:\n\t@touch "$$BACKEND_INSTALL_CAPTURE_PATH"\n',
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["BACKEND_INSTALL_CAPTURE_PATH"] = str(backend_install_capture_path)
    env["GIT_CURRENT_REVISION"] = "current-revision"
    env["GIT_FETCHED_REVISION"] = "current-revision"
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["SIMBOARD_ROOT"] = str(simboard_root)

    result = subprocess.run(
        ["make", "operations-refresh"],
        capture_output=True,
        check=False,
        cwd=repository_root,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "already current" in result.stdout
    assert not backend_install_capture_path.exists()
    refresh_lock_file = operations_dir / "simboard-ingestion-provision.lock"
    assert refresh_lock_file.stat().st_mode & 0o777 == 0o640

    legacy_refresh_lock_file = operations_dir / "SBCS-provision.lock"
    legacy_refresh_lock_file.touch()
    flock_capture_path = tmp_path / "flock-commands.txt"
    env["FLOCK_CAPTURE_PATH"] = str(flock_capture_path)
    env["GIT_FETCHED_REVISION"] = "updated-revision"
    result = subprocess.run(
        ["make", "operations-refresh"],
        capture_output=True,
        check=False,
        cwd=repository_root,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Refreshed SimBoard checkout" in result.stdout
    assert backend_install_capture_path.exists()
    assert flock_capture_path.read_text(encoding="utf-8").splitlines() == [
        "-n 201",
        "-n 202",
    ]

    env["GIT_STATUS_OUTPUT"] = " M deployment-change"
    result = subprocess.run(
        ["make", "operations-refresh"],
        capture_output=True,
        check=False,
        cwd=repository_root,
        env=env,
        text=True,
    )

    assert result.returncode != 0
    assert "SimBoard checkout has uncommitted changes" in result.stderr

    empty_root = tmp_path / "empty"
    (empty_root / "operations").mkdir(parents=True)
    env["SIMBOARD_ROOT"] = str(empty_root)
    env.pop("GIT_STATUS_OUTPUT")
    result = subprocess.run(
        ["make", "operations-refresh"],
        capture_output=True,
        check=False,
        cwd=repository_root,
        env=env,
        text=True,
    )

    assert result.returncode != 0
    assert (
        "SimBoard checkout does not exist; run operations-provision first"
        in result.stderr
    )

    missing_root = tmp_path / "missing"
    env["SIMBOARD_ROOT"] = str(missing_root)
    result = subprocess.run(
        ["make", "operations-refresh"],
        capture_output=True,
        check=False,
        cwd=repository_root,
        env=env,
        text=True,
    )

    assert result.returncode != 0
    assert (
        "Operations directory does not exist; run operations-provision first"
        in result.stderr
    )


def test_operations_init_v3_env_creates_protected_environment(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[4]
    simboard_root = tmp_path / "simboard"
    operations_dir = simboard_root / "operations"
    operations_dir.mkdir(parents=True)

    result = subprocess.run(
        [
            "make",
            "operations-init-v3-env",
            f"SIMBOARD_ROOT={simboard_root}",
            "environment=prod",
        ],
        capture_output=True,
        check=False,
        cwd=repository_root,
        input="\nservice-token\n\n",
        text=True,
    )

    destination = operations_dir / "lcrc-v3.prod.env"
    assert result.returncode == 0, result.stderr
    assert destination.stat().st_mode & 0o777 == 0o640
    assert destination.read_text(encoding="utf-8") == (
        "# prod E3SM v3 Chrysalis backfill configuration. Keep outside the repository.\n"
        "SIMBOARD_API_BASE_URL=https://simboard-api.e3sm.org\n"
        "SIMBOARD_API_TOKEN=service-token\n"
        "V3_DIAGNOSTICS_SOURCE_ROOT=/lcrc/group/e3sm/public_html/diagnostic_output\n"
        "\n# Optional: override the default historical archive mount.\n"
        "# OLD_PERF_ARCHIVE_ROOT=/path/to/OLD_PERF\n"
    )

    result = subprocess.run(
        [
            "make",
            "operations-init-v3-env",
            f"SIMBOARD_ROOT={simboard_root}",
            "environment=prod",
        ],
        capture_output=True,
        check=False,
        cwd=repository_root,
        text=True,
    )

    assert result.returncode != 0
    assert "refusing to overwrite it" in result.stderr


def test_v3_commands_report_missing_derived_environment(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[4]
    simboard_root = tmp_path / "simboard"

    result = subprocess.run(
        [
            "make",
            "v3-diagnostics-dry-run",
            f"SIMBOARD_ROOT={simboard_root}",
            "environment=dev",
        ],
        capture_output=True,
        check=False,
        cwd=repository_root,
        text=True,
    )

    expected_path = simboard_root / "operations/lcrc-v3.dev.env"
    assert result.returncode != 0
    assert f"Missing v3 environment file: {expected_path}" in result.stderr
    assert (
        f"make operations-init-v3-env SIMBOARD_ROOT={simboard_root} environment=dev"
        in result.stderr
    )
