from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.common.dependencies import get_database_session
from app.core.database import transaction
from app.features.site.models import Site
from app.features.site.schemas import SiteCreate, SiteOut

router = APIRouter(prefix="/sites", tags=["Sites"])


@router.post("", response_model=SiteOut, status_code=status.HTTP_201_CREATED)
def create_site(payload: SiteCreate, db: Session = Depends(get_database_session)):
    """Create a site with a unique name."""
    if db.query(Site).filter(Site.name == payload.name).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Site with this name already exists",
        )

    new_site = Site(**payload.model_dump())
    with transaction(db):
        db.add(new_site)
        db.flush()

    return new_site


@router.get("", response_model=list[SiteOut])
def list_sites(db: Session = Depends(get_database_session)):
    """List sites ordered by name."""
    return db.query(Site).order_by(Site.name.asc()).all()


@router.get("/{site_id}", response_model=SiteOut)
def get_site(site_id: UUID, db: Session = Depends(get_database_session)):
    """Retrieve a site by ID."""
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    return site
