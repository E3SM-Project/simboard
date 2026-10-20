#!/usr/bin/env python3

import gzip
import re
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

dry_run = True

timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
the_directory = Path.cwd() / "history_logs"
list_file = Path.cwd() / f"THE_LIST-{timestamp}"

filename_pattern = re.compile(r"-([0-9]{8})_[0-9]{6}(?:-[0-9]+)?\.log$")


def extract_date(filename):
    match = filename_pattern.search(filename)
    return match.group(1) if match else None


def archive_members(tar_path, directory, filenames, append, dry_run=False):
    mode = "a" if append else "w"

    # Existing names in the archive. Tar append mode cannot replace entries.
    existing_names = set()

    if append and tar_path.exists():
        with tarfile.open(tar_path, "r") as archive:
            existing_names = {
                member.name
                for member in archive.getmembers()
            }

    added = []
    skipped = []

    if dry_run:
        for filename in filenames:
            if filename in existing_names:
                skipped.append(filename)
            else:
                added.append(filename)
                existing_names.add(filename)
    else:
        with tarfile.open(tar_path, mode) as archive:
            for filename in filenames:
                source = directory / filename

                if filename in existing_names:
                    skipped.append(filename)
                    continue

                archive.add(source, arcname=filename)
                existing_names.add(filename)
                added.append(filename)

    for filename in skipped:
        print(f"Skipping duplicate archive member: {filename}")

    return added, skipped


def gzip_file(path):
    gz_path = Path(f"{path}.gz")

    with path.open("rb") as source, gzip.open(gz_path, "wb") as destination:
        shutil.copyfileobj(source, destination)

    path.unlink()

# To be launched only in the directory "simboard/operations", wherein a
# subdirectory "raw_logs", and "history_logs" are expected to hold recent
# log_files and the consequent weekly tar.gz files create by this reduction.
#
# The bifurcation "raw_logs" versus "history_logs" is only to allow "raw_logs"
# to remain untouched by log_reduction for possible summarization processing.
#
# When log_redux.py runs, any log_files in "history_logs" are partitioned
# into "Week_Blocks" (Sunday 00:00 to Saturday 23:59), and corresponding 
# "<week>".tar-gz archives are created or updated from the logs present.
#
# Ordinarily, the logs themselves are deleted.  But for testing purposes,
# "dry_run" will simply move the ogs to a subordinate "deleted" folder.
#
# in selected files are extracted from these tar files for inspection, and
# are inadvertently left in the directory, log_redux will NOT add them
# to the tar files (no duplicates allowed) but will be "deleted" along
# with all other "*.log" logs found.

def main():
    # Equivalent to find, sort, and awk.
    filenames = [
        path.name
        for path in the_directory.iterdir()
        if path.is_file()
    ]

    filenames.sort(
        key=lambda name: name[3:11] if len(name) >= 11 else name
    )

    filenames = [
        name for name in filenames
        if filename_pattern.search(name)
    ]

    list_file.write_text("\n".join(filenames) + ("\n" if filenames else ""))

    while list_file.exists() and list_file.stat().st_size > 0:
        remaining = list_file.read_text().splitlines()
        oldest = remaining[0]

        file_date_text = extract_date(oldest)
        if file_date_text is None:
            print(
                f"Skipping unrecognized filename: {oldest}",
                file=sys.stderr,
            )
            list_file.write_text("\n".join(remaining[1:]) + "\n")
            continue

        file_date = datetime.strptime(file_date_text, "%Y%m%d").date()

        # Python weekday: Monday=0, Sunday=6.
        sunday = file_date - timedelta(days=(file_date.weekday() + 1) % 7)
        saturday = sunday + timedelta(days=6)

        sunday_text = sunday.strftime("%Y%m%d")
        saturday_text = saturday.strftime("%Y%m%d")

        print(
            f"DEBUG_LOG_REDUX: (sun,sat) = "
            f"({sunday_text},{saturday_text})"
        )

        week_files = []
        for filename in remaining:
            date_text = extract_date(filename)
            if date_text and sunday_text <= date_text <= saturday_text:
                week_files.append(filename)

        if not week_files:
            print(
                f"ERROR: No files found for {oldest}",
                file=sys.stderr,
            )
            return 1

        week_file = Path(f"{list_file}.week")
        week_file.write_text("\n".join(week_files) + "\n")

        print(
            f"DEBUG_LOG_REDUX: calling mapfile with {week_file}"
        )

        archive_base = f"{sunday_text}-{saturday_text}"
        tar_archive = the_directory / f"{archive_base}.tar"
        gz_archive = Path(f"{tar_archive}.gz")

        if gz_archive.is_file() and not tar_archive.is_file():
            with gzip.open(gz_archive, "rb") as source, tar_archive.open(
                "wb"
            ) as destination:
                shutil.copyfileobj(source, destination)
            gz_archive.unlink()

        elif gz_archive.is_file() and tar_archive.is_file():
            print(
                f"Both archives exist: {tar_archive} and {gz_archive}",
                file=sys.stderr,
            )
            return 1

        added, skipped = archive_members(
            tar_archive,
            the_directory,
            week_files,
            append=tar_archive.exists(),
            dry_run=dry_run,
        )
        print(f"Added {len(added)} file(s), skipped {len(skipped)} duplicate(s)")

        processed = set(week_files)
        new_remaining = [
            filename for filename in remaining
            if filename not in processed
        ]
        list_file.write_text(
            "\n".join(new_remaining) + ("\n" if new_remaining else "")
        )

        week_file.unlink(missing_ok=True)

        # Move or delete source files only after the tar operation succeeds.
        if dry_run:
            deleted_directory = the_directory / "deleted"
            deleted_directory.mkdir(parents=True, exist_ok=True)

            for filename in week_files:
                shutil.move(
                    str(the_directory / filename),
                    str(deleted_directory / filename),
                )
        else:
            for filename in week_files:
                (the_directory / filename).unlink(missing_ok=True)

        if not dry_run:
            gzip_file(tar_archive)

        print(
            f"Processed {sunday_text} through {saturday_text}: "
            f"{gz_archive}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())

