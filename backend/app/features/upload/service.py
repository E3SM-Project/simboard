import tempfile
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.machine.service import MachineService
from app.features.simulation.repository import SimulationRepository
from app.features.upload import ingest
from app.features.upload.schemas import UploadResponse
from app.models.user import User


class UploadService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.sim_repo = SimulationRepository(session)
        self.machine_service = MachineService(session)

    async def ingest(self, archive: UploadFile, uploaded_by: User) -> UploadResponse:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / archive.filename
            archive_path.write_bytes(await archive.read())

            parsed_result = ingest.ingest_archive(archive_path)

        if parsed_result.errors:
            return UploadResponse(
                status="failed",
                errors=parsed_result.errors,
                warnings=parsed_result.warnings,
            )

        parsed = parsed_result.experiments[0]  # one experiment for now

        machine_id = await self.machine_service.resolve(parsed.machine_name)

        existing = await self.sim_repo.find_by_identity(
            case_name=parsed.case_name,
            machine_id=machine_id,
            simulation_start_date=parsed.simulation_start_date,
        )

        if existing:
            return UploadResponse(
                status="existing",
                simulation_id=existing.id,
                warnings=parsed_result.warnings,
            )

        sim_create = ingest.to_simulation_create(
            parsed=parsed,
            uploaded_by=uploaded_by,
            machine_id=machine_id,
        )

        simulation = await self.sim_repo.create(sim_create)

        return UploadResponse(
            status="created",
            simulation_id=simulation.id,
            warnings=parsed_result.warnings,
        )
