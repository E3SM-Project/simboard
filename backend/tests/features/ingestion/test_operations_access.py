"""Named-operator ACL setup and inheritance for operations artifacts."""

import os
import pwd
import subprocess
from pathlib import Path
from shutil import which

import pytest

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "backend/app/scripts/ingestion/sites/operations"


def run(*args: str | Path, **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
        **kwargs,
    )


def acl(path: Path) -> str:
    result = run("getfacl", "-cp", path)
    assert result.returncode == 0, result.stderr
    return result.stdout


@pytest.fixture
def deployment(tmp_path: Path) -> tuple[Path, str]:
    if not all(which(tool) for tool in ("getfacl", "setfacl", "getent")):
        pytest.skip("POSIX ACL tools unavailable")
    operator = next(
        (user.pw_name for user in pwd.getpwall() if user.pw_uid != os.geteuid()),
        None,
    )
    if operator is None:
        pytest.skip("No second local account available for ACL entries")
    root = tmp_path / "deployment with spaces"
    operations = root / "operations"
    operations.mkdir(parents=True)
    probe = operations / "probe"
    probe.touch()
    result = run("setfacl", "-m", f"u:{operator}:rw-", probe)
    if result.returncode:
        pytest.skip(f"Filesystem does not support POSIX ACLs: {result.stderr}")
    probe.unlink()
    return root, operator


def configure(root: Path, operator: str, apply: str = "false", **kwargs):
    return run(
        "make",
        "operations-configure-access",
        f"SIMBOARD_ROOT={root}",
        "site=chrysalis",
        f"operators={operator}",
        f"apply={apply}",
        **kwargs,
    )


def assert_private_access(path: Path, operator: str, permissions: str) -> None:
    text = acl(path)
    entry = next(
        line for line in text.splitlines() if line.startswith(f"user:{operator}:")
    )
    effective = (
        entry.split("#effective:")[-1]
        if "#effective:" in entry
        else entry.rsplit(":", 1)[-1]
    )
    assert effective == permissions
    assert "group::---\n" in text
    assert "other::---\n" in text


def test_preview_does_not_mutate(deployment: tuple[Path, str]) -> None:
    root, operator = deployment
    operations = root / "operations"
    before = acl(root), acl(operations), list(root.rglob("*"))
    result = configure(root, operator)
    assert result.returncode == 0, result.stderr
    assert "Preview only" in result.stdout
    assert operator in result.stdout
    assert str(operations) in result.stdout
    assert before == (acl(root), acl(operations), list(root.rglob("*")))


@pytest.mark.parametrize(
    ("argument", "message"),
    [
        ("site=../chrysalis", "Invalid site"),
        ("site=unknown", "Site configuration not readable"),
        ("apply=yes", "apply must be false or true"),
        ("SIMBOARD_ROOT=", "SIMBOARD_ROOT must be set"),
    ],
)
def test_make_rejects_invalid_inputs(
    tmp_path: Path, argument: str, message: str
) -> None:
    result = run(
        "make",
        "operations-configure-access",
        f"SIMBOARD_ROOT={tmp_path}",
        "site=chrysalis",
        "operators=root",
        argument,
    )
    assert result.returncode != 0
    assert message in result.stderr
    assert not list(tmp_path.iterdir())


def test_apply_replaces_acl_and_is_idempotent(deployment: tuple[Path, str]) -> None:
    root, operator = deployment
    operations = root / "operations"
    nested = operations / "nested"
    nested.mkdir()
    credential = nested / "env.sh"
    credential.write_text("secret-token-do-not-print")
    executable = operations / "script.sh"
    executable.write_text("#!/bin/sh\n")
    executable.chmod(0o650)
    group = pwd.getpwuid(os.geteuid()).pw_gid
    result = run(
        "setfacl",
        "-m",
        f"g:{group}:rwx,d:g:{group}:rwx,d:u::rwx,d:g::rwx,d:o::---",
        operations,
    )
    assert result.returncode == 0, result.stderr
    result = configure(root, operator, "true")
    assert result.returncode == 0, result.stderr
    assert "secret-token-do-not-print" not in result.stdout + result.stderr
    for directory in (operations, nested):
        assert_private_access(directory, operator, "rwx")
        assert f"default:user:{operator}:rwx" in acl(directory)
        assert "default:group::---" in acl(directory)
        assert f"group:{group}:" not in acl(directory)
    assert_private_access(credential, operator, "rw-")
    assert_private_access(executable, operator, "rwx")
    assert credential.stat().st_mode & 0o111 == 0
    backups = list(root.glob(".simboard-acl-backup.*"))
    assert len(backups) == 1
    assert backups[0].stat().st_mode & 0o777 == 0o600
    assert "secret-token-do-not-print" not in backups[0].read_text()
    before = {path: acl(path) for path in operations.rglob("*")}
    result = configure(root, operator, "true")
    assert result.returncode == 0, result.stderr
    assert before == {path: acl(path) for path in operations.rglob("*")}

    child = nested / "new-child"
    child.mkdir()
    grandchild = child / "new-file"
    grandchild.touch()
    assert_private_access(child, operator, "rwx")
    assert f"default:user:{operator}:rwx" in acl(child)
    assert_private_access(grandchild, operator, "rw-")


