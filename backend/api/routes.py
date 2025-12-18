from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from db.models import ImageRepository, SyncRunRepository, BatchSyncRepository, get_supabase_client
from config import get_settings

router = APIRouter()


class ConfigUpdate(BaseModel):
    """Configuration update request (read-only for env-based settings)"""
    sync_cron: Optional[str] = None
    image_max_size_mb: Optional[int] = None
    image_max_dimension: Optional[int] = None
    image_quality: Optional[int] = None


class BatchSyncConfig(BaseModel):
    """Configuration for batch sync."""
    batch_size: int = 100
    delay_between_batches: int = 2
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    dry_run: bool = False


def get_repos():
    settings = get_settings()
    client = get_supabase_client(settings.supabase_url, settings.supabase_service_key)
    return ImageRepository(client), SyncRunRepository(client)


@router.get("/status")
async def get_status():
    """Get current sync status and stats."""
    images_repo, runs_repo = get_repos()
    
    stats = await images_repo.get_stats()
    recent_runs = await runs_repo.get_recent_runs(limit=5)
    
    # Check if sync is currently running
    is_running = any(run.get("status") == "running" for run in recent_runs)
    
    return {
        "is_running": is_running,
        "stats": stats,
        "recent_runs": recent_runs,
    }


@router.post("/sync")
async def trigger_sync(
    background_tasks: BackgroundTasks,
    full_sync: bool = Query(False, description="Run full sync instead of incremental"),
    max_records: Optional[int] = Query(None, description="Limit number of records to process")
):
    """Trigger a sync operation."""
    from main import get_sync_engine

    images_repo, runs_repo = get_repos()
    recent_runs = await runs_repo.get_recent_runs(limit=1)

    if recent_runs and recent_runs[0].get("status") == "running":
        raise HTTPException(status_code=409, detail="Sync already in progress")

    # Create run_id before starting background task
    run_id = await runs_repo.start_run()

    async def run_sync():
        engine = get_sync_engine()
        await engine.run_sync(full_sync=full_sync, max_records=max_records, run_id=run_id)

    background_tasks.add_task(run_sync)

    response = {"message": "Sync started", "run_id": run_id, "full_sync": full_sync}
    if max_records:
        response["max_records"] = max_records
    return response


