import uuid
from enum import Enum

from fastapi_users.db import (
    SQLAlchemyBaseOAuthAccountTableUUID,
    SQLAlchemyBaseUserTableUUID,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models.base import Base


class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"


class User(SQLAlchemyBaseUserTableUUID, Base):
    """User table with role-based access control."""

    __tablename__ = "users"

    # Override hashed_password to allow nullable for OAuth users
    hashed_password: Mapped[str | None] = mapped_column(
        String(length=1024), nullable=True
    )

    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole, name="user_role"),
        nullable=False,
        default=UserRole.USER,
    )

    # Relationship to linked OAuth accounts
    oauth_accounts: Mapped[list["OAuthAccount"]] = relationship(
        "OAuthAccount",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",  # Required for async loading
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} role={self.role}>"


class OAuthAccount(SQLAlchemyBaseOAuthAccountTableUUID, Base):
    """Generic OAuth account table supporting multiple providers."""

    __tablename__ = "oauth_accounts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="cascade"), nullable=False
    )

    user: Mapped["User"] = relationship(
        "User", back_populates="oauth_accounts", lazy="selectin"
    )
