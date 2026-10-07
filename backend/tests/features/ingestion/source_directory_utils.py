"""Source-metadata stubs for runner tests using empty execution directories."""

from app.features.ingestion.schemas import SourceDirectoryObservation
from app.scripts.ingestion import archive_source_directories as source_module


def stub_source_directory_persistence(monkeypatch):
    def observe(case_path, execution_dirname, config, hpc_username=None):
        return SourceDirectoryObservation(
            case_name="parsed-case",
            hpc_username=hpc_username or "test-user",
            execution_id=execution_dirname,
            kind=config.scan_mode,
            case_path=str(case_path),
            execution_path=str(case_path / execution_dirname),
        )

    monkeypatch.setattr(source_module, "_observe_source_directory", observe)
    monkeypatch.setattr(
        source_module,
        "_post_source_directories_request",
        lambda *args, **kwargs: {"status_code": 200, "body": {}},
    )
