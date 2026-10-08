"""Portable metadata excerpts for the continuation-date regression (#370).

Source: qa/cases/OLD_PERF/v3.LR.piClim-histGHG_0201/<execution_id>/.
XML entries, the initial driver clock (cpl.log lines 287–291), and the latest
CaseStatus attempt are retained. Unrelated configuration and log history are
omitted. Required artifacts are gzipped at staging time to match discovery;
the original QA files are plain text and remain untouched.
"""

import gzip
from pathlib import Path

CASE_NAME = "v3.LR.piClim-histGHG_0201"
EXECUTIONS = {
    "729179.250417-002844": (
        "20190101",
        "20200101",
        "2025-04-17 00:28:44",
        "2025-04-17 03:39:33",
    ),
    "729278.250417-112829": (
        "20200101",
        "20210101",
        "2025-04-17 11:28:29",
        "2025-04-17 14:38:08",
    ),
    "729596.250417-144221": (
        "20210101",
        "20220101",
        "2025-04-17 14:42:21",
        "2025-04-17 17:53:33",
    ),
    "729670.250417-175452": (
        "20220101",
        "20230101",
        "2025-04-17 17:54:52",
        "2025-04-17 21:06:26",
    ),
    "729682.250417-210752": (
        "20230101",
        "20240101",
        "2025-04-17 21:07:52",
        "2025-04-18 00:19:49",
    ),
}
ENV_CASE = """<config>
  <entry id="CASE" value="v3.LR.piClim-histGHG_0201" />
  <entry id="MACH" value="chrysalis" />
  <entry id="REALUSER" value="ac.kai.zhang" />
  <entry id="CASE_HASH" value="f5f0d5b7eeb4c9527af168a441a914ca67dc03c62c56ace5a176151e52cc9409" />
  <entry id="COMPSET" value="20TRSOI_EAM%CMIP6-GHG_ELM%CNPRDCTCBCTOP_MPASSI%PRES_DOCN%DOM_MOSART_SGLC_SWAV_SIAC_SESP" />
</config>
"""
ENV_BUILD = """<config>
  <entry id="COMPILER" value="intel" />
  <entry id="GRID" value="a%ne30np4.pg2_l%r05_oi%IcoswISC30E3r5_r%r05_g%null_w%null_z%null_m%IcoswISC30E3r5" />
</config>
"""
ENV_RUN = """<config>
  <entry id="RUN_TYPE" value="hybrid" />
  <entry id="RUN_STARTDATE" value="1850-01-01" />
  <entry id="RUN_REFDATE" value="0201-01-01" />
  <entry id="CONTINUE_RUN" value="TRUE" />
  <entry id="STOP_OPTION" value="nyears" />
  <entry id="STOP_N" value="1" />
</config>
"""
README_CASE = """2025-03-06 10:28:54: create_newcase --case v3.LR.piClim-histGHG_0201 --compset F20TR-GHG --res ne30pg2_r05_IcoswISC30E3r5 --machine chrysalis
"""


def stage_continuation_case(root: Path, *, compressed_cpl: bool = False) -> Path:
    """Stage the real case's relevant metadata without depending on QA paths."""
    case = root / CASE_NAME
    for lid, (start, stop, run_start, run_end) in EXECUTIONS.items():
        execution = case / lid
        docs = execution / f"CaseDocs.{lid}"
        docs.mkdir(parents=True)
        files = {
            docs / f"env_case.xml.{lid}.gz": ENV_CASE,
            docs / f"env_build.xml.{lid}.gz": ENV_BUILD,
            docs / f"env_run.xml.{lid}.gz": ENV_RUN,
            docs / f"README.case.{lid}.gz": README_CASE,
            execution / f"CaseStatus.{lid}.gz": (
                f"{run_start}: case.run starting {lid.split('.')[0]}\n"
                f"{run_end}: case.run success {lid.split('.')[0]}\n"
            ),
            execution / f"GIT_DESCRIBE.{lid}.gz": "v3.0.2-2-g7c4ec379a6\n",
            execution
            / f"e3sm_timing.{CASE_NAME}.{lid}": f"  Case : {CASE_NAME}\n  LID : {lid}\n",
            execution / f"cpl.log.{lid}{'.gz' if compressed_cpl else ''}": (
                "(seq_timemgr_clockPrint) Clock = drv            1\n"
                "(seq_timemgr_clockPrint)   Start Time  =     18500101   00000\n"
                f"(seq_timemgr_clockPrint)   Curr Time   =     {start}   00000\n"
                "(seq_timemgr_clockPrint)   Ref Time    =     18500101   00000\n"
                f"(seq_timemgr_clockPrint)   Stop Time   =     {stop}   00000\n"
            ),
        }
        for path, content in files.items():
            if path.suffix == ".gz":
                with gzip.open(path, "wt") as stream:
                    stream.write(content)
            else:
                path.write_text(content)
    return case
