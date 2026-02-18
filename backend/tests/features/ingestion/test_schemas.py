from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.features.ingestion.schemas import (
    IngestFromPathRequest,
    IngestionRead,
    IngestionResponse,
    IngestionStatus,
)


class TestIngestionSchemas:
    def test_ingest_archive_request_valid(self) -> None:
        payload = IngestFromPathRequest(
            archive_path="/tmp/archive.zip", machine_name="chrysalis"
        )

        assert payload.archive_path == "/tmp/archive.zip"
        assert payload.machine_name == "chrysalis"

    def test_ingest_archive_request_missing_fields(self) -> None:
        with pytest.raises(ValidationError):
            IngestFromPathRequest()  # type: ignore[call-arg]

    def test_ingest_archive_response_valid(self) -> None:
        payload = IngestionResponse(
            created_count=1, duplicate_count=0, simulations=[], errors=[]
        )

        assert payload.created_count == 1
        assert payload.duplicate_count == 0
        assert payload.simulations == []
        assert payload.errors == []


class TestIngestionStatus:
    def test_status_enum_values(self) -> None:
        assert IngestionStatus.SUCCESS.value == "success"
        assert IngestionStatus.PARTIAL.value == "partial"
        assert IngestionStatus.FAILED.value == "failed"

    def test_status_enum_membership(self) -> None:
        assert "success" in [s.value for s in IngestionStatus]
        assert "partial" in [s.value for s in IngestionStatus]
        assert "failed" in [s.value for s in IngestionStatus]


class TestIngestionRead:
    def test_ingestion_read_valid(self) -> None:
        ingestion_id = uuid4()
        user_id = uuid4()
        machine_id = uuid4()
        now = datetime.now(timezone.utc)

        payload = IngestionRead(
            id=ingestion_id,
            sourceType="upload",
            sourceReference="test.tar.gz",
            machine_id=machine_id,
            triggeredBy=user_id,
            createdAt=now,
            status="success",
            createdCount=5,
            duplicateCount=2,
            errorCount=0,
            archiveSha256="abc123def456",
        )

        assert payload.id == ingestion_id
        assert payload.sourceType == "upload"
        assert payload.sourceReference == "test.tar.gz"
        assert payload.machine_id == machine_id
        assert payload.triggeredBy == user_id
        assert payload.createdAt == now
        assert payload.status == "success"
        assert payload.createdCount == 5
        assert payload.duplicateCount == 2
        assert payload.errorCount == 0
        assert payload.archiveSha256 == "abc123def456"

    def test_ingestion_read_optional_sha256(self) -> None:
        ingestion_id = uuid4()
        user_id = uuid4()
        machine_id = uuid4()
        now = datetime.now(timezone.utc)

        payload = IngestionRead(
            id=ingestion_id,
            sourceType="path",
            sourceReference="/tmp/archive.zip",
            machine_id=machine_id,
            triggeredBy=user_id,
            createdAt=now,
            status="partial",
            createdCount=3,
            duplicateCount=1,
            errorCount=2,
            archiveSha256=None,
        )

        assert payload.archiveSha256 is None

    def test_ingestion_read_missing_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            IngestionRead(  # type: ignore[call-arg]
                sourceType="upload",
                sourceReference="test.tar.gz",
            )
