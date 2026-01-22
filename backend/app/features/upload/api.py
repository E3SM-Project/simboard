from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database_async import get_async_session
from app.features.upload.schemas import UploadResponse
from app.features.upload.service import UploadService
from app.features.user.manager import current_active_user
from app.features.user.models import User

router = APIRouter(prefix="/upload", tags=["Upload"])


@router.post("", response_model=UploadResponse)
async def upload_simulation(
    archive: UploadFile,
    current_user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    service = UploadService(session=session)

    try:
        return await service.ingest(archive=archive, uploaded_by=current_user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
