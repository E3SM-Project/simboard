import pytest
from sqlalchemy.exc import IntegrityError

from app.features.machine.models import Machine

pytestmark = pytest.mark.asyncio


class TestMachineModelCreateAllSchema:
    async def test_create_all_schema_enforces_case_insensitive_uniqueness(
        self, async_db
    ) -> None:
        async_db.add(
            Machine(
                name="machine constraint",
                site="Site A",
                architecture="x86_64",
                scheduler="SLURM",
                gpu=False,
            )
        )
        await async_db.commit()

        async_db.add(
            Machine(
                name="MACHINE CONSTRAINT",
                site="Site B",
                architecture="ARM",
                scheduler="PBS",
                gpu=False,
            )
        )

        with pytest.raises(IntegrityError):
            await async_db.commit()

        await async_db.rollback()

    async def test_create_all_schema_enforces_lowercase_machine_names(
        self, async_db
    ) -> None:
        async_db.add(
            Machine(
                name="Mixed-Case-Machine",
                site="Site Mixed",
                architecture="x86_64",
                scheduler="SLURM",
                gpu=False,
            )
        )

        with pytest.raises(IntegrityError):
            await async_db.commit()

        await async_db.rollback()
