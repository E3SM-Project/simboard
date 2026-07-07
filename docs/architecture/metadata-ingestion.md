# Metadata Ingestion Architecture

HPC sites produce performance metadata that site-side automation collects and SimBoard ingests into PostgreSQL. Automated HPC collection reaches SimBoard ingestion through one of two submission workflows depending on whether the source archive is readable from the SimBoard backend environment on NERSC Spin.

Browser/manual uploads are supported separately and are not part of automated HPC state reconstruction from previously submitted execution IDs.

## Terminology

### Process terms

| Term       | Definition                                                                                                                                                                                                        |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Collection | Site-side scanning, discovery, validation, and packaging work that inspects case directories and their execution subdirectories to determine which case directories contain newly discovered complete executions. |
| Ingestion  | SimBoard API and database work that accepts collected metadata, normalizes it, and persists records in PostgreSQL.                                                                                                |

### Filesystem terms

| Term              | Definition                                                                                                             |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Staging directory | The active `PERF_ARCHIVE_DIR` tree where new performance output from E3SM runs appears before PACE moves it elsewhere. |
| Archive directory | The long-term `OLD_PERF_ARCHIVE_DIR` tree managed by PACE after staging output is moved.                               |

### Case and execution state terms

Case-level state is derived from execution-level state.

| Term                      | Definition                                                                                                                                                                                                                                                                                                                                                                          |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Complete execution        | An execution directory that has the required metadata files `env_case.xml..*.gz`, `env_build.xml..*.gz`, `env_run.xml..*`, `README.case..*.gz`, `CaseStatus..*.gz`, and `e3sm_timing..*`, with the required metadata present in those files. The timing file must also provide a non-empty execution ID (LID). Optional `GIT_CONFIG..*.gz` and `GIT_STATUS..*.gz` are not required. |
| Incomplete execution      | An execution directory that is missing one or more required metadata files, is missing required metadata in those files, does not provide a non-empty execution ID (LID) in the timing file, or cannot be read during discovery. Incomplete executions are skipped and do not enter case state.                                                                                     |
| Submission-qualified case | A parent case directory for which collection found at least one newly discovered complete execution ID that is not already present in the stored known execution IDs.                                                                                                                                                                                                               |
| Selected submission case  | A submission-qualified case that a given runner invocation selects for dry-run reporting or submission after applying any per-run cap such as `MAX_CASES_PER_RUN`.                                                                                                                                                                                                                  |
| Deferred execution        | A newly discovered valid execution ID that belongs to a submission-qualified case but is not selected in the current runner invocation because a per-run cap stopped selection earlier.                                                                                                                                                                                             |
| `processed_execution_ids` | Execution IDs already recorded in stored processed state for one case, reconstructed from prior successful ingestion state so future collection can treat matching discovered executions as already known.                                                                                                                                                                          |

### Runner counter and log field terms

These exact field names appear in runner completion logs, summary tables, and
related execution-decision reporting. Where a field is just the emitted count
form of a human term defined below, this section maps the exact field name to
that canonical term instead of repeating the full concept definition.

| Term                                | Definition                                                                                                                                  |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `submission_qualified_cases`        | Count form of “Submission-qualified case.”                                                                                                  |
| `selected_submission_cases`         | Count form of “Selected submission case.”                                                                                                   |
| `execution_dirs_scanned`            | Count of execution directories whose names matched the execution pattern and were checked during discovery validation.                      |
| `execution_dirs_accepted`           | Count of scanned execution directories that passed discovery validation and were retained as valid discovered executions.                   |
| `skipped_incomplete`                | Count of execution directories rejected during discovery because required metadata files or fields were missing or incomplete.              |
| `skipped_invalid`                   | Count of execution directories rejected during discovery because metadata was invalid or the directory could not be read.                   |
| `accepted_execution_ids`            | Count of newly discovered valid execution IDs selected for the current run.                                                                 |
| `rejected_existing_execution_ids`   | Count of valid discovered execution IDs already present in stored `processed_execution_ids` state.                                          |
| `rejected_incomplete_execution_ids` | Count of execution IDs rejected during discovery because required metadata files or fields were missing or incomplete.                      |
| `rejected_invalid_execution_ids`    | Count of execution IDs rejected during discovery because metadata was invalid or the directory could not be read.                           |
| `deferred_execution_ids`            | Count of newly discovered valid execution IDs not selected for the current run because per-run case capping stopped earlier case selection. |

