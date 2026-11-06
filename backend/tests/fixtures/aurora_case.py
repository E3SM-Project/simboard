"""Small, complete Aurora execution used by ingestion onboarding tests.

The file names and contents follow the CIME provenance contract consumed by
SimBoard. Values are synthetic, not copied from a private Aurora run; native
validation must still compare this contract with one real PACE-visible execution.

``stage_aurora_performance_root`` reproduces the directory layout PACE's
``pace_archive_aurora.sh`` leaves on Aurora: ``OLD_PERF`` inside the staging
root, unprefixed ``performance_archive_<timestamp>`` batches both archived and
left behind at the top level, and ``pace-exps-*`` upload work trees.
"""

import gzip
from pathlib import Path

CASE_NAME = "simboard.aurora.smoke"
HPC_USERNAME = "rjain"
EXECUTION_ID = "1457968.261014-145239"
ARCHIVED_EXECUTION_ID = "1457001.260725-101500"
ARCHIVE_MONTH = "2026-07"
ARCHIVED_BATCH = "performance_archive_2026_07_25_12_08_05"
LEFTOVER_BATCH = "performance_archive_2026_07_20_15_27_24"
UPLOAD_WORK_TREE = "pace-exps-amametjanov-2026-07-20-164459"

ENV_CASE = f"""<config>
  <entry id="CASE" value="{CASE_NAME}" />
  <entry id="MACH" value="aurora" />
  <entry id="REALUSER" value="{HPC_USERNAME}" />
  <entry id="CASE_HASH" value="e7718b7d7fb6df2a20ac595018464570db8d934cee518393602137ef8329785a" />
  <entry id="COMPSET" value="F2010-SCREAMv1" />
</config>
"""
ENV_BUILD = """<config>
  <entry id="COMPILER" value="oneapi-ifx" />
  <entry id="GRID" value="ne30pg2_ne30pg2" />
</config>
"""
ENV_RUN = """<config>
  <entry id="RUN_TYPE" value="startup" />
  <entry id="RUN_STARTDATE" value="2010-01-01" />
  <entry id="CONTINUE_RUN" value="FALSE" />
  <entry id="STOP_OPTION" value="ndays" />
  <entry id="STOP_N" value="5" />
</config>
"""
README_CASE = (
    "2026-10-14 14:52:39: create_newcase "
    f"--case {CASE_NAME} --compset F2010-SCREAMv1 "
    "--res ne30pg2_ne30pg2 --machine aurora\n"
)


def stage_aurora_case(case_parent: Path, *, execution_id: str = EXECUTION_ID) -> Path:
    """Create one parseable ``case/execution`` tree and return the case path."""
    case = case_parent / CASE_NAME
    execution = case / execution_id
    docs = execution / f"CaseDocs.{execution_id}"
    docs.mkdir(parents=True)
    job = execution_id.split(".")[0]
    files = {
        docs / f"env_case.xml.{execution_id}.gz": ENV_CASE,
        docs / f"env_build.xml.{execution_id}.gz": ENV_BUILD,
        docs / f"env_run.xml.{execution_id}.gz": ENV_RUN,
        docs / f"README.case.{execution_id}.gz": README_CASE,
        execution / f"CaseStatus.{execution_id}.gz": (
            f"2026-10-14 14:52:39: case.run starting {job}\n"
            f"2026-10-14 15:30:00: case.run success {job}\n"
        ),
        execution / f"GIT_DESCRIBE.{execution_id}.gz": "v4.0.0-alpha-12-g1a2b3c4\n",
        execution / f"e3sm_timing.{CASE_NAME}.{execution_id}": (
            f"  Case : {CASE_NAME}\n  Machine : aurora\n  LID : {execution_id}\n"
        ),
        execution / f"cpl.log.{execution_id}.gz": (
            "(seq_timemgr_clockPrint) Clock = drv            1\n"
            "(seq_timemgr_clockPrint)   Start Time  =     20100101   00000\n"
            "(seq_timemgr_clockPrint)   Curr Time   =     20100101   00000\n"
            "(seq_timemgr_clockPrint)   Ref Time    =     20100101   00000\n"
            "(seq_timemgr_clockPrint)   Stop Time   =     20100106   00000\n"
        ),
    }
    for path, content in files.items():
        if path.suffix == ".gz":
            with gzip.open(path, "wt") as stream:
                stream.write(content)
        else:
            path.write_text(content)

    return case


def stage_aurora_performance_root(staging_root: Path) -> Path:
    """Stage Aurora's PACE layout under ``staging_root`` and return ``OLD_PERF``.

    Only ``<user>/<case>/<EXECUTION_ID>`` is live staging output. Every other
    execution is a copy PACE already processed and must not be staged again:
    one archived batch (COMPLETED and FAILED buckets), one batch left at the
    top level after an interrupted upload, and one upload work tree.
    """
    stage_aurora_case(staging_root / HPC_USERNAME)

    old_perf = staging_root / "OLD_PERF"
    archived = old_perf / ARCHIVE_MONTH / ARCHIVED_BATCH
    stage_aurora_case(
        archived / "COMPLETED" / HPC_USERNAME, execution_id=ARCHIVED_EXECUTION_ID
    )
    stage_aurora_case(
        archived / "FAILED" / HPC_USERNAME, execution_id="1457002.260725-111500"
    )

    leftover = staging_root / LEFTOVER_BATCH
    stage_aurora_case(
        leftover / "COMPLETED" / HPC_USERNAME, execution_id="1457003.260720-101500"
    )
    stage_aurora_case(
        staging_root / UPLOAD_WORK_TREE / "exp0" / HPC_USERNAME,
        execution_id="1457004.260720-121500",
    )
    (staging_root / "manual-logs").mkdir()
    (staging_root / "pace_archive_aurora.sh").write_text("# PACE collector\n")

    return old_perf
