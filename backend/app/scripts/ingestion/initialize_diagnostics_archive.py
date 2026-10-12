"""Optionally bootstrap a diagnostics root before the first zppy publishing run."""

import argparse
import grp
import os
from pathlib import Path

from app.scripts.ingestion.diagnostics_archives import DIAGNOSTICS_ARCHIVES_BY_MACHINE


def initialize_archive(machine: str) -> Path:
    """Create only a missing root, using the caller's UID and the site's group."""
    archive = DIAGNOSTICS_ARCHIVES_BY_MACHINE.get(machine)
    if archive is None:
        raise ValueError(f"Unknown diagnostics machine: {machine}")
    root = Path(archive.root)
    if root.is_dir():
        print(f"Archive already exists; unchanged: {root}")
        return root
    if root.exists() or root.is_symlink():
        raise ValueError(f"Archive path is not a directory: {root}")

    # Require the site's publishing parent; never create a local substitute tree.
    parent = root.parent.stat()
    gid = grp.getgrnam(archive.group).gr_gid if archive.group else parent.st_gid
    if gid not in {*os.getgroups(), os.getegid()}:
        raise ValueError(
            f"Current NERSC/site account must belong to archive group {gid}"
        )
    try:
        root.mkdir(mode=0o700)
    except FileExistsError:
        if not root.is_dir():
            raise
        print(f"Archive already exists; unchanged: {root}")
        return root
    try:
        os.chown(root, os.getuid(), gid)
        root.chmod(0o2775)
    except OSError:
        root.rmdir()
        raise
    print(f"Created archive: {root} (uid={os.getuid()}, gid={gid}, mode=2775)")
    return root


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--machine", default=os.environ.get("MACHINE_NAME"))
    args = parser.parse_args()
    if not args.machine:
        parser.error("Specify --machine or MACHINE_NAME")
    try:
        initialize_archive(args.machine)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"Cannot initialize diagnostics archive: {exc}\n")


if __name__ == "__main__":
    main()
