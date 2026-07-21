from sqlalchemy.orm import Session

from app.features.site.models import Site


def get_or_create_site(db: Session, name: str = "Test Site") -> Site:
    """Return a named site for relationship-based test setup."""
    site = db.query(Site).filter(Site.name == name).one_or_none()
    if site is None:
        site = Site(name=name)
        db.add(site)
        db.flush()
    return site
