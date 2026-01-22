# router.py

from datetime import datetime

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.features.simulation.schemas import SimulationCreate, SimulationStatus

from .ingest import IngestionError, ingest_simulation
from .schemas import UploadResponse
from .service import handle_file_upload

router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("/file", response_model=UploadResponse)
async def upload_file(file: UploadFile = File()):
    try:
        file_location = handle_file_upload(file)
        return UploadResponse(
            filename=file.filename,
            status="success",
            message=f"File saved to {file_location}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/ingest", response_model=dict)
async def upload_and_ingest(file: UploadFile = File()):
    """
    Upload a simulation archive and trigger automated ingestion.
    """
    try:
        file_location = handle_file_upload(file)
        # For demo, use a placeholder user string
        upload_user = "simboard_user"
        results = ingest_simulation(file_location, upload_user)

        # Map results to SimBoard schema (SimulationCreate) for each experiment
        mapped = []
        for result in results:
            if not result["success"]:
                mapped.append(result)
                continue

            data = result["data"]

            # Machine lookup: for demo, just pass machine name string
            machine_name = data.get("machine")
            # TODO: Replace with actual UUID lookup from DB
            machine_id = machine_name  # Placeholder

            # Parse git_tag and git_commit_hash from version string
            version = data.get("version", "")
            git_tag, git_commit_hash = None, None
            if version:
                parts = version.split("-")
                if len(parts) >= 3:
                    git_tag = "-".join(parts[:-2])
                    git_commit_hash = parts[-1].replace("g", "")

            sim = SimulationCreate(
                name=data.get("case", ""),
                case_name=data.get("case", ""),
                description=None,
                compset=data.get("compset", ""),
                compset_alias=data.get("long_compset", ""),
                grid_name=data.get("res", ""),
                grid_resolution=data.get("long_res", ""),
                parent_simulation_id=None,
                simulation_type="e3sm_simulation",
                status=SimulationStatus.COMPLETED,
                campaign_id=None,
                experiment_type_id=None,
                initialization_type=data.get("run_type", ""),
                group_name=data.get("case_group"),
                machine_id=machine_id,
                simulation_start_date=data.get("exp_date", datetime.now()),
                simulation_end_date=None,
                run_start_date=None,
                run_end_date=None,
                compiler=data.get("compiler"),
                key_features=None,
                known_issues=None,
                notes_markdown=None,
                git_repository_url=None,
                git_branch=None,
                git_tag=git_tag,
                git_commit_hash=git_commit_hash,
                created_by=None,
                last_updated_by=None,
                extra={
                    "lid": data.get("lid"),
                    "user": data.get("user"),
                    "mpilib": data.get("mpilib"),
                },
                artifacts=[],
                links=[],
            )

            mapped.append(
                {"simulation": sim.model_dump(), "warnings": result["warnings"]}
            )

        return {"results": mapped}

    except IngestionError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
