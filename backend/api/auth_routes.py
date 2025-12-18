"""
Authentication API routes for Zoho OAuth user login.
"""
from fastapi import APIRouter, HTTPException, Response, Request, Depends
from fastapi.responses import RedirectResponse
from typing import Optional
import logging

from auth.user_auth import get_user_auth, ZohoUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Cookie settings
SESSION_COOKIE_NAME = "session"
COOKIE_MAX_AGE = 60 * 60 * 24  # 24 hours


def get_current_user(request: Request) -> Optional[ZohoUser]:
    """
    Dependency to get the current authenticated user from session cookie.

    Returns None if not authenticated (doesn't raise exception).
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None

    auth = get_user_auth()
    return auth.verify_session_token(token)


def require_auth(request: Request) -> ZohoUser:
    """
    Dependency that requires authentication.

    Raises HTTPException 401 if not authenticated.
    """
    user = get_current_user(request)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


@router.get("/login")
async def login():
    """
    Initiate Zoho OAuth login flow.

    Returns a redirect to Zoho's authorization page.
    """
    auth = get_user_auth()
    auth_url, state = auth.get_authorization_url()

    response = RedirectResponse(url=auth_url, status_code=302)
    # Store state in a short-lived cookie for CSRF protection
    response.set_cookie(
        key="oauth_state",
        value=state,
        max_age=300,  # 5 minutes
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/callback")
async def oauth_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
):
    """
    Handle OAuth callback from Zoho.

    Exchanges the authorization code for tokens, fetches user info,
    validates against whitelist, and creates a session.
    """
    # Handle OAuth errors
    if error:
        logger.warning(f"OAuth error: {error} - {error_description}")
        return RedirectResponse(
            url=f"/login?error={error}&message={error_description or 'Authentication failed'}",
            status_code=302,
        )

    if not code or not state:
        logger.warning("Missing code or state in OAuth callback")
        return RedirectResponse(
            url="/login?error=invalid_request&message=Missing authorization code",
            status_code=302,
        )

    # Verify state to prevent CSRF
    stored_state = request.cookies.get("oauth_state")
    auth = get_user_auth()

    if not stored_state or not auth.validate_state(stored_state) or stored_state != state:
        logger.warning("Invalid OAuth state - possible CSRF attack")
        return RedirectResponse(
            url="/login?error=invalid_state&message=Invalid state parameter",
            status_code=302,
        )

    try:
        # Exchange code for tokens
        tokens = await auth.exchange_code_for_tokens(code)
        access_token = tokens.get("access_token")

        if not access_token:
            logger.error("No access token in response")
            return RedirectResponse(
                url="/login?error=token_error&message=Failed to obtain access token",
                status_code=302,
            )

        # Get user info
        user = await auth.get_user_info(access_token)
        logger.info(f"User logged in: {user.email}")

        # Check whitelist
        if not auth.is_user_whitelisted(user.email):
            logger.warning(f"User not whitelisted: {user.email}")
            return RedirectResponse(
                url="/login?error=access_denied&message=Your account is not authorized to access this application",
                status_code=302,
            )

        # Create session token
        session_token = auth.create_session_token(user)

        # Redirect to app with session cookie
        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=session_token,
            max_age=COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=False,  # Set to True in production with HTTPS
        )
        # Clear the oauth_state cookie
        response.delete_cookie(key="oauth_state")

        return response

    except Exception as e:
        logger.exception(f"OAuth callback error: {e}")
        return RedirectResponse(
            url=f"/login?error=server_error&message=Authentication failed: {str(e)}",
            status_code=302,
        )


@router.post("/logout")
async def logout(response: Response):
    """
    Log out the current user by clearing the session cookie.
    """
    response.delete_cookie(key=SESSION_COOKIE_NAME)
    return {"message": "Logged out successfully"}


@router.get("/logout")
async def logout_get():
    """
    Log out via GET request (for simple links) - redirects to login page.
    """
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(key=SESSION_COOKIE_NAME)
    return response


@router.get("/me")
async def get_current_user_info(user: ZohoUser = Depends(require_auth)):
    """
    Get the current authenticated user's information.
    """
    return {
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "display_name": user.display_name,
        "zoho_uid": user.zoho_uid,
    }


@router.get("/check")
async def check_auth(request: Request):
    """
    Check if the current request is authenticated.

    Returns authentication status without requiring auth.
    Useful for the frontend to check session validity.
    """
    user = get_current_user(request)
    if user:
        return {
            "authenticated": True,
            "user": {
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "display_name": user.display_name,
            },
        }
    return {"authenticated": False, "user": None}
