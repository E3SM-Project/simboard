from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from fastapi_users.authentication.strategy import Strategy
from fastapi_users.exceptions import UserAlreadyExists
from fastapi_users.manager import BaseUserManager
from fastapi_users.router.oauth import (
    STATE_TOKEN_AUDIENCE,
    ErrorCode,
    OAuth2AuthorizeResponse,
    decode_jwt,
    generate_state_token,
)
from httpx_oauth.integrations.fastapi import OAuth2AuthorizeCallback

from app.core.config import settings
from app.features.user.auth.oauth import (
    GITHUB_OAUTH_BACKEND,
    GITHUB_OAUTH_CLIENT,
    _build_frontend_auth_redirect_url,
    _normalize_post_login_return_to,
)
from app.features.user.auth.token import JWT_BEARER_BACKEND
from app.features.user.manager import (
    current_active_user,
    fastapi_users,
    get_user_manager,
)
from app.features.user.schemas import UserRead, UserUpdate

user_router = APIRouter(prefix="/users", tags=["users"])
auth_router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_authorize_callback = OAuth2AuthorizeCallback(
    GITHUB_OAUTH_CLIENT,
    redirect_url=settings.github_redirect_url,
)


# --- GitHub OAuth Routes ---
@auth_router.get(
    "/github/authorize",
    name="oauth:github.github.authorize",
    response_model=OAuth2AuthorizeResponse,
)
async def github_authorize(
    return_to: str | None = Query(default=None),
    scopes: list[str] | None = Query(default=None),
) -> OAuth2AuthorizeResponse:
    """Initiate the GitHub OAuth flow by generating an authorization URL.

    Parameters:
    -----------
    return_to : str | None
        The URL to redirect to after login.
    scopes : list[str] | None
        The OAuth scopes to request.

    Returns:
    --------
    OAuth2AuthorizeResponse
        An object containing the GitHub authorization URL.
    """
    state_data: dict[str, str] = {}
    normalized_return_to = _normalize_post_login_return_to(return_to)
    if normalized_return_to is not None:
        state_data["return_to"] = normalized_return_to

    state = generate_state_token(state_data, settings.github_state_secret_key)
    authorization_url = await GITHUB_OAUTH_CLIENT.get_authorization_url(
        settings.github_redirect_url,
        state,
        scopes,
    )

    return OAuth2AuthorizeResponse(authorization_url=authorization_url)


@auth_router.get(
    "/github/callback",
    name="oauth:github.github.callback",
    description="The response varies based on the authentication backend used.",
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "content": {
                "application/json": {
                    "examples": {
                        "INVALID_STATE_TOKEN": {
                            "summary": "Invalid state token.",
                            "value": None,
                        },
                        ErrorCode.LOGIN_BAD_CREDENTIALS: {
                            "summary": "User is inactive.",
                            "value": {"detail": ErrorCode.LOGIN_BAD_CREDENTIALS},
                        },
                    }
                }
            }
        },
    },
)
async def github_callback(
    request: Request,
    access_token_state=Depends(oauth2_authorize_callback),  # noqa: B008
    user_manager: BaseUserManager = Depends(get_user_manager),  # noqa: B008
    strategy: Strategy = Depends(GITHUB_OAUTH_BACKEND.get_strategy),  # noqa: B008
):
    """
    Handle the GitHub OAuth callback by processing the access token and logging
    in the user.

    Parameters
    ----------
    request : Request
        The incoming HTTP request.
    access_token_state : tuple[dict, str | None]
        A tuple containing the access token information and the state token.
    user_manager : BaseUserManager
        The user manager instance for handling user operations.
    strategy : Strategy
        The authentication strategy for logging in the user.

    Returns
    -------
    Response
        A response object that redirects the user to the frontend with the
        appropriate authentication state.
    """

    token, state = access_token_state
    account_id, account_email = await GITHUB_OAUTH_CLIENT.get_id_email(
        token["access_token"]
    )

    if account_email is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorCode.OAUTH_NOT_AVAILABLE_EMAIL,
        )

    if state is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

    try:
        state_data = decode_jwt(
            state,
            settings.github_state_secret_key,
            [STATE_TOKEN_AUDIENCE],
        )
    except Exception as exc:  # pragma: no cover - library-specific decode failures
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST) from exc

    try:
        user = await user_manager.oauth_callback(
            GITHUB_OAUTH_CLIENT.name,
            token["access_token"],
            account_id,
            account_email,
            token.get("expires_at"),
            token.get("refresh_token"),
            request,
            associate_by_email=True,
            is_verified_by_default=True,
        )
    except UserAlreadyExists as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorCode.OAUTH_USER_ALREADY_EXISTS,
        ) from exc

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorCode.LOGIN_BAD_CREDENTIALS,
        )

    response = await GITHUB_OAUTH_BACKEND.login(strategy, user)
    response.headers["location"] = _build_frontend_auth_redirect_url(
        state_data.get("return_to")
    )
    await user_manager.on_after_login(user, request, response)
    return response


# --- JWT Login Routes ---
auth_router.include_router(
    fastapi_users.get_auth_router(JWT_BEARER_BACKEND),
    prefix="/jwt",
)


@auth_router.post("/logout", status_code=status.HTTP_200_OK)
async def logout():
    """Log out the current user by clearing the authentication cookie."""
    response = JSONResponse(
        content={"message": "Successfully logged out"},
        status_code=status.HTTP_200_OK,
    )
    response.delete_cookie(
        key=settings.cookie_name,
        path="/",
        httponly=settings.cookie_httponly,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )

    return response


# --- USER ROUTES ---
# Users can manage their own profile; /{id} routes require superuser internally.
user_router.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    tags=["users"],
    dependencies=[Depends(current_active_user)],
)
