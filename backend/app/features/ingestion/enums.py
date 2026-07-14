from enum import StrEnum


class IngestionStatus(StrEnum):
    """Status values for ingestion audit records."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class IngestionSourceType(StrEnum):
    """Source types for ingestion audit records."""

    HPC_PATH = "hpc_path"
    HPC_UPLOAD = "hpc_upload"
    BROWSER_UPLOAD = "browser_upload"


class ExecutionDiscoveryOutcome(StrEnum):
    """Immutable outcome of validating one discovered execution."""

    ACCEPTED = "accepted"
    REJECTED_INCOMPLETE = "rejected_incomplete"
    REJECTED_INVALID = "rejected_invalid"
