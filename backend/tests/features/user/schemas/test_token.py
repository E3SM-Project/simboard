import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.features.user.schemas import ApiTokenCreate, ApiTokenCreated, ApiTokenRead


class TestApiTokenCreate:
    def test_valid_api_token_create(self) -> None:
        user_id = uuid.uuid4()
        expires_at = datetime(2030, 1, 1, tzinfo=timezone.utc)

        payload = ApiTokenCreate(
            name="hpc-ingestion",
            user_id=user_id,
            expires_at=expires_at,
        )

        assert payload.name == "hpc-ingestion"
        assert payload.user_id == user_id
        assert payload.expires_at == expires_at

    def test_default_expires_at_none(self) -> None:
        payload = ApiTokenCreate(
            name="hpc-ingestion",
            user_id=uuid.uuid4(),
        )

        assert payload.expires_at is None

    def test_invalid_user_id(self) -> None:
        with pytest.raises(ValidationError):
            ApiTokenCreate(name="hpc-ingestion", user_id="not-a-uuid")


class TestApiTokenCreated:
    def test_valid_api_token_created(self) -> None:
        token = ApiTokenCreated(
            id=uuid.uuid4(),
            name="hpc-ingestion",
            token="sbk_exampletoken",
            created_at=datetime.now(timezone.utc),
            expires_at=None,
        )

        assert token.name == "hpc-ingestion"
        assert token.token.startswith("sbk_")
        assert token.expires_at is None

    def test_from_attributes(self) -> None:
        class DummyToken:
            def __init__(self, id, name, token, created_at, expires_at):
                self.id = id
                self.name = name
                self.token = token
                self.created_at = created_at
                self.expires_at = expires_at

        dummy = DummyToken(
            id=uuid.uuid4(),
            name="ci-token",
            token="sbk_dummy",
            created_at=datetime.now(timezone.utc),
            expires_at=None,
        )

        model = ApiTokenCreated.model_validate(dummy)

        assert model.name == "ci-token"
        assert model.token == "sbk_dummy"


class TestApiTokenRead:
    def test_valid_api_token_read(self) -> None:
        token = ApiTokenRead(
            id=uuid.uuid4(),
            name="hpc-ingestion",
            user_id=uuid.uuid4(),
            created_at=datetime.now(timezone.utc),
            expires_at=None,
            revoked=False,
        )

        assert token.name == "hpc-ingestion"
        assert token.revoked is False

    def test_from_attributes(self) -> None:
        class DummyToken:
            def __init__(
                self,
                id,
                name,
                user_id,
                created_at,
                expires_at,
                revoked,
            ):
                self.id = id
                self.name = name
                self.user_id = user_id
                self.created_at = created_at
                self.expires_at = expires_at
                self.revoked = revoked

        dummy = DummyToken(
            id=uuid.uuid4(),
            name="ci-token",
            user_id=uuid.uuid4(),
            created_at=datetime.now(timezone.utc),
            expires_at=None,
            revoked=True,
        )

        model = ApiTokenRead.model_validate(dummy)

        assert model.name == "ci-token"
        assert model.revoked is True
