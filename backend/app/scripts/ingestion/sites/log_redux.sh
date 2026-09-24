#!/usr/bin/env bash
set -euo pipefail

dry_run=1

ts=`date -u +%Y%m%d_%H%M%S`
THE_DIRECTORY=`pwd`/history_logs
LIST_FILE="THE_LIST-$ts"

find "$THE_DIRECTORY" -maxdepth 1 -type f \
  -printf '%f\n' |
sort -t- -k4.1,4.8 |
awk 'match($0, /-[0-9]{8}_[0-9]{6}\.log$/) { print }' > "$LIST_FILE"

while [[ -s "$LIST_FILE" ]]; do
    oldest=$(head -n 1 "$LIST_FILE")

    # Extract YYYYMMDD from the filename.
    if [[ $oldest =~ -([0-9]{8})_[0-9]{6}\.log$ ]]; then
        file_date=${BASH_REMATCH[1]}
    else
        echo "Skipping unrecognized filename: $oldest" >&2
        sed -i '1d' "$LIST_FILE"
        continue
    fi

    # Calculate Sunday and following Saturday in UTC.
    sunday=$(date -u -d "$file_date -$(date -u -d "$file_date" +%w) days" +%Y%m%d)
    saturday=$(date -u -d "$sunday +6 days" +%Y%m%d)

    echo "DEBUG_LOG_REDUX: (sun,sat) = ($sunday,$saturday)"

    # Select files in this week, preserving the existing list order.
    awk -v start="$sunday" -v end="$saturday" '
        match($0, /-([0-9]{8})_[0-9]{6}\.log$/, m) &&
        m[1] >= start && m[1] <= end
    ' "$LIST_FILE" > "${LIST_FILE}.week"

    [[ -s "${LIST_FILE}.week" ]] || {
        echo "ERROR: No files found for $oldest" >&2
        exit 1
    }

    echo "DEBUG_LOG_REDUX: calling mapfile with ${LIST_FILE}.week"

    mapfile -t week_files < "${LIST_FILE}.week"

    # Prepare the archive for this week
    archive_base="${sunday}-${saturday}"
    tar_archive="${THE_DIRECTORY}/${archive_base}.tar"
    gz_archive="${tar_archive}.gz"

    if [[ -f "$gz_archive" && ! -f "$tar_archive" ]]; then
        gunzip -c "$gz_archive" > "$tar_archive" || exit 1
        rm -f "$gz_archive"
    elif [[ -f "$gz_archive" && -f "$tar_archive" ]]; then
        echo "Both archives exist: $tar_archive and $gz_archive" >&2
        exit 1
    fi

    # Append to an existing archive, or create a new one.
    if [[ ! -f "$tar_archive" ]]; then
        tar -C "$THE_DIRECTORY" -cf "$tar_archive" "${week_files[@]}"
    else
        tar -C "$THE_DIRECTORY" -rf "$tar_archive" "${week_files[@]}"
    fi

    # Remove processed files from the working list.
    awk '
        NR == FNR { processed[$0] = 1; next }
        !($0 in processed)
    ' "${LIST_FILE}.week" "$LIST_FILE" > "${LIST_FILE}.remaining"

    mv "${LIST_FILE}.remaining" "$LIST_FILE"
    rm -f "${LIST_FILE}.week"

    cd $THE_DIRECTORY

    # Move/Delete source files only after tar succeeds.
    if [[ $dry_run -eq 1 ]]; then
        mv -- "${week_files[@]}" ${THE_DIRECTORY}/deleted/
    else
        rm -f -- "${week_files[@]}"
    fi

    # Compress when you are finished adding files.
    gzip -f "$tar_archive"

    cd ..

    echo "Processed $sunday through $saturday: $gz_archive"
done

exit 0