@router.get("/images")
async def list_images(
    tags: Optional[str] = Query(None, description="Comma-separated tags to filter by"),
    category: Optional[str] = None,
    job_captain_timesheet: Optional[str] = Query(None, description="Filter by job captain timesheet"),
    project_name: Optional[str] = Query(None, description="Filter by project name"),
    department: Optional[str] = Query(None, description="Filter by department"),
    photo_origin: Optional[str] = Query(None, description="Filter by photo origin"),
    search: Optional[str] = Query(None, description="Search in filename and description"),
    date_from: Optional[str] = Query(None, description="Filter by synced date from (ISO format)"),
    date_to: Optional[str] = Query(None, description="Filter by synced date to (ISO format)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List synced images with optional filtering."""
    images_repo, _ = get_repos()

    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    images = await images_repo.get_images(
        tags=tag_list,
        category=category,
        job_captain_timesheet=job_captain_timesheet,
        project_name=project_name,
        department=department,
        photo_origin=photo_origin,
        search=search,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )

    # Add signed URLs for image access
    settings = get_settings()
    client = get_supabase_client(settings.supabase_url, settings.supabase_service_key)

    for img in images:
        if img.get("storage_path"):
            try:
                signed = client.storage.from_(settings.supabase_storage_bucket).create_signed_url(
                    img["storage_path"], 3600  # 1 hour expiry
                )
                # Handle both possible key names from different supabase-py versions
                img["url"] = signed.get("signedUrl") or signed.get("signedURL") or signed.get("signed_url")
            except Exception as e:
                import logging
                logging.error(f"Failed to create signed URL for {img.get('storage_path')}: {e}")
                img["url"] = None

        # Extract categorization fields from zoho_metadata for frontend
        metadata = img.get("zoho_metadata", {})
        if not img.get("job_captain_timesheet"):
            img["job_captain_timesheet"] = metadata.get("Add_Job_Captain_Time_Sheet_Number")
        if not img.get("project_name"):
            img["project_name"] = metadata.get("Project")
        if not img.get("department"):
            img["department"] = metadata.get("Project_Department")
        if not img.get("photo_origin"):
            img["photo_origin"] = metadata.get("Photo_Origin")

    # Get total count for pagination
    total_count = await images_repo.get_count(
        tags=tag_list,
        category=category,
        job_captain_timesheet=job_captain_timesheet,
        project_name=project_name,
        department=department,
        photo_origin=photo_origin,
        search=search,
        date_from=date_from,
        date_to=date_to,
    )

    return {"images": images, "count": total_count}


@router.get("/runs")
async def list_runs(limit: int = Query(20, ge=1, le=100)):
    """List recent sync runs."""
    _, runs_repo = get_repos()
    runs = await runs_repo.get_recent_runs(limit=limit)
    return {"runs": runs}


@router.get("/runs/{run_id}")
async def get_run(run_id: str):
    """Get details of a specific sync run including error log."""
    settings = get_settings()
    client = get_supabase_client(settings.supabase_url, settings.supabase_service_key)
    result = client.table("sync_runs").select("*").eq("id", run_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Run not found")
    return result.data[0]


# =============================================================================
# Batch Sync Endpoints
# =============================================================================

def get_batch_repo():
    """Get batch sync repository."""
    settings = get_settings()
    client = get_supabase_client(settings.supabase_url, settings.supabase_service_key)
    return BatchSyncRepository(client)


def get_batch_engine():
    """Get batch sync engine."""
    from main import get_sync_engine
    from sync.batch_engine import BatchSyncEngine

    # Reuse the same configuration as the regular sync engine
    sync_engine = get_sync_engine()
    return BatchSyncEngine(
        zoho_client=sync_engine.zoho,
        supabase_client=sync_engine.supabase,
        storage_bucket=sync_engine.bucket,
        image_processor=sync_engine.processor,
        report_link_name=sync_engine.report_link_name,
        tag_fields=sync_engine.tag_fields,
        category_field=sync_engine.category_field,
        description_field=sync_engine.description_field,
    )


@router.post("/sync/batch")
async def start_batch_sync(
    background_tasks: BackgroundTasks,
    config: BatchSyncConfig,
):
    """Start a new batch sync session."""
    batch_repo = get_batch_repo()

    # Check if there's already an active batch sync
    active = await batch_repo.get_active_batch_sync()
    if active and active.get("status") in ["pending", "running"]:
        raise HTTPException(
            status_code=409,
            detail=f"Batch sync already in progress (id: {active['id']}, status: {active['status']})"
        )

    # Parse dates if provided
    date_from = None
    date_to = None
    if config.date_from:
        try:
            date_from = datetime.fromisoformat(config.date_from.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date_from format")
    if config.date_to:
        try:
            date_to = datetime.fromisoformat(config.date_to.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date_to format")

    # Create batch sync record
    batch_state = await batch_repo.create_batch_sync(
        batch_size=config.batch_size,
        delay_between_batches=config.delay_between_batches,
        date_from=date_from,
        date_to=date_to,
        dry_run=config.dry_run,
    )

    batch_id = batch_state["id"]

    # Start batch sync in background
    async def run_batch():
        engine = get_batch_engine()
        await engine.run_batch_sync(batch_id)

    background_tasks.add_task(run_batch)

    return {
        "message": "Batch sync started",
        "batch_id": batch_id,
        "config": {
            "batch_size": config.batch_size,
            "delay_between_batches": config.delay_between_batches,
            "date_from": config.date_from,
            "date_to": config.date_to,
            "dry_run": config.dry_run,
        }
    }


@router.get("/sync/batch")
async def get_batch_sync_status():
    """Get current batch sync status."""
    batch_repo = get_batch_repo()

    # Get active batch sync
    active = await batch_repo.get_active_batch_sync()

    # Get recent batch syncs
    recent = await batch_repo.get_recent_batch_syncs(limit=5)

    return {
        "active": active,
        "recent": recent,
    }


@router.get("/sync/batch/{batch_id}")
async def get_batch_sync_details(batch_id: str):
    """Get details of a specific batch sync."""
    batch_repo = get_batch_repo()
    batch_state = await batch_repo.get_batch_sync(batch_id)

    if not batch_state:
        raise HTTPException(status_code=404, detail="Batch sync not found")

    return batch_state


@router.post("/sync/batch/{batch_id}/pause")
async def pause_batch_sync(batch_id: str):
    """Pause a running batch sync."""
    from sync.batch_engine import request_pause

    batch_repo = get_batch_repo()
    batch_state = await batch_repo.get_batch_sync(batch_id)

    if not batch_state:
        raise HTTPException(status_code=404, detail="Batch sync not found")

    if batch_state.get("status") != "running":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot pause batch sync with status: {batch_state.get('status')}"
        )

    request_pause(batch_id)
    return {"message": "Pause requested", "batch_id": batch_id}


@router.post("/sync/batch/{batch_id}/resume")
async def resume_batch_sync(
    batch_id: str,
    background_tasks: BackgroundTasks,
):
    """Resume a paused batch sync."""
    batch_repo = get_batch_repo()
    batch_state = await batch_repo.get_batch_sync(batch_id)

    if not batch_state:
        raise HTTPException(status_code=404, detail="Batch sync not found")

    if batch_state.get("status") != "paused":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resume batch sync with status: {batch_state.get('status')}"
        )

    # Check if there's another running batch sync
    active = await batch_repo.get_active_batch_sync()
    if active and active.get("id") != batch_id and active.get("status") == "running":
        raise HTTPException(
            status_code=409,
            detail=f"Another batch sync is already running (id: {active['id']})"
        )

    # Start batch sync in background (it will resume from current_offset)
    async def run_batch():
        engine = get_batch_engine()
        await engine.run_batch_sync(batch_id)

    background_tasks.add_task(run_batch)

    return {"message": "Batch sync resumed", "batch_id": batch_id}


@router.post("/sync/batch/{batch_id}/cancel")
async def cancel_batch_sync(batch_id: str):
    """Cancel a running or paused batch sync."""
    from sync.batch_engine import request_cancel

    batch_repo = get_batch_repo()
    batch_state = await batch_repo.get_batch_sync(batch_id)

    if not batch_state:
        raise HTTPException(status_code=404, detail="Batch sync not found")

    status = batch_state.get("status")
    if status not in ["pending", "running", "paused"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel batch sync with status: {status}"
        )

    if status == "running":
        request_cancel(batch_id)
        return {"message": "Cancel requested", "batch_id": batch_id}
    else:
        # If paused or pending, cancel immediately
        await batch_repo.set_status(batch_id, "cancelled")
        return {"message": "Batch sync cancelled", "batch_id": batch_id}


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@router.get("/config")
async def get_config():
    """Get current configuration (sensitive values masked)."""
    settings = get_settings()
    return {
        "zoho_client_id": "***" + settings.zoho_client_id[-4:] if settings.zoho_client_id else "",
        "zoho_client_secret": "***" + settings.zoho_client_secret[-4:] if settings.zoho_client_secret else "",
        "zoho_refresh_token": "***" + settings.zoho_refresh_token[-4:] if settings.zoho_refresh_token else "",
        "zoho_account_owner_name": settings.zoho_account_owner_name,
        "zoho_app_link_name": settings.zoho_app_link_name,
        "zoho_report_link_name": settings.zoho_report_link_name,
        "supabase_storage_bucket": settings.supabase_storage_bucket,
        "sync_cron": settings.sync_cron,
        "image_max_size_mb": settings.image_max_size_mb,
        "image_max_dimension": settings.image_max_dimension,
        "image_quality": settings.image_quality,
        # Field mappings from defaults (could be made configurable)
        "field_job_captain_timesheet": "Add_Job_Captain_Time_Sheet_Number",
        "field_project_name": "Project",
        "field_department": "Project_Department",
        "field_tags": "Tags",
        "field_description": "Description",
    }


@router.put("/config")
async def update_config(config: ConfigUpdate):
    """Update configuration. Note: Environment-based settings require restart."""
    # Since settings come from environment variables, we can't update them at runtime
    # Return current config with a note
    return {
        "message": "Configuration is environment-based. Changes require app restart.",
        "note": "Update environment variables and restart to apply changes.",
    }


@router.post("/config/test-zoho")
async def test_zoho_connection():
    """Test connection to Zoho Creator API."""
    import traceback
    try:
        from main import get_sync_engine
        engine = get_sync_engine()

        # Try to fetch a small number of records to test the connection
        record_count = 0
        async for record in engine.zoho.fetch_records(engine.report_link_name, limit=1):
            record_count += 1
            break

        return {
            "success": True,
            "message": "Successfully connected to Zoho Creator",
            "records_count": record_count if record_count > 0 else None
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Connection failed: {str(e)}",
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc()
        }


@router.get("/debug/images")
async def debug_images():
    """Debug endpoint: Check what images API returns."""
    settings = get_settings()
    client = get_supabase_client(settings.supabase_url, settings.supabase_service_key)

    # Get raw images from database
    result = client.table("images").select("*").limit(3).execute()
    images = result.data

    # Try to create signed URLs and capture any issues
    debug_info = []
    for img in images:
        info = {
            "id": img.get("id"),
            "storage_path": img.get("storage_path"),
            "original_filename": img.get("original_filename"),
        }
        if img.get("storage_path"):
            try:
                signed = client.storage.from_(settings.supabase_storage_bucket).create_signed_url(
                    img["storage_path"], 3600
                )
                info["signed_response"] = signed
                info["url"] = signed.get("signedUrl") or signed.get("signedURL") or signed.get("signed_url")
            except Exception as e:
                info["error"] = str(e)
        debug_info.append(info)

    return {
        "bucket": settings.supabase_storage_bucket,
        "image_count": len(images),
        "debug_info": debug_info,
    }


@router.get("/debug/sample-record")
async def get_sample_record():
    """Debug endpoint: Get a sample record from Zoho to inspect structure."""
    import traceback
    try:
        from main import get_sync_engine
        engine = get_sync_engine()

        async for record in engine.zoho.fetch_records(engine.report_link_name, limit=1):
            # Extract image fields to see what we're getting
            image_fields = engine.zoho.extract_image_fields(record)
            return {
                "success": True,
                "record": record,
                "extracted_image_fields": image_fields,
                "field_names": list(record.keys()),
            }

        return {"success": False, "message": "No records found"}
    except Exception as e:
        return {
            "success": False,
            "message": str(e),
            "traceback": traceback.format_exc()
        }


@router.get("/images/filters")
async def get_filter_values():
    """Get distinct values for filter dropdowns."""
    settings = get_settings()
    client = get_supabase_client(settings.supabase_url, settings.supabase_service_key)

    # Query distinct values from zoho_metadata
    # This is a simplified approach - in production you might want to cache these
    try:
        result = client.table("images").select("zoho_metadata").execute()

        job_captain_timesheets = set()
        project_names = set()
        departments = set()
        photo_origins = set()

        for row in result.data:
            metadata = row.get("zoho_metadata", {})
            if metadata:
                jct = metadata.get("Add_Job_Captain_Time_Sheet_Number")
                if jct:
                    job_captain_timesheets.add(str(jct))
                proj = metadata.get("Project")
                if proj:
                    project_names.add(str(proj))
                dept = metadata.get("Project_Department")
                if dept:
                    departments.add(str(dept))
                origin = metadata.get("Photo_Origin")
                if origin:
                    photo_origins.add(str(origin))

        return {
            "job_captain_timesheets": sorted(list(job_captain_timesheets)),
            "project_names": sorted(list(project_names)),
            "departments": sorted(list(departments)),
            "photo_origins": sorted(list(photo_origins)),
        }
    except Exception as e:
        return {
            "job_captain_timesheets": [],
            "project_names": [],
            "departments": [],
            "photo_origins": [],
        }
