from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.version import API_BASE
from app.features.site.api import create_site, get_site, list_sites
from app.features.site.models import Site
from app.features.site.schemas import SiteCreate


def test_create_site_function_and_endpoint(db: Session, client) -> None:
    created = create_site(SiteCreate(name="ZZ Test Site"), db)
    assert created.name == "ZZ Test Site"

    response = client.post(f"{API_BASE}/sites", json={"name": "ZZZ Test Site"})
    assert response.status_code == 201
    assert response.json()["name"] == "ZZZ Test Site"


def test_create_site_rejects_duplicate_name(db: Session, client) -> None:
    db.add(Site(name="Duplicate Site"))
    db.commit()

    with pytest.raises(HTTPException, match="Site with this name already exists"):
        create_site(SiteCreate(name="Duplicate Site"), db)

    response = client.post(f"{API_BASE}/sites", json={"name": "Duplicate Site"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Site with this name already exists"


def test_list_sites_is_ordered(db: Session, client) -> None:
    db.add_all([Site(name="ZZ Site"), Site(name="AA Site")])
    db.commit()

    names = [site.name for site in list_sites(db)]
    assert names == sorted(names)

    response = client.get(f"{API_BASE}/sites")
    assert response.status_code == 200
    endpoint_names = [site["name"] for site in response.json()]
    assert endpoint_names == sorted(endpoint_names)


def test_get_site_and_missing_site(db: Session, client) -> None:
    site = Site(name="Lookup Site")
    db.add(site)
    db.commit()

    assert get_site(site.id, db).id == site.id
    response = client.get(f"{API_BASE}/sites/{site.id}")
    assert response.status_code == 200
    assert response.json()["id"] == str(site.id)

    missing_id = uuid4()
    with pytest.raises(HTTPException, match="Site not found"):
        get_site(missing_id, db)
    assert client.get(f"{API_BASE}/sites/{missing_id}").status_code == 404
