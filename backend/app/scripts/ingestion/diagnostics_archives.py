"""Reviewed diagnostics archive locations; never populated at scanner runtime."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DiagnosticsArchive:
    root: str
    public_base_url: str


# Refresh from Mache [web_portal] configuration in a reviewed change when sites move.
DIAGNOSTICS_ARCHIVES_BY_MACHINE: dict[str, DiagnosticsArchive] = {
    "perlmutter": DiagnosticsArchive(
        root="/global/cfs/cdirs/e3sm/diagnostic_output",
        public_base_url="https://portal.nersc.gov/cfs/e3sm/diagnostic_output",
    ),
    "pm": DiagnosticsArchive(
        root="/global/cfs/cdirs/e3sm/diagnostic_output",
        public_base_url="https://portal.nersc.gov/cfs/e3sm/diagnostic_output",
    ),
    "pm-cpu": DiagnosticsArchive(
        root="/global/cfs/cdirs/e3sm/diagnostic_output",
        public_base_url="https://portal.nersc.gov/cfs/e3sm/diagnostic_output",
    ),
    "pm-gpu": DiagnosticsArchive(
        root="/global/cfs/cdirs/e3sm/diagnostic_output",
        public_base_url="https://portal.nersc.gov/cfs/e3sm/diagnostic_output",
    ),
    "chrysalis": DiagnosticsArchive(
        root="/lcrc/group/e3sm/diagnostic_output",
        public_base_url="https://web.lcrc.anl.gov/public/e3sm/diagnostic_output",
    ),
}
