from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from app.common.dependencies import get_database_session
from app.features.catalog.enums import ExternalLinkKind
from app.features.catalog.models import Case
from app.features.diagnostics.discovery import discover_runs_cached
from app.features.diagnostics.schemas import CaseDiagnosticsOut, DiagnosticsSourceOut

router = APIRouter(tags=["Diagnostics"])


@router.get("/cases/{case_id}/diagnostics/runs", response_model=CaseDiagnosticsOut)
def get_case_diagnostics_runs(
    case_id: UUID, db: Session = Depends(get_database_session)
) -> CaseDiagnosticsOut:
    """List the E3SM Diags and MPAS-Analysis runs published for a case.

    Each ``diagnostic`` link on the case is the root of its zppy output; the
    runs beneath it are read from the archive's directory listings. A root
    that cannot be read is reported with an ``error`` rather than failing.
    """
    case = (
        db.query(Case)
        .options(selectinload(Case.links))
        .filter(Case.id == case_id)
        .one_or_none()
    )
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    sources = []
    for link in case.links:
        if link.kind != ExternalLinkKind.DIAGNOSTIC:
            continue
        found = discover_runs_cached(link.url)
        sources.append(
            DiagnosticsSourceOut.model_validate(
                {**vars(found), "runs": list(found.runs), "label": link.label}
            )
        )

    return CaseDiagnosticsOut(case_id=case.id, case_name=case.name, sources=sources)