## Performance Directories

There are two PACE performance directories on HPC sites: staging (`PERF_ARCHIVE_DIR`) and archive (`OLD_PERF_ARCHIVE_DIR`).

> **Info**
>
> SimBoard automation can scan either `PERF_ARCHIVE_DIR` or
> `OLD_PERF_ARCHIVE_DIR` depending on runner configuration.

### 1. Staging directory (`PERF_ARCHIVE_DIR`)

Active filesystem location where E3SM cases write new performance output. PACE refers to this as `PERF_ARCHIVE_DIR`.

Structure:

```bash
user/
  case/
    execution/
```

Example NERSC path:

```bash
/global/cfs/projectdirs/e3sm/performance_archive
├── abarthel
│   └── 20260618.v3.LR.piControl.mct.1day-av.pm-cpu
├── adonahue
│   ├── downscaling.ne256pg2_ne256pg2.F2010-SCREAMv1.20260624
│   ├── Downscaling.ne32pg2_ne32pg2.F2010-SCREAMv1.20260616
│   ├── Downscaling.ne32pg2_ne32pg2.F2010-SCREAMv1.20260622
│   └── downscaling.y2.ne30pg2_ne30pg2.F2010-SCREAMv1.c10-sep11-f602da2b98
...
```

### 2. Archive directory (`OLD_PERF_ARCHIVE_DIR`)

Long-term filesystem location managed by PACE, referred to as `OLD_PERF_ARCHIVE_DIR`. PACE moves staging output into this directory once per day.

Structure:

```bash
year-month/
  performance_archive_<timestamp>/
    status/ # Note, status only appears on machines that support it, such as on NERSC and ALCF.
      user/
        case/
          execution/
```

Example NERSC path for "COMPLETED"` status cases:

```bash
/global/cfs/projectdirs/e3sm/OLD_PERF/2026-05/performance_archive_2026_05_22_08_01_32/COMPLETED
.
├── azamat
│   └── SMS.ne30pg2_EC30to60E2r2.WCYCLXX2010.pm-gpu_gnugpu.a1
│       └── 42473005.250904-163426
├── bogensch
│   ├── scream_dpxx_DYCOMSrf01.3dturb.001a
│   │   └── 53269661.260521-154752
│   ├── scream_dpxx_DYCOMSrf01.3dturb.100m.001a
│   │   └── 53270491.260521-162926
│   ├── scream_dpxx_DYCOMSrf01.3dturb.100m.cntl
│   │   └── 53271053.260521-170115
│   └── scream_dpxx_GATEIDEAL.horiz_diff.200m.010a.cntl
│       └── 53253881.260522-001001
├── feng809
│   └── SSP245_ZATM_BGC_ne30pg2_f09_oEC60to30v3_2026051915
│       ├── 53193441.260521-011112
│       └── 53246396.260521-161023
├── jayesh
│   ├── test_ne30pg2_r05_IcoswISC30E3r5.WCYCL1850_hdf5c_lossy_mt8_norestarts
│   │   └── 53247504.260521-132759
│   └── test_ne30pg2_r05_IcoswISC30E3r5.WCYCL1850_hdf5c_lossy_nomt_norestarts
│       └── 53245397.260521-082234
├── meng
│   ├── f2010-eamxx-mam4xx_ne30pg2_ne30pg2_gnugpu.mamxx_srf_emis
│   │   └── 53250710.260522-000618
│   └── f2010-eamxx-mam4xx_ne30pg2_ne30pg2_gnugpu.master
│       └── 53250675.260522-000505
├── sprice
│   ├── 20260305.BGWCYCL2010.ne30pg2_r05_IcoswISC30E3r5_gis4to40.pm-cpu.testConfigNewSMBandIC
│   │   ├── 53243007.260521-065833
│   │   └── 53248389.260522-014341
│   └── 20260320.WCYCL2010NS.ne30pg2_r05_IcoswISC30E3r5.pm-cpu.baseline
│       ├── 53240397.260521-065833
│       └── 53247565.260521-233111
├── whannah
│   └── E3SM.2026-impflx-debug-00.GPU.F2010-SCREAMv1.ne256pg2_ne256pg2.NN_128.iflx_0.gust_0
│       ├── 53244020.260521-104056
│       └── 53254801.260522-022602
└── yuying
    └── ne30pg2_ne30pg2.F20TR-SCREAMv1.260501.cosp_test
        └── 53262495.260521-133430
