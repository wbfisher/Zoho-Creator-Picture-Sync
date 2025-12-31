from pydantic_settings import BaseSettings
from typing import Optional
import json
import os


class Settings(BaseSettings):
    # Zoho OAuth
    zoho_client_id: str = ""
    zoho_client_secret: str = ""
    zoho_refresh_token: str = ""
    zoho_account_owner_name: str = ""
    zoho_app_link_name: str = ""
    zoho_report_link_name: str = ""

    # Supabase
    supabase_url: str = ""
    supabase_service_key: str = ""
    supabase_storage_bucket: str = "zoho-pictures"

    # Field Mappings - map Zoho fields to our categories
    field_job_captain_timesheet: str = "Add_Job_Captain_Time_Sheet_Number"
    field_project_name: str = "Project"
    field_department: str = "Project_Department"
    field_tags: str = ""
    field_description: str = ""

    # Sync Config
    sync_cron: str = "0 2 * * *"
    image_max_size_mb: int = 5
    image_max_dimension: int = 4000
    image_quality: int = 85
    sync_batch_size: int = 5  # Concurrent downloads during sync
    sync_rate_limit: float = 5.0  # Max Zoho API calls per second

    # Storage Config
    use_signed_urls: bool = True  # Use signed URLs (True) or public URLs (False)

    # App
    app_secret_key: str = "change-me-in-production"
    log_level: str = "INFO"
    config_file: str = ".config.json"

    class Config:
        env_file = ".env"

    def save_to_file(self):
        """Save user-configurable settings to a JSON file."""
        config_data = {
            "zoho_client_id": self.zoho_client_id,
            "zoho_client_secret": self.zoho_client_secret,
            "zoho_refresh_token": self.zoho_refresh_token,
            "zoho_account_owner_name": self.zoho_account_owner_name,
            "zoho_app_link_name": self.zoho_app_link_name,
            "zoho_report_link_name": self.zoho_report_link_name,
            "field_job_captain_timesheet": self.field_job_captain_timesheet,
            "field_project_name": self.field_project_name,
            "field_department": self.field_department,
            "field_tags": self.field_tags,
            "field_description": self.field_description,
            "sync_cron": self.sync_cron,
            "image_max_size_mb": self.image_max_size_mb,
            "image_max_dimension": self.image_max_dimension,
            "image_quality": self.image_quality,
            "sync_batch_size": self.sync_batch_size,
            "sync_rate_limit": self.sync_rate_limit,
            "supabase_storage_bucket": self.supabase_storage_bucket,
            "use_signed_urls": self.use_signed_urls,
        }
        with open(self.config_file, "w") as f:
            json.dump(config_data, f, indent=2)

    def load_from_file(self):
        """Load settings from JSON file if it exists."""
        if os.path.exists(self.config_file):
            with open(self.config_file, "r") as f:
                data = json.load(f)
                for key, value in data.items():
                    if hasattr(self, key) and value:
                        setattr(self, key, value)

    def to_safe_dict(self) -> dict:
        """Return config dict with sensitive values masked."""
        return {
            "zoho_client_id": "***" if self.zoho_client_id else "",
            "zoho_client_secret": "***" if self.zoho_client_secret else "",
            "zoho_refresh_token": "***" if self.zoho_refresh_token else "",
            "zoho_account_owner_name": self.zoho_account_owner_name,
            "zoho_app_link_name": self.zoho_app_link_name,
            "zoho_report_link_name": self.zoho_report_link_name,
            "field_job_captain_timesheet": self.field_job_captain_timesheet,
            "field_project_name": self.field_project_name,
            "field_department": self.field_department,
            "field_tags": self.field_tags,
            "field_description": self.field_description,
            "sync_cron": self.sync_cron,
            "image_max_size_mb": self.image_max_size_mb,
            "image_max_dimension": self.image_max_dimension,
            "image_quality": self.image_quality,
            "sync_batch_size": self.sync_batch_size,
            "sync_rate_limit": self.sync_rate_limit,
            "supabase_storage_bucket": self.supabase_storage_bucket,
            "use_signed_urls": self.use_signed_urls,
        }


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.load_from_file()
    return _settings


def update_settings(updates: dict) -> Settings:
    """Update settings and persist to file."""
    global _settings
    settings = get_settings()

    for key, value in updates.items():
        if hasattr(settings, key) and value is not None:
            setattr(settings, key, value)

    settings.save_to_file()
    return settings