@pytest.mark.parametrize("operator", ["", "bad,user", "unknown-simboard-test-user"])
def test_invalid_operators_fail_before_changes(
    deployment: tuple[Path, str], operator: str
) -> None:
    root, _ = deployment
    before = acl(root / "operations")
    result = configure(root, operator, "true")
    assert result.returncode != 0
    assert acl(root / "operations") == before
    assert not list(root.glob(".simboard-acl-backup.*"))


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo", "root-symlink"])
def test_unsafe_entries_fail_before_changes(
    deployment: tuple[Path, str], kind: str
) -> None:
    root, operator = deployment
    outside = root.parent / "outside"
    outside.touch()
    path = root / "operations/unsafe"
    before = acl(root / "operations"), acl(outside)
    if kind == "symlink":
        path.symlink_to(outside)
    elif kind == "hardlink":
        os.link(outside, path)
    elif kind == "fifo":
        os.mkfifo(path)
    else:
        alias = root.parent / "alias"
        alias.symlink_to(root, target_is_directory=True)
        root = alias
    result = configure(root, operator, "true")
    assert result.returncode != 0
    assert before == (acl(root / "operations"), acl(outside))
    assert not list(root.glob(".simboard-acl-backup.*"))


def test_acl_support_failure_does_not_change_permissions(
    deployment: tuple[Path, str], tmp_path: Path
) -> None:
    root, operator = deployment
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    command = bin_dir / "setfacl"
    command.write_text("#!/bin/sh\nexit 1\n")
    command.chmod(0o755)
    before = acl(root), acl(root / "operations")
    result = configure(
        root,
        operator,
        "true",
        env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"},
    )
    assert result.returncode != 0
    assert "does not support" in result.stderr
    assert before == (acl(root), acl(root / "operations"))
    assert not list(root.rglob(".acl-probe.*"))
    assert not list(root.glob(".simboard-acl-backup.*"))


def test_root_mask_must_allow_traversal(deployment: tuple[Path, str]) -> None:
    root, operator = deployment
    result = run("setfacl", "-m", f"u:{operator}:rwx,m::rw-", root)
    assert result.returncode == 0, result.stderr
    before = acl(root), acl(root / "operations")
    result = configure(root, operator, "true")
    assert result.returncode != 0
    assert "mask must permit traversal" in result.stderr
    assert before == (acl(root), acl(root / "operations"))


def test_foreign_owned_entries_fail_before_changes(
    deployment: tuple[Path, str], tmp_path: Path
) -> None:
    root, operator = deployment
    file = root / "operations/another-operators-log"
    file.touch()
    before = acl(root), acl(root / "operations"), acl(file)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    command = bin_dir / "stat"
    real_stat = which("stat")
    assert real_stat is not None
    command.write_text(
        '#!/bin/bash\nif [[ "$2" == %u && "${!#}" == "$FOREIGN_FILE" ]]; then\n'
        '  printf "%s\\n" "$FOREIGN_UID"\n'
        "else\n"
        '  exec "$REAL_STAT" "$@"\n'
        "fi\n"
    )
    command.chmod(0o755)
    result = configure(
        root,
        operator,
        "true",
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "REAL_STAT": real_stat,
            "FOREIGN_FILE": str(file),
            "FOREIGN_UID": str(os.geteuid() + 1),
        },
    )
    assert result.returncode != 0
    assert "Current user must own" in result.stderr
    assert "another owner's ACL" in result.stderr
    assert before == (acl(root), acl(root / "operations"), acl(file))
    assert not list(root.glob(".simboard-acl-backup.*"))


def test_reapply_removes_unlisted_operators(deployment: tuple[Path, str]) -> None:
    root, operator = deployment
    result = configure(root, operator, "true")
    assert result.returncode == 0, result.stderr
    owner = pwd.getpwuid(os.geteuid()).pw_name
    result = configure(root, owner, "true")
    assert result.returncode == 0, result.stderr
    assert f"user:{operator}:" not in acl(root / "operations")
    assert f"default:user:{operator}:" not in acl(root / "operations")
    assert_private_access(root / "operations", owner, "rwx")


def test_backup_restores_existing_permissions(deployment: tuple[Path, str]) -> None:
    root, operator = deployment
    operations = root / "operations"
    file = operations / "existing.txt"
    file.touch()
    before = {path: acl(path) for path in (root, operations, file)}
    result = configure(root, operator, "true")
    assert result.returncode == 0, result.stderr
    backup = next(root.glob(".simboard-acl-backup.*"))
    result = run("setfacl", f"--restore={backup}")
    assert result.returncode == 0, result.stderr
    assert before == {path: acl(path) for path in before}