...
```

## Site Summary

| Site / Machine     | Collection / submission mode    | Scheduler                      | Staging directory (`PERF_ARCHIVE_DIR`)                | Archive directory (`OLD_PERF_ARCHIVE_DIR`)  |
| ------------------ | ------------------------------- | ------------------------------ | ----------------------------------------------------- | ------------------------------------------- |
| NERSC / Perlmutter | Local path submission           | Cron                           | `/global/cfs/projectdirs/e3sm/performance_archive`    | `/global/cfs/projectdirs/e3sm/OLD_PERF`     |
| LCRC / Chrysalis   | Remote automated archive upload | Sandia Jenkins                 | `/lcrc/group/e3sm/PERF_Chrysalis/performance_archive` | `/lcrc/group/e3sm/PERF_Chrysalis/OLD_PERF`  |
| SNL / Compy        | Remote automated archive upload | Sandia Jenkins                 | `/compyfs/performance_archive`                        | `/compyfs/OLD_PERF`                         |
| ALCF / Aurora      | Remote automated archive upload | ALCF GitLab job, daily at 7 AM | `/lus/flare/projects/E3SM_Dec/performance_archive`    | `TODO`                                      |
| OLCF / Frontier    | Remote automated archive upload | Local cron job                 | `/lustre/orion/proj-shared/cli115`                    | `/lustre/orion/cli115/proj-shared/OLD_PERF` |

## Collection and Submission Modes

Automated HPC collection reaches SimBoard ingestion through two site-side submission modes. Both use database-backed stored known execution IDs, but they submit submission-qualified cases through different routes:

- `nersc_archive_ingestor.py` for local path submission on NERSC / Perlmutter
- `hpc_upload_archive_ingestor.py` for remote automated archive upload from LCRC and other DOE sites

| Mode                            | Script / entry point             | Access pattern                                                                                                         | Route                                | Use when                                        | Examples                          |
| ------------------------------- | -------------------------------- | ---------------------------------------------------------------------------------------------------------------------- | ------------------------------------ | ----------------------------------------------- | --------------------------------- |
| Local path submission           | `nersc_archive_ingestor.py`      | Site-side collection submits a mounted case directory path inside `PERF_ARCHIVE_DIR` (mounted at `PERF_ARCHIVE_ROOT`). | `/api/v1/ingestions/from-path`       | Source archive is readable from NERSC Spin.     | NERSC / Perlmutter                |
| Remote automated archive upload | `hpc_upload_archive_ingestor.py` | Site job uploads one submission-qualified case archive over HTTPS.                                                     | `/api/v1/ingestions/from-hpc-upload` | Source archive is not readable from NERSC Spin. | LCRC / Chrysalis; other DOE sites |
| Browser/manual upload           | N/A                              | User uploads an archive through the browser.                                                                           | `/api/v1/ingestions/from-upload`     | Manual, test, or ad hoc ingestion is needed.    | User workstation                  |

### Automated Submission-State Flow

Both automated scripts follow the same submission-state sequence:

1. Scan either the staging performance directory (`PERF_ARCHIVE_DIR`, mounted at `PERF_ARCHIVE_ROOT`) or the archive directory (`OLD_PERF_ARCHIVE_DIR`, mounted at `OLD_PERF_ARCHIVE_ROOT`) for case directories and metadata.
2. Read known execution IDs from `/api/v1/ingestions/state`.
3. Compare discovered complete execution IDs with database-backed state.
4. Submit each case that contains at least one newly discovered execution ID, along with the full discovered `processed_execution_ids` set.
5. SimBoard stores the submitted known execution IDs on ingestion audit rows.
6. Future runs reconstruct the known execution IDs from PostgreSQL.

Collection atomicity for staging scans is `(case_path, execution_id)`. Archive
scans additionally deduplicate by stable logical case identity plus
`execution_id` so timestamped snapshot parents do not cause repeated archive
ingestion across `OLD_PERF_ARCHIVE_DIR` snapshots. Updating files inside an
already recorded execution directory does not make that execution eligible
again, and incomplete executions do not become case state.

Remote automated uploads must contain exactly one case directory per request. The submitted `case_path` is used as the stable case identifier for that uploaded case.

```mermaid
flowchart TD
  subgraph RUNNERS["Site-Side Collection Scripts"]
    NERSC["nersc_archive_ingestor.py\nNERSC / Perlmutter"]
    HPC["hpc_upload_archive_ingestor.py\nLCRC / other DOE sites"]

    SCAN["Scan staging filesystem\nPERF_ARCHIVE_DIR"]
    STATE_REQ["Read known execution IDs\nGET /api/v1/ingestions/state"]
    COMPARE["Compare collection results\nwith database-backed state"]
    CHANGED["Submission-qualified\ncase directories"]

    NERSC_PAYLOAD["Submission-qualified case path\n+ processed_execution_ids"]
    HPC_PAYLOAD["One case archive\n+ case_path\n+ processed_execution_ids"]
  end

  subgraph BACKEND["SimBoard Backend"]
    STATE["State API"]
    PATH["POST /api/v1/ingestions/from-path"]
    UPLOAD["POST /api/v1/ingestions/from-hpc-upload"]
    NORMALIZE["Normalize and validate"]
    AUDIT["Store ingestion audit row\nwith known execution IDs"]
    DB[("PostgreSQL")]
  end

  NERSC --> SCAN
  HPC --> SCAN

  SCAN --> STATE_REQ
  STATE_REQ --> STATE
  STATE -->|"known execution IDs"| STATE_REQ
  STATE --> DB

  STATE_REQ --> COMPARE
  COMPARE --> CHANGED

  CHANGED --> NERSC_PAYLOAD --> PATH
  CHANGED --> HPC_PAYLOAD --> UPLOAD

  PATH --> NORMALIZE
  UPLOAD --> NORMALIZE
  NORMALIZE --> AUDIT --> DB
