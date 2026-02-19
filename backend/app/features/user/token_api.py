"""API endpoints for managing API tokens."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.common.dependencies import get_database_session
from app.features.user.manager import current_active_user
from app.features.user.models import ApiToken, User, UserRole
from app.features.user.schemas import ApiTokenCreate, ApiTokenCreated, ApiTokenRead
from app.features.user.token_auth import generate_token

router = APIRouter(prefix="/tokens", tags=["API Tokens"])


@router.post(
    "",
    response_model=ApiTokenCreated,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "API token created successfully"},
        403: {"description": "Forbidden: only administrators can create tokens"},
    },
)
def create_api_token(
    payload: ApiTokenCreate,
    db: Session = Depends(get_database_session),
    user: User = Depends(current_active_user),
):
    """
    Create a new API token.

    Only administrators can create API tokens.
    The raw token is returned only once at creation time.

    Parameters
    ----------
    payload : ApiTokenCreate
        Token creation parameters
    db : Session
        Database session
    user : User
        Current authenticated user

    Returns
    -------
    ApiTokenCreated
        Created token with raw token value (returned only once)

    Raises
    ------
    HTTPException
        403 if user is not an administrator
    """
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can create API tokens",
        )

    # Generate token
    raw_token, token_hash = generate_token()

    # Create token record
    api_token = ApiToken(
        name=payload.name,
        token_hash=token_hash,
        user_id=payload.user_id,
        created_at=datetime.now(timezone.utc),
        expires_at=payload.expires_at,
        revoked=False,
    )

    db.add(api_token)
    db.commit()
    db.refresh(api_token)

    # Return created token with raw token (only time it's returned)
    return ApiTokenCreated(
        id=api_token.id,
        name=api_token.name,
        token=raw_token,  # Raw token returned only once
        created_at=api_token.created_at,
        expires_at=api_token.expires_at,
    )


@router.get(
    "",
    response_model=list[ApiTokenRead],
    responses={
        200: {"description": "List of API tokens"},
        403: {"description": "Forbidden: only administrators can list tokens"},
    },
)
def list_api_tokens(
    db: Session = Depends(get_database_session),
    user: User = Depends(current_active_user),
):
    """
    List all API tokens.

    Only administrators can list API tokens.

    Parameters
    ----------
    db : Session
        Database session
    user : User
        Current authenticated user

    Returns
    -------
    list[ApiTokenRead]
        List of API tokens (without raw token values)

    Raises
    ------
    HTTPException
        403 if user is not an administrator
    """
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can list API tokens",
        )

    tokens = db.query(ApiToken).all()
    return tokens


@router.delete(
    "/{token_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {"description": "Token revoked successfully"},
        403: {"description": "Forbidden: only administrators can revoke tokens"},
        404: {"description": "Token not found"},
    },
)
def revoke_api_token(
    token_id: UUID,
    db: Session = Depends(get_database_session),
    user: User = Depends(current_active_user),
):
    """
    Revoke an API token.

    Only administrators can revoke API tokens.
    Revoked tokens cannot be used for authentication.

    Parameters
    ----------
    token_id : UUID
        ID of the token to revoke
    db : Session
        Database session
    user : User
        Current authenticated user

    Raises
    ------
    HTTPException
        403 if user is not an administrator
        404 if token not found
    """
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can revoke API tokens",
        )

    token = db.query(ApiToken).filter(ApiToken.id == token_id).first()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token not found",
        )

    token.revoked = True
    db.commit()

    return None