def test_missing_defaults_fail_closed_during_initialization(
    deployment: tuple[Path, str],
) -> None:
    root, operator = deployment
    result = configure(root, operator, "true")
    assert result.returncode == 0, result.stderr
    result = run("setfacl", "-k", root / "operations")
    assert result.returncode == 0, result.stderr
    result = run(
        "make", "operations-init-cron", "site=chrysalis", f"SIMBOARD_ROOT={root}"
    )
    assert result.returncode != 0
    assert "missing restrictive default ACLs" in result.stderr
    assert not (root / "operations/chrysalis.crontab").exists()


def test_initializers_preserve_inherited_operator_write_access(
    deployment: tuple[Path, str],
) -> None:
    root, operator = deployment
    owner = pwd.getpwuid(os.geteuid()).pw_name
    result = configure(root, f"{owner} {operator}", "true")
    assert result.returncode == 0, result.stderr
    result = run(
        "make",
        "operations-init-env",
        "site=chrysalis",
        f"SIMBOARD_ROOT={root}",
        input="https://dev.test\nsecret-dev\nhttps://prod.test\nsecret-prod\n",
    )
    assert result.returncode == 0, result.stderr
    assert "secret-dev" not in result.stdout + result.stderr
    result = run(
        "make", "operations-init-cron", "site=chrysalis", f"SIMBOARD_ROOT={root}"
    )
    assert result.returncode == 0, result.stderr
    result = run(
        "make",
        "operations-init-v3-env",
        "env=dev",
        f"SIMBOARD_ROOT={root}",
        input="https://dev.test\nsecret-v3\n/data/diagnostics\n",
    )
    assert result.returncode == 0, result.stderr
    for name in ("env.dev.sh", "env.prod.sh", "chrysalis.crontab", "lcrc-v3.dev.env"):
        assert_private_access(root / "operations" / name, operator, "rw-")


def test_launcher_preserves_log_and_lock_access(
    deployment: tuple[Path, str],
) -> None:
    root, operator = deployment
    result = configure(root, operator, "true")
    assert result.returncode == 0, result.stderr
    runtime = root / "repository/simboard/backend/.venv/bin"
    runtime.mkdir(parents=True)
    python = runtime / "python"
    python.write_text("#!/bin/sh\nexit 0\n")
    python.chmod(0o755)
    result = run(
        "bash",
        SCRIPTS.parent / "site_ingestion_launcher.sh",
        "chrysalis",
        "staging",
        env={
            **os.environ,
            "SIMBOARD_ROOT": str(root),
            "DRY_RUN": "true",
            "DRY_RUN_USE_REMOTE_STATE": "false",
            "PYTHON_BIN": str(python),
        },
    )
    assert result.returncode == 0, result.stderr
    operations = root / "operations"
    assert_private_access(operations / "raw_logs", operator, "rwx")
    logs = list((operations / "raw_logs").glob("*.log"))
    locks = list(operations.glob("*.lock"))
    assert len(logs) == len(locks) == 1
    for path in logs + locks:
        assert_private_access(path, operator, "rw-")


def test_provision_preserves_acl_policy(deployment: tuple[Path, str]) -> None:
    root, operator = deployment
    result = configure(root, operator, "true")
    assert result.returncode == 0, result.stderr
    bin_dir = root.parent / "bin"
    bin_dir.mkdir()
    for name in ("git", "make"):
        command = bin_dir / name
        command.write_text("#!/bin/sh\nexit 0\n")
        command.chmod(0o755)
    getent = bin_dir / "getent"
    getent.write_text("#!/bin/sh\nexit 0\n")
    getent.chmod(0o755)
    chgrp = bin_dir / "chgrp"
    chgrp.write_text('#!/bin/sh\ntouch "$CHGRP_CAPTURE"\n')
    chgrp.chmod(0o755)
    capture = root.parent / "chgrp-called"
    (root / "repository/simboard/.git").mkdir(parents=True)
    operations = root / "operations"
    before = acl(operations)
    result = run(
        "bash",
        SCRIPTS / "provision_operations.sh",
        env={
            **os.environ,
            "SIMBOARD_ROOT": str(root),
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "CHGRP_CAPTURE": str(capture),
        },
    )
    assert result.returncode == 0, result.stderr
    assert acl(operations) == before
    assert not capture.exists()
    for name in ("raw_logs", "quality_assurance"):
        assert_private_access(operations / name, operator, "rwx")


def test_refresh_lock_inherits_operator_access(
    deployment: tuple[Path, str],
) -> None:
    root, operator = deployment
    result = configure(root, operator, "true")
    assert result.returncode == 0, result.stderr
    (root / "repository/simboard/.git").mkdir(parents=True)
    bin_dir = root.parent / "bin"
    bin_dir.mkdir()
    git = bin_dir / "git"
    git.write_text(
        '#!/bin/sh\ncase "$*" in\n  *rev-parse*) printf "revision\\n" ;;\nesac\n'
    )
    git.chmod(0o755)
    result = run(
        "bash",
        SCRIPTS / "refresh_repository.sh",
        env={
            **os.environ,
            "SIMBOARD_ROOT": str(root),
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
        },
    )
    assert result.returncode == 0, result.stderr
    assert_private_access(
        root / "operations/simboard-ingestion-provision.lock", operator, "rw-"
    )
