import httpx
from datetime import datetime, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class ZohoAuthError(Exception):
    """Raised when Zoho token refresh fails. Carries diagnostics from the response."""

    def __init__(self, message: str, response_body: str = None, status_code: int = None):
        super().__init__(message)
        self.response_body = response_body
        self.status_code = status_code


class ZohoAuth:
    TOKEN_URL = "https://accounts.zoho.com/oauth/v2/token"

    def __init__(self, client_id: str, client_secret: str, refresh_token: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self._access_token: Optional[str] = None
        self._token_expires: Optional[datetime] = None
        # Diagnostics for health checks
        self.last_error: Optional[str] = None
        self.last_refresh_at: Optional[datetime] = None

    async def get_access_token(self) -> str:
        if self._access_token and self._token_expires and datetime.now() < self._token_expires:
            return self._access_token

        await self._refresh_access_token()
        return self._access_token

    async def _refresh_access_token(self):
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                params={
                    "grant_type": "refresh_token",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": self.refresh_token,
                }
            )

        body = response.text[:500]

        if response.status_code != 200:
            self.last_error = f"HTTP {response.status_code} from Zoho token endpoint: {body}"
            logger.error(f"Zoho token refresh failed: {self.last_error}")
            raise ZohoAuthError(
                f"Zoho token refresh failed with HTTP {response.status_code}",
                response_body=body,
                status_code=response.status_code,
            )

        data = response.json()

        # Zoho returns HTTP 200 with {"error": "..."} when the refresh token is
        # invalid/revoked. This is what silently killed the sync for 5 months —
        # surface it loudly instead of crashing on a KeyError.
        if "access_token" not in data:
            err = data.get("error", "unknown_error")
            self.last_error = f"Zoho rejected token refresh: {err} (response: {body})"
            logger.error(
                f"{self.last_error} — the refresh token is likely invalid or revoked. "
                "Generate a new grant code in Zoho API Console (Self Client), exchange it "
                "for a refresh token, and update ZOHO_REFRESH_TOKEN."
            )
            raise ZohoAuthError(
                f"Zoho rejected token refresh: {err}",
                response_body=body,
                status_code=response.status_code,
            )

        self._access_token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        self._token_expires = datetime.now() + timedelta(seconds=expires_in - 60)
        self.last_error = None
        self.last_refresh_at = datetime.now()

        logger.info("Zoho access token refreshed")

    async def check(self) -> dict:
        """Verify a valid access token can be obtained. Never raises.

        Uses the cached token when still valid, so calling this from a health
        endpoint costs at most one refresh per hour.
        """
        try:
            await self.get_access_token()
            return {
                "ok": True,
                "last_refresh_at": self.last_refresh_at.isoformat() if self.last_refresh_at else None,
            }
        except Exception as e:
            return {"ok": False, "error": str(e), "detail": self.last_error}
