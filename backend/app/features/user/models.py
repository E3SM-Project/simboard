import uuid
from datetime import datetime
from enum import Enum

from fastapi_users.db import (
    SQLAlchemyBaseOAuthAccountTableUUID,
    SQLAlchemyBaseUserTableUUID,
)
from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models.base import Base


class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"
    SERVICE_ACCOUNT = "service_account"


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

    # Relationship to API tokens
    api_tokens: Mapped[list["ApiToken"]] = relationship(
        "ApiToken",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
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


class ApiToken(Base):
    """API token for programmatic authentication (e.g., HPC ingestion)."""

    __tablename__ = "api_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)

    token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    revoked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    user: Mapped["User"] = relationship("User", back_populates="api_tokens")

    def __repr__(self) -> str:
        return f"<ApiToken id={self.id} name={self.name!r} user_id={self.user_id}>"
