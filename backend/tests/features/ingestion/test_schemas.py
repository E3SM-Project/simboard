import pytest
from pydantic import ValidationError

from app.features.ingestion.schemas import IngestArchiveRequest, IngestArchiveResponse


class TestIngestionSchemas:
    def test_ingest_archive_request_valid(self) -> None:
        payload = IngestArchiveRequest(
            archive_path="/tmp/archive.zip", output_dir="/tmp/extracted"
        )

        assert payload.archive_path == "/tmp/archive.zip"
        assert payload.output_dir == "/tmp/extracted"

    def test_ingest_archive_request_missing_fields(self) -> None:
        with pytest.raises(ValidationError):
            IngestArchiveRequest(output_dir="/tmp/extracted")  # type: ignore[call-arg]

    def test_ingest_archive_response_valid(self) -> None:
        payload = IngestArchiveResponse(
            created_count=1, duplicate_count=0, simulations=[], errors=[]
        )

        assert payload.created_count == 1
        assert payload.duplicate_count == 0
        assert payload.simulations == []
        assert payload.simulations == []