```

### Runner Configuration

All automated ingestion requests require a bearer API token. Both site-side runners use:

- `SIMBOARD_API_BASE_URL`
- `SIMBOARD_API_TOKEN`
- `SCAN_MODE`
- `PERF_ARCHIVE_ROOT`
- `OLD_PERF_ARCHIVE_ROOT`
- `MACHINE_NAME`
- `DRY_RUN`

They also support these tuning options:

- `MAX_CASES_PER_RUN`
- `MAX_ATTEMPTS`
- `REQUEST_TIMEOUT_SECONDS`
- `ARCHIVE_YEAR_START`
- `ARCHIVE_YEAR_END`

`SCAN_MODE` selects whether a runner scans staging or archive roots. Year-range
filters apply only to archive mode and are intended for targeted backfills, not
for normal staging collection.

`MAX_CASES_PER_RUN` is an optional per-run throttle. Leave it unset for normal
operation when runners should submit every submission-qualified case they find.
Set it when operators need to limit one invocation's submission volume, such as:

- draining a large backlog gradually after downtime or a collection pause
- reducing API, database, or upload load during periods of heavy ingestion
- rolling out ingestion changes cautiously while watching logs and results
- debugging or validating behavior on a small batch before allowing full drain
- mitigating temporary backend or network instability without stopping collection

### Stored Results

After ingestion, SimBoard stores normalized cases, simulations, machines, artifacts, links, and audit records in PostgreSQL. Simulation rows preserve parsed `CASE_HASH` values so the frontend can group related executions inside a case without assigning persistent reference runs. The frontend reads the resulting catalog data through `/api/v1` endpoints.

> **Note**
>
> SimBoard records artifact references such as output directories, source archive locations, run scripts, and batch logs to support reproducibility.
>
> Referenced source archive directories may be cleaned up by scheduled site-side jobs outside of SimBoard to limit storage growth.

### Reference: PACE Upload Scripts

PACE uses site-specific upload scripts and schedulers to collect or upload metadata from `PERF_ARCHIVE_DIR`. These serve as references for existing DOE-site automation and are not part of the SimBoard ingestion API. They also provide context for the design of the remote automated upload workflow and the expected contents of staged performance metadata.

Source: [PACE Collection and Upload Reference](https://e3sm.atlassian.net/wiki/spaces/EPG/pages/5477335106/PACE+Collection+and+Upload+Reference)
