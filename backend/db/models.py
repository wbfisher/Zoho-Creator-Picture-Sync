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
    
    -- Metadata from Zoho record (customize based on your form fields)
    tags TEXT[],
    category TEXT,
    description TEXT,
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

-- Batch sync state table: tracks batch sync sessions with pause/resume
CREATE TABLE IF NOT EXISTS batch_sync_state (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    -- Status: pending, running, paused, completed, cancelled, failed
    status TEXT DEFAULT 'pending',

    -- Configuration
    batch_size INTEGER DEFAULT 100,
    delay_between_batches INTEGER DEFAULT 2,  -- seconds
    date_from TIMESTAMP,
    date_to TIMESTAMP,
    dry_run BOOLEAN DEFAULT FALSE,

    -- Progress tracking
    current_offset INTEGER DEFAULT 0,
    total_records_estimated INTEGER,

    -- Stats
    batches_completed INTEGER DEFAULT 0,
    records_processed INTEGER DEFAULT 0,
    images_synced INTEGER DEFAULT 0,
    images_skipped INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0,
    error_log JSONB DEFAULT '[]'::jsonb,

    -- Current batch info
    current_batch_started_at TIMESTAMP,
    last_batch_completed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_batch_sync_state_status ON batch_sync_state(status);
CREATE INDEX IF NOT EXISTS idx_batch_sync_state_created ON batch_sync_state(created_at DESC);
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
        tags: list[str] = None,
        category: str = None,
        job_captain_timesheet: str = None,
        project_name: str = None,
        department: str = None,
        photo_origin: str = None,
        search: str = None,
        date_from: str = None,
        date_to: str = None,
        sort_by: str = "zoho_created_at",
        sort_order: str = "desc",
        limit: int = 100,
        offset: int = 0
    ) -> list[dict]:
        query = self.client.table("images").select("*")

        if tags:
            query = query.contains("tags", tags)
        if category:
            query = query.eq("category", category)

        # Filter by zoho_metadata fields
        # For lookup fields (dict with display_value), use nested contains
        if job_captain_timesheet:
            query = query.contains(
                "zoho_metadata",
                {"Add_Job_Captain_Time_Sheet_Number": {"display_value": job_captain_timesheet}}
            )
        if project_name:
            query = query.contains(
                "zoho_metadata",
                {"Project1": {"display_value": project_name}}
            )
        if department:
            query = query.contains(
                "zoho_metadata",
                {"Project_Department1": {"display_value": department}}
            )
        if photo_origin:
            query = query.contains("zoho_metadata", {"Photo_Origin": photo_origin})

        # Search in filename and description
        if search:
            query = query.or_(f"original_filename.ilike.%{search}%,description.ilike.%{search}%")

        # Date filters (on zoho_created_at for when photo was taken)
        if date_from:
            query = query.gte("zoho_created_at", date_from)
        if date_to:
            query = query.lte("zoho_created_at", date_to)

        # Sorting - validate allowed fields
        allowed_sort_fields = ["zoho_created_at", "synced_at", "original_filename"]
        if sort_by not in allowed_sort_fields:
            sort_by = "zoho_created_at"
        is_desc = sort_order.lower() == "desc"

        result = query.order(sort_by, desc=is_desc).range(offset, offset + limit - 1).execute()
        return result.data

    async def get_count(
        self,
        tags: list[str] = None,
        category: str = None,
        job_captain_timesheet: str = None,
        project_name: str = None,
        department: str = None,
        photo_origin: str = None,
        search: str = None,
        date_from: str = None,
        date_to: str = None,
    ) -> int:
        query = self.client.table("images").select("id", count="exact")

        if tags:
            query = query.contains("tags", tags)
        if category:
            query = query.eq("category", category)

        # Filter by zoho_metadata fields
        # For lookup fields (dict with display_value), use nested contains
        if job_captain_timesheet:
            query = query.contains(
                "zoho_metadata",
                {"Add_Job_Captain_Time_Sheet_Number": {"display_value": job_captain_timesheet}}
            )
        if project_name:
            query = query.contains(
                "zoho_metadata",
                {"Project1": {"display_value": project_name}}
            )
        if department:
            query = query.contains(
                "zoho_metadata",
                {"Project_Department1": {"display_value": department}}
            )
        if photo_origin:
            query = query.contains("zoho_metadata", {"Photo_Origin": photo_origin})

        # Search in filename and description
        if search:
            query = query.or_(f"original_filename.ilike.%{search}%,description.ilike.%{search}%")

        # Date filters (on zoho_created_at for when photo was taken)
        if date_from:
            query = query.gte("zoho_created_at", date_from)
        if date_to:
            query = query.lte("zoho_created_at", date_to)

        result = query.execute()
        return result.count or 0

    async def get_stats(self) -> dict:
        total = self.client.table("images").select("id", count="exact").execute()
        processed = self.client.table("images").select("id", count="exact").eq("was_processed", True).execute()

        return {
            "total_images": total.count,
            "processed_images": processed.count,
        }

    async def get_oldest_image_date(self) -> Optional[datetime]:
        """Get the oldest zoho_created_at date among synced images."""
        result = self.client.table("images").select("zoho_created_at").order(
            "zoho_created_at", desc=False
        ).limit(1).execute()
        if result.data and result.data[0].get("zoho_created_at"):
            date_str = result.data[0]["zoho_created_at"]
            try:
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                logger.warning(f"Could not parse oldest image date: {date_str}")
                return None
        return None


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


