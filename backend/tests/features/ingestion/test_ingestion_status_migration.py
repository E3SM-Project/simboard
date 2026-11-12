"""Historical status repair changes only failed ingestions without errors."""

from importlib import import_module
from itertools import product

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from app.features.ingestion.enums import IngestionSourceType, IngestionStatus
from app.features.ingestion.models import Ingestion
from app.features.machine.models import Machine

migration = import_module(
    "migrations.versions.20261112_000000_fix_error_free_ingestion_status"
)


def test_ingestion_status_migration_repairs_only_failed_rows_without_errors(
    db, normal_user_sync
):
    machine = db.query(Machine).first()
    db.add_all(
        [
            Ingestion(
                source_type=IngestionSourceType.HPC_PATH,
                source_reference="/archive/status-repair",
                machine_id=machine.id,
                triggered_by=normal_user_sync["id"],
                status=status,
                created_count=created_count,
                duplicate_count=duplicate_count,
                error_count=error_count,
                archive_sha256="a" * 64,
                processed_execution_ids=["100.1-1"],
            )
            for status, created_count, duplicate_count, error_count in product(
                IngestionStatus, [0, 1], [0, 2], [0, 1]
            )
        ]
    )
    db.flush()
    connection = db.connection()
    query = text("SELECT * FROM ingestions ORDER BY id")
    before = connection.execute(query).mappings().all()
    expected = [
        {
            **row,
            "status": (
                "success"
                if row["status"] == "failed" and row["error_count"] == 0
                else row["status"]
            ),
        }
        for row in before
    ]

    with Operations.context(MigrationContext.configure(connection)):
        migration.upgrade()
        assert connection.execute(query).mappings().all() == expected
        migration.downgrade()
        assert connection.execute(query).mappings().all() == expected
        migration.upgrade()
        assert connection.execute(query).mappings().all() == expected
