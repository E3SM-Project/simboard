"""Scheduler-agnostic HPC archive ingestion entrypoint.

This module is the stable entrypoint for site wrappers such as Jenkins or cron
jobs. The current implementation delegates to the existing NERSC archive
ingestor so Perlmutter behavior remains unchanged while non-NERSC wrappers move
to a shared command name.
"""

from __future__ import annotations

from app.scripts.ingestion.nersc_archive_ingestor import main

if __name__ == "__main__":
    raise SystemExit(main())
