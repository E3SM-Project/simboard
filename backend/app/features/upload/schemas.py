from typing import List, Literal
from uuid import UUID

from app.common.schemas.base import CamelInBaseModel


class UploadResponse(CamelInBaseModel):
    status: Literal["created", "existing", "failed"]
    simulation_id: UUID | None = None
    warnings: List[str] = []
    errors: List[str] = []
