"""Tests for the Ingestion audit model."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.features.ingestion.models import Ingestion, IngestionSourceType
from app.features.machine.models import Machine


class TestIngestionModel:
    def test_create_ingestion_record(self, db: Session, normal_user_sync: dict) -> None:
        """Test creating a basic ingestion audit record."""
        user_id = normal_user_sync["id"]
        machine = db.query(Machine).first()
        assert machine is not None

        ingestion = Ingestion(
            source_type=IngestionSourceType.HPC_UPLOAD.value,
            source_reference="test_archive.tar.gz",
            machine_id=machine.id,
            triggered_by=user_id,
            created_at=datetime.now(timezone.utc),
            status="success",
            created_count=5,
            duplicate_count=2,
            error_count=0,
            archive_sha256="abc123def456",
        )

        db.add(ingestion)
        db.commit()
        db.refresh(ingestion)

        assert ingestion.id is not None
        assert str(ingestion.source_type) == "hpc_upload"
        assert ingestion.source_reference == "test_archive.tar.gz"
        assert ingestion.triggered_by == user_id
        assert ingestion.status == "success"
        assert ingestion.created_count == 5
        assert ingestion.duplicate_count == 2
        assert ingestion.error_count == 0
        assert ingestion.archive_sha256 == "abc123def456"

    def test_create_ingestion_without_sha256(
        self, db: Session, normal_user_sync: dict
    ) -> None:
        """Test creating ingestion record without SHA256 hash (path-based)."""
        user_id = normal_user_sync["id"]
        machine = db.query(Machine).first()
        assert machine is not None

        ingestion = Ingestion(
            source_type=IngestionSourceType.HPC_PATH.value,
            source_reference="/tmp/test_archive.zip",
            machine_id=machine.id,
            triggered_by=user_id,
            created_at=datetime.now(timezone.utc),
            status="partial",
            created_count=3,
            duplicate_count=1,
            error_count=2,
            archive_sha256=None,
        )

        db.add(ingestion)
        db.commit()
        db.refresh(ingestion)

        assert ingestion.id is not None
        assert str(ingestion.source_type) == "hpc_path"
        assert ingestion.archive_sha256 is None

    def test_ingestion_user_relationship(
        self, db: Session, normal_user_sync: dict
    ) -> None:
        """Test the relationship between Ingestion and User."""
        user_id = normal_user_sync["id"]
        machine = db.query(Machine).first()
        assert machine is not None

        ingestion = Ingestion(
            source_type=IngestionSourceType.HPC_UPLOAD.value,
            source_reference="test.tar.gz",
            machine_id=machine.id,
            triggered_by=user_id,
            created_at=datetime.now(timezone.utc),
            status="success",
            created_count=1,
            duplicate_count=0,
            error_count=0,
        )

        db.add(ingestion)
        db.commit()
        db.refresh(ingestion)

        # Access the user relationship
        assert ingestion.user is not None
        assert ingestion.user.id == user_id
        assert ingestion.user.email == normal_user_sync["email"]

    def test_ingestion_default_counts(
        self, db: Session, normal_user_sync: dict
    ) -> None:
        """Test that count fields have proper defaults."""
        user_id = normal_user_sync["id"]
        machine = db.query(Machine).first()
        assert machine is not None

        ingestion = Ingestion(
            source_type=IngestionSourceType.HPC_UPLOAD.value,
            source_reference="test.tar.gz",
            machine_id=machine.id,
            triggered_by=user_id,
            created_at=datetime.now(timezone.utc),
            status="failed",
        )

        db.add(ingestion)
        db.commit()
        db.refresh(ingestion)

        # Defaults should be 0 for count fields
        assert ingestion.created_count == 0
        assert ingestion.duplicate_count == 0
        assert ingestion.error_count == 0

    def test_ingestion_repr(self, db: Session, normal_user_sync: dict) -> None:
        """Test the __repr__ method."""
        user_id = normal_user_sync["id"]
        machine = db.query(Machine).first()
        assert machine is not None

        ingestion = Ingestion(
            source_type=IngestionSourceType.HPC_UPLOAD.value,
            source_reference="test.tar.gz",
            machine_id=machine.id,
            triggered_by=user_id,
            created_at=datetime.now(timezone.utc),
            status="success",
            created_count=1,
            duplicate_count=0,
            error_count=0,
        )

        db.add(ingestion)
        db.commit()
        db.refresh(ingestion)

        repr_str = repr(ingestion)
        assert "Ingestion id=" in repr_str
        assert "source_type=<IngestionSourceType.HPC_UPLOAD: 'hpc_upload'>" in repr_str
        assert "status='success'" in repr_str

    def test_query_ingestions_by_user(
        self, db: Session, normal_user_sync: dict
    ) -> None:
        """Test querying ingestions by user."""
        user_id = normal_user_sync["id"]
        machine = db.query(Machine).first()
        assert machine is not None

        # Create multiple ingestion records
        for i in range(3):
            ingestion = Ingestion(
                source_type=IngestionSourceType.HPC_UPLOAD.value,
                source_reference=f"test{i}.tar.gz",
                machine_id=machine.id,
                triggered_by=user_id,
                created_at=datetime.now(timezone.utc),
                status="success",
                created_count=i + 1,
                duplicate_count=0,
                error_count=0,
            )
            db.add(ingestion)

        db.commit()

        # Query ingestions by user
        ingestions = db.query(Ingestion).filter(Ingestion.triggered_by == user_id).all()

        assert len(ingestions) == 3
        assert all(ing.triggered_by == user_id for ing in ingestions)

    def test_query_ingestions_by_status(
        self, db: Session, normal_user_sync: dict
    ) -> None:
        """Test querying ingestions by status."""
        user_id = normal_user_sync["id"]
        machine = db.query(Machine).first()
        assert machine is not None

        statuses = ["success", "partial", "failed"]
        for status in statuses:
            ingestion = Ingestion(
                source_type=IngestionSourceType.HPC_UPLOAD.value,
                source_reference=f"test_{status}.tar.gz",
                machine_id=machine.id,
                triggered_by=user_id,
                created_at=datetime.now(timezone.utc),
                status=status,
                created_count=1,
                duplicate_count=0,
                error_count=0 if status == "success" else 1,
            )
            db.add(ingestion)

        db.commit()

        # Query only successful ingestions
        successful = db.query(Ingestion).filter(Ingestion.status == "success").all()
        assert len(successful) == 1
        assert successful[0].status == "success"

        # Query failed ingestions
        failed = db.query(Ingestion).filter(Ingestion.status == "failed").all()
        assert len(failed) == 1
        assert failed[0].status == "failed"
