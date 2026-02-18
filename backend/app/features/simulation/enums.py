from enum import StrEnum


class SimulationStatus(StrEnum):
    """Enumeration of possible simulation statuses."""

    UNKNOWN = "unknown"
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    FAILED = "failed"
    COMPLETED = "completed"


class SimulationType(StrEnum):
    """Enumeration of possible simulation types."""

    UNKNOWN = "unknown"
    PRODUCTION = "production"
    EXPERIMENTAL = "experimental"
    TEST = "test"


class ArtifactKind(StrEnum):
    """Enumeration of possible artifact types."""

    OUTPUT = "output"
    ARCHIVE = "archive"
    RUN_SCRIPT = "run_script"
    POSTPROCESS_SCRIPT = "postprocessing_script"


class ExternalLinkKind(StrEnum):
    """Enumeration of possible external link types."""

    DIAGNOSTIC = "diagnostic"
    PERFORMANCE = "performance"
    DOCS = "docs"
    OTHER = "other"


class ExperimentType(StrEnum):
    # --- DECK core experiments ---
    PI_CONTROL = "piControl"
    HISTORICAL = "historical"
    AMIP = "amip"
    ABRUPT_4XCO2 = "abrupt-4xCO2"
    ONE_PCT_CO2 = "1pctCO2"

    # --- ScenarioMIP (SSPs) ---
    SSP119 = "ssp119"
    SSP126 = "ssp126"
    SSP245 = "ssp245"
    SSP370 = "ssp370"
    SSP585 = "ssp585"

    # --- ESM variants ---
    ESM_HIST = "esm-hist"
    ESM_PICONTROL = "esm-piControl"
