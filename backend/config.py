from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Zoho OAuth
    zoho_client_id: str
    zoho_client_secret: str
    zoho_refresh_token: str
    zoho_account_owner_name: str
    zoho_app_link_name: str
    zoho_report_link_name: str
    
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
    
    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
