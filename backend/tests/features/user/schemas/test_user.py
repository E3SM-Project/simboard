import uuid

import pytest
from pydantic import ValidationError

from app.features.user.schemas import (
    UserCreate,
    UserPreview,
    UserRead,
    UserUpdate,
)


class TestUserRead:
    def test_valid_user_read(self) -> None:
        user_id = uuid.uuid4()
        user = UserRead(
            id=user_id,
            email="user@example.com",
            is_active=True,
            is_superuser=False,
            is_verified=True,
            role="user",
        )

        assert user.id == user_id
        assert user.email == "user@example.com"
        assert user.role == "user"
        assert user.is_active
        assert user.is_verified
        assert not user.is_superuser

    def test_invalid_email_user_read(self) -> None:
        with pytest.raises(ValidationError):
            UserRead(
                id=uuid.uuid4(),
                email="invalid-email",
                is_active=True,
                is_superuser=False,
                is_verified=True,
                role="user",
            )


class TestUserCreate:
    def test_defaults(self) -> None:
        user = UserCreate(email="new@example.com")

        assert user.role == "user"
        assert user.password is None

    def test_with_password(self) -> None:
        user = UserCreate(email="new@example.com", password="secret", role="admin")

        assert user.password == "secret"
        assert user.role == "admin"

    def test_invalid_email(self) -> None:
        with pytest.raises(ValidationError):
            UserCreate(email="not-an-email")


class TestUserUpdate:
    def test_partial_update(self) -> None:
        update = UserUpdate(email="updated@example.com")

        assert update.email == "updated@example.com"
        assert update.role is None
        assert update.password is None

    def test_role_change(self) -> None:
        update = UserUpdate(role="admin")

        assert update.role == "admin"


class TestUserPreview:
    def test_valid_preview(self) -> None:
        preview = UserPreview(
            id=uuid.uuid4(),
            email="preview@example.com",
            role="user",
            full_name="Preview User",
        )

        assert isinstance(preview.id, uuid.UUID)
        assert isinstance(preview.email, str)
        assert preview.email == "preview@example.com"
        assert preview.role == "user"
        assert preview.full_name == "Preview User"

    def test_from_attributes(self) -> None:
        class DummyUser:
            def __init__(self, id, email, role, full_name):
                self.id = id
                self.email = email
                self.role = role
                self.full_name = full_name

        dummy = DummyUser(uuid.uuid4(), "orm@example.com", "admin", "ORM User")
        preview = UserPreview.model_validate(dummy)

        assert preview.email == "orm@example.com"
        assert preview.role == "admin"
        assert preview.full_name == "ORM User"

    def test_invalid_email(self) -> None:
        with pytest.raises(ValidationError):
            UserPreview(
                id=uuid.uuid4(),
                email="invalid-email",
                role="user",
            )
