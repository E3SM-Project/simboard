import uuid

import pytest
from pydantic import ValidationError

from app.features.user.schemas import ServiceAccountCreate, ServiceAccountResponse


class TestServiceAccountCreate:
    def test_valid_service_account_create(self) -> None:
        payload = ServiceAccountCreate(service_name="nersc-ingestor")

        assert payload.service_name == "nersc-ingestor"

    def test_missing_service_name(self) -> None:
        with pytest.raises(ValidationError):
            ServiceAccountCreate.model_validate({})


class TestServiceAccountResponse:
    def test_valid_service_account_response(self) -> None:
        response = ServiceAccountResponse(
            id=uuid.uuid4(),
            email="nersc-ingestor@example.com",
            role="service_account",
            created=True,
        )

        assert response.email == "nersc-ingestor@example.com"
        assert response.role == "service_account"
        assert response.created is True

    def test_from_attributes(self) -> None:
        class DummyServiceAccount:
            def __init__(self, id, email, role, created):
                self.id = id
                self.email = email
                self.role = role
                self.created = created

        dummy = DummyServiceAccount(
            id=uuid.uuid4(),
            email="existing@example.com",
            role="service_account",
            created=False,
        )

        model = ServiceAccountResponse.model_validate(dummy)

        assert model.email == "existing@example.com"
        assert model.created is False

    def test_missing_required_field(self) -> None:
        with pytest.raises(ValidationError):
            ServiceAccountResponse.model_validate(
                {
                    "id": str(uuid.uuid4()),
                    "email": "valid@example.com",
                    "role": "service_account",
                }
            )
