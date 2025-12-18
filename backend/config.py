from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import List


class Settings(BaseSettings):
    # Zoho OAuth (for Zoho Creator API - server-to-server)
    zoho_client_id: str
    zoho_client_secret: str
    zoho_refresh_token: str
    zoho_account_owner_name: str
    zoho_app_link_name: str
    zoho_report_link_name: str

    # Zoho OAuth User Login (for user authentication)
    # These can be the same as above or a separate Zoho OAuth client
    zoho_auth_client_id: str = ""  # Defaults to zoho_client_id if empty
    zoho_auth_client_secret: str = ""  # Defaults to zoho_client_secret if empty
    zoho_auth_redirect_uri: str = "http://localhost:8000/api/auth/callback"
    zoho_auth_scopes: str = "AaaServer.profile.READ"  # Scopes for user login

    # User Whitelist (comma-separated email addresses)
    # If empty, all authenticated Zoho users are allowed
    auth_whitelist: str = ""

    # Supabase
    supabase_url: str
    supabase_service_key: str
    supabase_storage_bucket: str = "zoho-pictures"

    # Sync Config
    sync_cron: str = "0 2 * * *"
    image_max_size_mb: int = 5
    image_max_dimension: int = 4000
    image_quality: int = 85

    # App
    app_secret_key: str = "change-me-in-production"
    log_level: str = "INFO"

    @property
    def effective_auth_client_id(self) -> str:
        """Return the OAuth client ID for user auth (falls back to main client)."""
        return self.zoho_auth_client_id or self.zoho_client_id

    @property
    def effective_auth_client_secret(self) -> str:
        """Return the OAuth client secret for user auth (falls back to main secret)."""
        return self.zoho_auth_client_secret or self.zoho_client_secret

    @property
    def whitelist_emails(self) -> List[str]:
        """Parse whitelist into a list of email addresses."""
        if not self.auth_whitelist:
            return []
        return [email.strip().lower() for email in self.auth_whitelist.split(",") if email.strip()]
    
    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
