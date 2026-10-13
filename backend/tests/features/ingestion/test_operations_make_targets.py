"""Operations Make target naming, grouping, and phony declarations."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
OPS_TARGETS = (
    "ops-provision",
    "ops-refresh",
    "ops-init-env",
    "ops-init-v3-env",
    "ops-init-cron",
    "ops-configure-access",
)


def run(*args: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def test_operations_help_has_its_own_section() -> None:
    result = run("make", "help")
    assert result.returncode == 0, result.stderr
    backend, rest = result.stdout.split("Operations:\n", 1)
    operations, _ = rest.split("Frontend:\n", 1)
    deployment, rest = operations.split("  Ingestion:\n", 1)
    ingestion, diagnostics = rest.split("  Diagnostics:\n", 1)
    assert "  Deployment:\n" in deployment
    groups = (
        (deployment, OPS_TARGETS),
        (
            ingestion,
            ("ingest-dry-run", "ingest-apply", "v3-ingest-dry-run", "v3-ingest-apply"),
        ),
        (
            diagnostics,
            (
                "diags-dry-run",
                "diags-apply",
                "diags-init-archive",
                "v3-diags-dry-run",
                "v3-diags-apply",
            ),
        ),
    )
    for section, targets in groups:
        for target in targets:
            assert f"make {target} " in section
            assert target not in backend
    assert "make operations-" not in result.stdout
    assert "make diagnostics-" not in result.stdout
    assert "make v3-diagnostics-" not in result.stdout


@pytest.mark.parametrize("target", OPS_TARGETS)
def test_operations_targets_are_phony(tmp_path: Path, target: str) -> None:
    (tmp_path / target).touch()
    result = run("make", "-f", ROOT / "Makefile", "-C", tmp_path, "-n", target)
    assert result.returncode == 0, result.stderr
    assert "bash" in result.stdout
