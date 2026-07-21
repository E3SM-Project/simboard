from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.features.site.schemas import SiteCreate, SiteOut


def test_site_create_accepts_name() -> None:
    assert SiteCreate(name="NERSC").name == "NERSC"


def test_site_create_requires_name() -> None:
    with pytest.raises(ValidationError):
        SiteCreate()


def test_site_out_serializes_camel_case_timestamps() -> None:
    now = datetime.now(UTC)
    site = SiteOut(id=uuid4(), name="NERSC", created_at=now, updated_at=now)

    assert site.model_dump(by_alias=True) == {
        "id": site.id,
        "name": "NERSC",
        "createdAt": now,
        "updatedAt": now,
    }