class BatchSyncRepository:
    """Repository for managing batch sync state."""

    def __init__(self, client: Client):
        self.client = client

    async def create_batch_sync(
        self,
        batch_size: int = 100,
        delay_between_batches: int = 2,
        date_from: datetime = None,
        date_to: datetime = None,
        dry_run: bool = False,
        total_records_estimated: int = None,
    ) -> dict:
        """Create a new batch sync session."""
        data = {
            "status": "pending",
            "batch_size": batch_size,
            "delay_between_batches": delay_between_batches,
            "dry_run": dry_run,
            "current_offset": 0,
            "batches_completed": 0,
            "records_processed": 0,
            "images_synced": 0,
            "images_skipped": 0,
            "errors": 0,
            "error_log": [],
        }
        if date_from:
            data["date_from"] = date_from.isoformat()
        if date_to:
            data["date_to"] = date_to.isoformat()
        if total_records_estimated is not None:
            data["total_records_estimated"] = total_records_estimated

        result = self.client.table("batch_sync_state").insert(data).execute()
        return result.data[0]

    async def get_batch_sync(self, batch_id: str) -> Optional[dict]:
        """Get a batch sync by ID."""
        result = self.client.table("batch_sync_state").select("*").eq("id", batch_id).execute()
        return result.data[0] if result.data else None

    async def get_active_batch_sync(self) -> Optional[dict]:
        """Get the currently active (running or paused) batch sync."""
        result = self.client.table("batch_sync_state").select("*").in_(
            "status", ["pending", "running", "paused"]
        ).order("created_at", desc=True).limit(1).execute()
        return result.data[0] if result.data else None

    async def get_recent_batch_syncs(self, limit: int = 10) -> list[dict]:
        """Get recent batch sync sessions."""
        result = self.client.table("batch_sync_state").select("*").order(
            "created_at", desc=True
        ).limit(limit).execute()
        return result.data

    async def update_batch_sync(
        self,
        batch_id: str,
        status: str = None,
        current_offset: int = None,
        batches_completed: int = None,
        records_processed: int = None,
        images_synced: int = None,
        images_skipped: int = None,
        errors: int = None,
        error_log: list = None,
        current_batch_started_at: datetime = None,
        last_batch_completed_at: datetime = None,
        total_records_estimated: int = None,
    ):
        """Update batch sync state."""
        data = {"updated_at": datetime.utcnow().isoformat()}

        if status is not None:
            data["status"] = status
        if current_offset is not None:
            data["current_offset"] = current_offset
        if batches_completed is not None:
            data["batches_completed"] = batches_completed
        if records_processed is not None:
            data["records_processed"] = records_processed
        if images_synced is not None:
            data["images_synced"] = images_synced
        if images_skipped is not None:
            data["images_skipped"] = images_skipped
        if errors is not None:
            data["errors"] = errors
        if error_log is not None:
            data["error_log"] = error_log
        if current_batch_started_at is not None:
            data["current_batch_started_at"] = current_batch_started_at.isoformat()
        if last_batch_completed_at is not None:
            data["last_batch_completed_at"] = last_batch_completed_at.isoformat()
        if total_records_estimated is not None:
            data["total_records_estimated"] = total_records_estimated

        self.client.table("batch_sync_state").update(data).eq("id", batch_id).execute()

    async def set_status(self, batch_id: str, status: str):
        """Set the status of a batch sync."""
        await self.update_batch_sync(batch_id, status=status)

    async def append_errors(self, batch_id: str, new_errors: list):
        """Append errors to the error log."""
        current = await self.get_batch_sync(batch_id)
        if current:
            existing_errors = current.get("error_log") or []
            combined = existing_errors + new_errors
            # Keep last 1000 errors max
            if len(combined) > 1000:
                combined = combined[-1000:]
            await self.update_batch_sync(batch_id, error_log=combined)
