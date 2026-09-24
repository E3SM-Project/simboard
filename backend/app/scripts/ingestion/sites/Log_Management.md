Near midnight (UTC?) each day, all ~96 15-minute-scheduled staging run logfiles
are processed to itemize timestamped new case_ids (plus respective exec_ids).
The result is supplied as a daily "summary gains" log, and the 96 source logs
are moved to log_history.

By default a daily cron job can select a date, find all 96 files generated for
that date for processing.  The script can accept a command-line YYYYMMDD date
as override, and seeks just those to produce a summary manually.

==============================================================================

Background:  Each day, 96 15-minute "staging runs" are conducted, allowing
simboard users rapid update ability for ongoing operations.  As well, after
PACE sweeps up new case/exec "staging" materials on a daily basis for 
archiving, any case/execs that may have been missed by the 15-minute simboard
staging ingestion can be picked up by a daily simboard "archive" run that
targets the PACE archive directories.

All of this activity results in 96 simboard "staging" run logs, and one
"archive" run log each day.  The detail provided by each log is valuable for
quick runtime problem analysis, but also taxing in terms of space and inodes.

===========================================================================

SIMBOARD LOG MANAGEMENT

LOG_SUMMARIZATION:

    tool:    [site]/summarize_collection.sh  (run daily when "day" completes)
    input:   [operations]/raw_logs/          (selected by dates)
    output:  [operations]/summary_logs       (Collection_Report_<date>)
             (raw logs used as input are moved to [operations]/history_logs)

    1. Summarize staging and archive gains in the daily summary log
    2. Summarize errors encountered (not yet well-defined)

LOG_REDUCTION:

    tool:    [site]/log_redux.sh
    input:   [operations]/history_logs  (all log files moved from raw_logs)
    output:  [operations]/history_logs  (multiple <Week-Block>.tar.gz)

    Can be run on any schedule (daily or weekly, etc).

    Based upon logfile dates found, a sets of "Week-Blocks" are defined.
    Each Week-Block is named <YYYYMMDD-YYYYMMDD>, where the first date is
    a Sunday, and the second date is the following Saturday.

    Log files found are added to a tar archive <Week-Block>.tar.gz according
    to their log-date.  If new logs arrive for an existing Week-Block, the
    corresponding tar file is opened and appended to, otherwise created new.

    Log files successfully archived are generally deleted, unless "dry_run"
    is set in the script, in which case they are moved to a "deleted" folder
    [operations]/history_logs/deleted/.    

ENHANCEMENT:

    Presently, if a user extracts logs from a <Week-Block>.tar.gz file, and
    leaves it in the history_logs directory, a subsequent run of log_redux.sh
    will result in the log being added again.  This can be avoided by taking
    a "tar -tvf" isting of any existing archive to which files may be added,
    and skipping any that are already present.

