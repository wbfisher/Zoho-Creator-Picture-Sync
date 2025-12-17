from supabase import create_client, Client
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def get_supabase_client(url: str, key: str) -> Client:
    return create_client(url, key)


# SQL to create tables (run once in Supabase SQL editor)
SCHEMA_SQL = """
-- Images table: tracks all synced images
CREATE TABLE IF NOT EXISTS images (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zoho_record_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    original_filename TEXT,
    storage_path TEXT NOT NULL,
    file_size_bytes INTEGER,
    was_processed BOOLEAN DEFAULT FALSE,

    -- Metadata from Zoho record
    tags TEXT[],
    category TEXT,
    description TEXT,

    -- Key categorization fields
    job_captain_timesheet TEXT,
    project_name TEXT,
    department TEXT,

    zoho_metadata JSONB,

    -- Timestamps
    zoho_created_at TIMESTAMP,
    zoho_modified_at TIMESTAMP,
    synced_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(zoho_record_id, field_name)
);

-- Sync runs table: tracks each sync execution
CREATE TABLE IF NOT EXISTS sync_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    status TEXT DEFAULT 'running',
    records_processed INTEGER DEFAULT 0,
    images_synced INTEGER DEFAULT 0,
    images_skipped INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0,
    error_log JSONB
);

-- Index for efficient queries
CREATE INDEX IF NOT EXISTS idx_images_zoho_record ON images(zoho_record_id);
CREATE INDEX IF NOT EXISTS idx_images_tags ON images USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_images_synced_at ON images(synced_at DESC);
CREATE INDEX IF NOT EXISTS idx_sync_runs_started ON sync_runs(started_at DESC);

-- New indexes for filtering
CREATE INDEX IF NOT EXISTS idx_images_job_captain ON images(job_captain_timesheet);
CREATE INDEX IF NOT EXISTS idx_images_project ON images(project_name);
CREATE INDEX IF NOT EXISTS idx_images_department ON images(department);

-- Full text search index
CREATE INDEX IF NOT EXISTS idx_images_filename_search ON images USING GIN(to_tsvector('english', original_filename));
"""


class ImageRepository:
    def __init__(self, client: Client):
        self.client = client

    async def image_exists(self, zoho_record_id: str, field_name: str) -> bool:
        result = self.client.table("images").select("id").eq(
            "zoho_record_id", zoho_record_id
        ).eq("field_name", field_name).execute()
        return len(result.data) > 0

    async def upsert_image(
        self,
        zoho_record_id: str,
        field_name: str,
        storage_path: str,
        original_filename: str,
        file_size_bytes: int,
        was_processed: bool,
        tags: list[str] = None,
        category: str = None,
        description: str = None,
        job_captain_timesheet: str = None,
        project_name: str = None,
        department: str = None,
        zoho_metadata: dict = None,
        zoho_created_at: datetime = None,
        zoho_modified_at: datetime = None,
    ):
        data = {
            "zoho_record_id": zoho_record_id,
            "field_name": field_name,
            "storage_path": storage_path,
            "original_filename": original_filename,
            "file_size_bytes": file_size_bytes,
            "was_processed": was_processed,
            "tags": tags or [],
            "category": category,
            "description": description,
            "job_captain_timesheet": job_captain_timesheet,
            "project_name": project_name,
            "department": department,
            "zoho_metadata": zoho_metadata or {},
            "synced_at": datetime.utcnow().isoformat(),
        }
        if zoho_created_at:
            data["zoho_created_at"] = zoho_created_at.isoformat()
        if zoho_modified_at:
            data["zoho_modified_at"] = zoho_modified_at.isoformat()

        self.client.table("images").upsert(
            data,
            on_conflict="zoho_record_id,field_name"
        ).execute()

    async def get_images(
        self,
        job_captain_timesheet: str = None,
        project_name: str = None,
        department: str = None,
        search: str = None,
        tags: list[str] = None,
        category: str = None,
        date_from: str = None,
        date_to: str = None,
        limit: int = 100,
        offset: int = 0
    ) -> tuple[list[dict], int]:
        """Get images with filters. Returns (images, total_count)."""
        # Build query
        query = self.client.table("images").select("*", count="exact")

        if job_captain_timesheet:
            query = query.eq("job_captain_timesheet", job_captain_timesheet)
        if project_name:
            query = query.eq("project_name", project_name)
        if department:
            query = query.eq("department", department)
        if tags:
            query = query.contains("tags", tags)
        if category:
            query = query.eq("category", category)
        if search:
            query = query.ilike("original_filename", f"%{search}%")
        if date_from:
            query = query.gte("synced_at", date_from)
        if date_to:
            query = query.lte("synced_at", date_to)

        result = query.order("synced_at", desc=True).range(offset, offset + limit - 1).execute()
        return result.data, result.count or 0

    async def get_filter_values(self) -> dict:
        """Get distinct values for filter dropdowns."""
        # Get distinct job captain timesheets
        jc_result = self.client.table("images").select("job_captain_timesheet").neq(
            "job_captain_timesheet", None
        ).execute()
        job_captains = sorted(set(r["job_captain_timesheet"] for r in jc_result.data if r["job_captain_timesheet"]))

        # Get distinct projects
        proj_result = self.client.table("images").select("project_name").neq(
            "project_name", None
        ).execute()
        projects = sorted(set(r["project_name"] for r in proj_result.data if r["project_name"]))

        # Get distinct departments
        dept_result = self.client.table("images").select("department").neq(
            "department", None
        ).execute()
        departments = sorted(set(r["department"] for r in dept_result.data if r["department"]))

        return {
            "job_captain_timesheets": job_captains,
            "project_names": projects,
            "departments": departments,
        }

    async def get_stats(self) -> dict:
        total = self.client.table("images").select("id", count="exact").execute()
        processed = self.client.table("images").select("id", count="exact").eq("was_processed", True).execute()

        return {
            "total_images": total.count,
            "processed_images": processed.count,
        }


class SyncRunRepository:
    def __init__(self, client: Client):
        self.client = client

    async def start_run(self) -> str:
        result = self.client.table("sync_runs").insert({
            "status": "running"
        }).execute()
        return result.data[0]["id"]

    async def update_run(
        self,
        run_id: str,
        records_processed: int = None,
        images_synced: int = None,
        images_skipped: int = None,
        errors: int = None,
    ):
        data = {}
        if records_processed is not None:
            data["records_processed"] = records_processed
        if images_synced is not None:
            data["images_synced"] = images_synced
        if images_skipped is not None:
            data["images_skipped"] = images_skipped
        if errors is not None:
            data["errors"] = errors

        if data:
            self.client.table("sync_runs").update(data).eq("id", run_id).execute()

    async def complete_run(self, run_id: str, status: str = "completed", error_log: list = None):
        data = {
            "status": status,
            "completed_at": datetime.utcnow().isoformat(),
        }
        if error_log:
            data["error_log"] = error_log

        self.client.table("sync_runs").update(data).eq("id", run_id).execute()

    async def get_recent_runs(self, limit: int = 10) -> list[dict]:
        result = self.client.table("sync_runs").select("*").order(
            "started_at", desc=True
        ).limit(limit).execute()
        return result.data

    async def get_last_successful_run(self) -> Optional[dict]:
        result = self.client.table("sync_runs").select("*").eq(
            "status", "completed"
        ).order("completed_at", desc=True).limit(1).execute()
        return result.data[0] if result.data else None
