"""Exercise operator Make targets through the host launcher without real scans."""

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture
def diagnostics_workspace(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    # Include spaces to exercise quoting of deployment and interpreter paths.
    root = tmp_path / "simboard root"
    operations = root / "operations"
    operations.mkdir(parents=True)
    backend = root / "repository/simboard/backend"
    backend.mkdir(parents=True)
    (backend / ".venv").mkdir()
    python = backend / "fake python"
    python.write_text(
        "#!/usr/bin/env bash\n"
        'printf "%s\\n" "$DRY_RUN" "$MACHINE_NAME" "$SIMBOARD_ENV_FILE" '
        '"${SIMBOARD_API_BASE_URL-unset}" "$*" > "$CAPTURE_PATH"\n'
        'exit "${SCANNER_EXIT_CODE:-0}"\n',
        encoding="utf-8",
    )
    python.chmod(0o755)
    capture = tmp_path / "capture.txt"
    process_env = os.environ.copy()
    for key in (
        "SIMBOARD_ROOT",
        "SIMBOARD_SITE_CONFIG",
        "SIMBOARD_ENV_FILE",
        "SIMBOARD_API_BASE_URL",
        "SIMBOARD_API_TOKEN",
        "MACHINE_NAME",
        "MAKEFLAGS",
        "MFLAGS",
        "MAKEOVERRIDES",
    ):
        process_env.pop(key, None)
    process_env.update(PYTHON_BIN=str(python), CAPTURE_PATH=str(capture))
    return root, capture, process_env


def _make(target: str, args: list[str], process_env: dict[str, str]):
    return subprocess.run(
        ["make", "--no-print-directory", target, *args],
        cwd=REPO_ROOT,
        env=process_env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("api_env", ["dev", "prod"])
@pytest.mark.parametrize(
    ("target", "dry_run"),
    [("diagnostics-dry-run", "true"), ("diagnostics-apply", "false")],
)
def test_targets_select_mode_environment_and_launcher_logs(
    diagnostics_workspace, target: str, dry_run: str, api_env: str
) -> None:
    root, capture, process_env = diagnostics_workspace
    # The explicit target mode must win over inherited or command-line DRY_RUN.
    opposite_mode = "false" if dry_run == "true" else "true"
    process_env["DRY_RUN"] = opposite_mode
    conflicting_config = root / "unexpected.config"
    conflicting_config.write_text('echo "must not load another site" >&2\nexit 99\n')
    process_env["SIMBOARD_SITE_CONFIG"] = str(conflicting_config)
    env_file = root / f"operations/env.{api_env}.sh"
    if dry_run == "true":
        env_file.write_text('echo "must not load dry-run credentials" >&2\nexit 99\n')
    else:
        env_file.write_text(
            f"export SIMBOARD_API_BASE_URL=https://{api_env}.example.org\n"
            "export SIMBOARD_API_TOKEN=test-token\n"
        )
    result = _make(
        target,
        [
            f"SIMBOARD_ROOT={root}",
            "site=chrysalis",
            f"env={api_env}",
            f"DRY_RUN={opposite_mode}",
        ],
        process_env,
    )
    assert result.returncode == 0, result.stderr
    assert capture.read_text().splitlines() == [
        dry_run,
        "chrysalis",
        str(env_file),
        "unset" if dry_run == "true" else f"https://{api_env}.example.org",
        "-m app.scripts.ingestion.diagnostics_link_scanner",
    ]
    logs = list((root / "operations/raw_logs").glob("simboard-diagnostics-*.log"))
    assert len(logs) == 1
    assert f"chrysalis-env.{api_env}.sh-" in logs[0].name
    assert "event=launcher_finished exit_code=0" in logs[0].read_text()
    assert (
        root / f"operations/simboard-diagnostics-chrysalis-env.{api_env}.sh.lock"
    ).exists()
    assert "test-token" not in result.stdout + result.stderr + logs[0].read_text()


@pytest.mark.parametrize("target", ["diagnostics-dry-run", "diagnostics-apply"])
@pytest.mark.parametrize(
    ("missing", "site", "api_env", "message"),
    [
        ("root", "chrysalis", "prod", "Usage:"),
        ("site", "chrysalis", "prod", "Usage:"),
        ("env", "chrysalis", "prod", "Usage:"),
        (None, "unknown", "prod", "Site configuration not readable"),
        (None, "../chrysalis", "prod", "site must contain only"),
        (None, "Chrysalis", "prod", "site must contain only"),
        (None, "chrysalis", "staging", "env must be dev or prod"),
        (None, "chrysalis", "", "Usage:"),
    ],
)
def test_targets_reject_invalid_arguments_before_execution(
    diagnostics_workspace, target, missing, site, api_env, message
) -> None:
    root, capture, process_env = diagnostics_workspace
    args = {
        "root": f"SIMBOARD_ROOT={root}",
        "site": f"site={site}",
        "env": f"env={api_env}",
    }
    result = _make(
        target, [value for key, value in args.items() if key != missing], process_env
    )
    assert result.returncode != 0
    assert message in result.stderr
    assert not capture.exists()
    assert not (root / "operations/raw_logs").exists()


@pytest.mark.parametrize("target", ["diagnostics-dry-run", "diagnostics-apply"])
def test_targets_propagate_scanner_failure(diagnostics_workspace, target) -> None:
    root, capture, process_env = diagnostics_workspace
    (root / "operations/env.prod.sh").write_text(
        "export SIMBOARD_API_BASE_URL=https://prod.example.org\n"
        "export SIMBOARD_API_TOKEN=test-token\n"
    )
    process_env["SCANNER_EXIT_CODE"] = "7"
    result = _make(
        target, [f"SIMBOARD_ROOT={root}", "site=chrysalis", "env=prod"], process_env
    )
    assert result.returncode != 0
    assert capture.exists()
    assert "Diagnostics launcher failed (exit 7)" in result.stderr
    assert str(root / "operations/raw_logs") in result.stderr
    log = next((root / "operations/raw_logs").glob("simboard-diagnostics-*.log"))
    assert "event=launcher_finished exit_code=7" in log.read_text()


@pytest.mark.parametrize(
    ("target", "succeeds"),
    [("diagnostics-dry-run", True), ("diagnostics-apply", False)],
)
def test_only_live_scans_require_api_environment_file(
    diagnostics_workspace, target, succeeds
) -> None:
    root, capture, process_env = diagnostics_workspace
    result = _make(
        target, [f"SIMBOARD_ROOT={root}", "site=chrysalis", "env=prod"], process_env
    )
    assert (result.returncode == 0) is succeeds
    assert capture.exists() is succeeds
    if not succeeds:
        assert "env.prod.sh" in result.stderr
        assert "Diagnostics launcher failed" in result.stderr
        logs = list((root / "operations/raw_logs").glob("simboard-diagnostics-*.log"))
        assert len(logs) == 1
        text = logs[0].read_text()
        assert "event=launcher_loading_api_environment" in text
        assert "event=launcher_api_environment_unreadable" in text
        assert "event=launcher_finished exit_code=1" in text
        assert "invoking scanner:" not in text
        assert not (
            root / "operations/simboard-diagnostics-chrysalis-env.prod.sh.lock"
        ).exists()
