import hashlib
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session, selectinload

from app.common.dependencies import get_database_session
from app.features.catalog.enums import ExternalLinkKind
from app.features.catalog.models import Case
from app.features.diagnostics import compare
from app.features.diagnostics.catalog import read_catalog_cached
from app.features.diagnostics.discovery import discover_runs_cached
from app.features.diagnostics.e3sm_diags import IMAGE_WIDTH
from app.features.diagnostics.plots import Catalog, Plot
from app.features.diagnostics.schemas import (
    CaseDiagnosticsOut,
    ComparedPlotOut,
    CompareOut,
    CompareRequest,
    CompareRunOut,
    DiagnosticsSourceOut,
    GroupOut,
    PanelOut,
    SetDetailOut,
    SetSummaryOut,
)

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


@router.post("/diagnostics/compare", response_model=CompareOut)
def compare_runs(payload: CompareRequest, request: Request, response: Response):
    """Line up the plots several diagnostics runs published.

    Returns every plot set the runs share and, for one of them (``set``, or
    the first), its variables with each run's image path. Plots only some
    runs published are left out and counted in ``missing``.
    """
    with ThreadPoolExecutor(max_workers=len(payload.runs)) as pool:
        catalogs = list(
            pool.map(lambda run: read_catalog_cached(run.url, run.label), payload.runs)
        )

    shared = compare.shared_sets(catalogs)
    active = next(
        (s for s in shared if s.name == payload.set), shared[0] if shared else None
    )
    result = CompareOut(
        runs=[
            CompareRunOut(
                url=c.url,
                label=run.label,
                tool=c.tool,
                image_base_url=c.image_base_url,
                partial=c.partial,
                error=c.error,
            )
            for run, c in zip(payload.runs, catalogs, strict=True)
        ],
        sets=[_summary(s) for s in shared],
        set=_detail(active, catalogs) if active else None,
    )

    # Catalogs change rarely; let the browser revalidate instead of re-reading.
    etag = f'"{hashlib.sha256(result.model_dump_json().encode()).hexdigest()[:32]}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    response.headers["ETag"] = etag
    return result


def _summary(shared: compare.SharedSet) -> SetSummaryOut:
    return SetSummaryOut(
        name=shared.name,
        title=shared.title,
        plot_count=len(shared.plots),
        missing=shared.missing,
    )


def _detail(shared: compare.SharedSet, catalogs: list[Catalog]) -> SetDetailOut:
    tool = next(c.tool for c in catalogs if c.error is None)
    panels = compare.panels(tool, shared.name)

    def compared(plot: Plot) -> ComparedPlotOut:
        # One entry per requested run; None where a run could not be read.
        per_run = [compare.find_plot(c, shared.name, plot.key) for c in catalogs]
        return ComparedPlotOut(
            key=plot.key,
            season=plot.season,
            region=plot.region,
            single_panel=plot.single_panel,
            paths=[p.path if p else None for p in per_run],
            references=[p.reference if p else None for p in per_run],
        )

    return SetDetailOut(
        **_summary(shared).model_dump(),
        image_width=IMAGE_WIDTH if panels else None,
        panels={view: PanelOut(**box._asdict()) for view, box in panels.items()},
        groups=[
            GroupOut(
                id=group.id,
                title=group.title,
                reference=group.reference,
                plots=[compared(plot) for plot in group.plots],
            )
            for group in compare.group_plots(shared.plots)
        ],
    )
