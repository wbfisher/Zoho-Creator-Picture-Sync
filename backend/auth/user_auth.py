"""
Zoho OAuth User Authentication Module.

This module handles user authentication via Zoho OAuth 2.0 authorization code flow.
It's separate from the server-to-server Zoho API authentication used for syncing.
"""
import httpx
import jwt
import secrets
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

# Zoho OAuth endpoints
ZOHO_AUTH_URL = "https://accounts.zoho.com/oauth/v2/auth"
ZOHO_TOKEN_URL = "https://accounts.zoho.com/oauth/v2/token"
ZOHO_USER_INFO_URL = "https://accounts.zoho.com/oauth/user/info"

# Session settings
SESSION_EXPIRE_HOURS = 24
JWT_ALGORITHM = "HS256"


@dataclass
class ZohoUser:
    """Represents an authenticated Zoho user."""
    email: str
    first_name: str
    last_name: str
    display_name: str
    zoho_uid: str


class ZohoUserAuth:
    """
    Handles Zoho OAuth 2.0 authorization code flow for user authentication.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scopes: str,
        secret_key: str,
        whitelist: list[str],
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scopes = scopes
        self.secret_key = secret_key
        self.whitelist = [email.lower() for email in whitelist]
        # Store state tokens to prevent CSRF
        self._pending_states: dict[str, datetime] = {}

    def get_authorization_url(self) -> tuple[str, str]:
        """
        Generate the Zoho OAuth authorization URL.

        Returns:
            Tuple of (authorization_url, state_token)
        """
        state = secrets.token_urlsafe(32)
        # Store state with expiry (5 minutes)
        self._pending_states[state] = datetime.now() + timedelta(minutes=5)
        self._cleanup_expired_states()

        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": self.scopes,
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{ZOHO_AUTH_URL}?{query}", state

    def validate_state(self, state: str) -> bool:
        """Validate that the state token is valid and not expired."""
        self._cleanup_expired_states()
        if state in self._pending_states:
            del self._pending_states[state]
            return True
        return False

    def _cleanup_expired_states(self):
        """Remove expired state tokens."""
        now = datetime.now()
        expired = [s for s, exp in self._pending_states.items() if exp < now]
        for s in expired:
            del self._pending_states[s]

    async def exchange_code_for_tokens(self, code: str) -> dict:
        """
        Exchange authorization code for access and refresh tokens.

        Args:
            code: The authorization code from Zoho callback

        Returns:
            Token response dict containing access_token, refresh_token, etc.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                ZOHO_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": self.redirect_uri,
                    "code": code,
                },
            )
            response.raise_for_status()
            return response.json()

    async def get_user_info(self, access_token: str) -> ZohoUser:
        """
        Fetch user information from Zoho using the access token.

        Args:
            access_token: Valid Zoho access token

        Returns:
            ZohoUser object with user details
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                ZOHO_USER_INFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            data = response.json()

            return ZohoUser(
                email=data.get("Email", ""),
                first_name=data.get("First_Name", ""),
                last_name=data.get("Last_Name", ""),
                display_name=data.get("Display_Name", ""),
                zoho_uid=data.get("ZUID", ""),
            )

    def is_user_whitelisted(self, email: str) -> bool:
        """
        Check if a user's email is in the whitelist.

        Args:
            email: User's email address

        Returns:
            True if whitelisted or if whitelist is empty (allow all)
        """
        if not self.whitelist:
            # Empty whitelist means allow all authenticated users
            return True
        return email.lower() in self.whitelist

    def create_session_token(self, user: ZohoUser) -> str:
        """
        Create a JWT session token for the authenticated user.

        Args:
            user: ZohoUser object

        Returns:
            JWT token string
        """
        payload = {
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "display_name": user.display_name,
            "zoho_uid": user.zoho_uid,
            "exp": datetime.utcnow() + timedelta(hours=SESSION_EXPIRE_HOURS),
            "iat": datetime.utcnow(),
        }
        return jwt.encode(payload, self.secret_key, algorithm=JWT_ALGORITHM)

    def verify_session_token(self, token: str) -> Optional[ZohoUser]:
        """
        Verify and decode a JWT session token.

        Args:
            token: JWT token string

        Returns:
            ZohoUser object if valid, None otherwise
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[JWT_ALGORITHM])
            return ZohoUser(
                email=payload["email"],
                first_name=payload["first_name"],
                last_name=payload["last_name"],
                display_name=payload["display_name"],
                zoho_uid=payload["zoho_uid"],
            )
        except jwt.ExpiredSignatureError:
            logger.debug("Session token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.debug(f"Invalid session token: {e}")
            return None


# Global instance (initialized in main.py)
_user_auth: Optional[ZohoUserAuth] = None


def get_user_auth() -> ZohoUserAuth:
    """Get the global ZohoUserAuth instance."""
    global _user_auth
    if _user_auth is None:
        from config import get_settings
        settings = get_settings()
        _user_auth = ZohoUserAuth(
            client_id=settings.effective_auth_client_id,
            client_secret=settings.effective_auth_client_secret,
            redirect_uri=settings.zoho_auth_redirect_uri,
            scopes=settings.zoho_auth_scopes,
            secret_key=settings.app_secret_key,
            whitelist=settings.whitelist_emails,
        )
    return _user_auth
