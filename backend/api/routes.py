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
    date_from: Optional[str] = Query(None, description="Filter by photo date from (ISO format)"),
    date_to: Optional[str] = Query(None, description="Filter by photo date to (ISO format)"),
    sort_by: Optional[str] = Query("zoho_created_at", description="Sort by: zoho_created_at, synced_at, original_filename"),
    sort_order: Optional[str] = Query("desc", description="Sort order: asc or desc"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List synced images with optional filtering and sorting."""
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
        sort_by=sort_by or "zoho_created_at",
        sort_order=sort_order or "desc",
        limit=limit,
        offset=offset,
    )

    # Add URLs for image access
    settings = get_settings()

    # Use public URLs (no API call needed - instant!)
    # Format: https://<project>.supabase.co/storage/v1/object/public/<bucket>/<path>
    base_url = f"{settings.supabase_url}/storage/v1/object/public/{settings.supabase_storage_bucket}"

    for img in images:
        if img.get("storage_path"):
            img["url"] = f"{base_url}/{img['storage_path']}"

    # Extract categorization fields from zoho_metadata for frontend
    for img in images:
        metadata = img.get("zoho_metadata", {})
        if not img.get("job_captain_timesheet"):
            img["job_captain_timesheet"] = metadata.get("Add_Job_Captain_Time_Sheet_Number")
        if not img.get("project_name"):
            img["project_name"] = metadata.get("Project1")
        if not img.get("department"):
            img["department"] = metadata.get("Project_Department1")
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
# Quick Batch Sync - "Download Next N Photos"
# =============================================================================

@router.get("/sync/quick-batch/status")
async def get_quick_batch_status():
    """Get info for quick batch sync (oldest synced photo date)."""
    images_repo, _ = get_repos()
    oldest_date = await images_repo.get_oldest_image_date()
    stats = await images_repo.get_stats()

    return {
        "oldest_synced_date": oldest_date.isoformat() if oldest_date else None,
        "total_synced": stats.get("total_images", 0),
    }


@router.post("/sync/quick-batch")
async def start_quick_batch(
    background_tasks: BackgroundTasks,
    count: int = Query(100, ge=10, le=500, description="Number of photos to download"),
):
    """
    Quick batch sync - automatically continues from oldest synced photo.

    This endpoint:
    1. Finds the oldest synced photo's creation date
    2. Fetches photos from Zoho that are older than that date
    3. Syncs up to 'count' photos

    No date configuration needed - just click and go!
    """
    from main import get_sync_engine

    images_repo, runs_repo = get_repos()

    # Check if sync is already running
    recent_runs = await runs_repo.get_recent_runs(limit=1)
    if recent_runs and recent_runs[0].get("status") == "running":
        raise HTTPException(status_code=409, detail="Sync already in progress")

    # Get oldest synced photo date
    oldest_date = await images_repo.get_oldest_image_date()

    # Create run record
    run_id = await runs_repo.start_run()

    # Run sync in background
    async def run_quick_sync():
        engine = get_sync_engine()
        await engine.run_sync(
            full_sync=True,  # Don't use modified_since logic
            max_records=count,
            run_id=run_id,
            added_before=oldest_date,  # Only get photos older than what we have
        )

    background_tasks.add_task(run_quick_sync)

    return {
        "message": f"Downloading up to {count} photos" + (
            f" older than {oldest_date.strftime('%b %d, %Y')}" if oldest_date else " (starting from most recent)"
        ),
        "run_id": run_id,
        "count": count,
        "oldest_synced_date": oldest_date.isoformat() if oldest_date else None,
    }


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
    try:
        batch_repo = get_batch_repo()

        # Get active batch sync
        active = await batch_repo.get_active_batch_sync()

        # Get recent batch syncs
        recent = await batch_repo.get_recent_batch_syncs(limit=5)

        return {
            "active": active,
            "recent": recent,
        }
    except Exception as e:
        # Handle case where batch_sync_state table doesn't exist yet
        import logging
        logging.warning(f"Batch sync status fetch failed (table may not exist): {e}")
        return {
            "active": None,
            "recent": [],
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
        "field_project_name": "Project1",
        "field_department": "Project_Department1",
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

    # Public URL base
    base_url = f"{settings.supabase_url}/storage/v1/object/public/{settings.supabase_storage_bucket}"

    debug_info = []
    for img in images:
        info = {
            "id": img.get("id"),
            "storage_path": img.get("storage_path"),
            "original_filename": img.get("original_filename"),
        }
        if img.get("storage_path"):
            info["public_url"] = f"{base_url}/{img['storage_path']}"
        debug_info.append(info)

    return {
        "bucket": settings.supabase_storage_bucket,
        "base_url": base_url,
        "image_count": len(images),
        "debug_info": debug_info,
    }


@router.get("/debug/counts")
async def debug_counts():
    """Debug endpoint: Get detailed count breakdown of images in database."""
    settings = get_settings()
    client = get_supabase_client(settings.supabase_url, settings.supabase_service_key)

    # Total images
    total_result = client.table("images").select("id", count="exact").execute()
    total_images = total_result.count or 0

    # Unique Zoho records (to see records vs images ratio)
    all_images = client.table("images").select("zoho_record_id, field_name, synced_at").execute()

    unique_records = set()
    field_names = {}
    for img in all_images.data:
        unique_records.add(img.get("zoho_record_id"))
        field = img.get("field_name", "unknown")
        field_names[field] = field_names.get(field, 0) + 1

    # Recent sync runs
    runs_result = client.table("sync_runs").select("*").order("started_at", desc=True).limit(5).execute()

    return {
        "total_images": total_images,
        "unique_zoho_records": len(unique_records),
        "images_per_record_avg": round(total_images / len(unique_records), 2) if unique_records else 0,
        "field_name_breakdown": field_names,
        "recent_sync_runs": [
            {
                "id": r.get("id")[:8],
                "status": r.get("status"),
                "records_processed": r.get("records_processed"),
                "images_synced": r.get("images_synced"),
                "images_skipped": r.get("images_skipped"),
                "errors": r.get("errors"),
                "started_at": r.get("started_at"),
            }
            for r in runs_result.data
        ],
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


@router.get("/debug/db-sample")
async def get_db_sample():
    """Debug endpoint: Get a sample image from database to inspect zoho_metadata structure."""
    settings = get_settings()
    client = get_supabase_client(settings)

    result = client.table("images").select("id, zoho_metadata").limit(1).execute()

    if result.data and len(result.data) > 0:
        metadata = result.data[0].get("zoho_metadata", {})
        project1 = metadata.get("Project1")
        dept = metadata.get("Project_Department1")
        timesheet = metadata.get("Add_Job_Captain_Time_Sheet_Number")

        return {
            "success": True,
            "image_id": result.data[0]["id"],
            "Project1_raw": project1,
            "Project1_type": type(project1).__name__,
            "Project1_display_value": project1.get("display_value") if isinstance(project1, dict) else None,
            "Department_raw": dept,
            "Department_type": type(dept).__name__,
            "Timesheet_raw": timesheet,
            "Timesheet_type": type(timesheet).__name__,
        }

    return {"success": False, "message": "No images in database"}


# Simple in-memory cache for filter values
_filter_cache = {
    "data": None,
    "timestamp": 0,
}
_FILTER_CACHE_TTL = 600  # 10 minutes (filter values rarely change)


@router.get("/images/filters")
async def get_filter_values():
    """Get distinct values for filter dropdowns (cached for 10 minutes)."""
    import time

    # Return cached data if still valid
    if _filter_cache["data"] and (time.time() - _filter_cache["timestamp"]) < _FILTER_CACHE_TTL:
        return _filter_cache["data"]

    settings = get_settings()
    client = get_supabase_client(settings.supabase_url, settings.supabase_service_key)

    try:
        # Try to use the optimized RPC function first (if it exists)
        try:
            rpc_result = client.rpc("get_image_filter_values").execute()
            if rpc_result.data:
                result_data = rpc_result.data
                _filter_cache["data"] = result_data
                _filter_cache["timestamp"] = time.time()
                return result_data
        except Exception:
            pass  # RPC function doesn't exist, fall back to manual query

        # Fallback: Query with pagination to handle large datasets
        # Only fetch necessary data, process in chunks
        job_captain_timesheets = set()
        project_names = set()
        departments = set()
        photo_origins = set()

        offset = 0
        batch_size = 5000
        max_batches = 10  # Safety limit: 50k records max

        for _ in range(max_batches):
            result = client.table("images").select("zoho_metadata").range(offset, offset + batch_size - 1).execute()

            if not result.data:
                break

            for row in result.data:
                metadata = row.get("zoho_metadata", {})
                if metadata:
                    jct = metadata.get("Add_Job_Captain_Time_Sheet_Number")
                    if jct:
                        # Handle Zoho lookup field (dict with display_value) or plain string
                        if isinstance(jct, dict):
                            ts_number = jct.get("display_value") or jct.get("Time_Sheet_Number_New") or str(jct.get("ID", ""))
                            if ts_number:
                                job_captain_timesheets.add(ts_number)
                        else:
                            job_captain_timesheets.add(str(jct))
                    proj = metadata.get("Project1")
                    if proj:
                        # Handle Zoho lookup field or plain string
                        if isinstance(proj, dict):
                            proj_name = proj.get("display_value") or str(proj.get("ID", ""))
                            if proj_name:
                                project_names.add(proj_name)
                        else:
                            project_names.add(str(proj))
                    dept = metadata.get("Project_Department1")
                    if dept:
                        # Handle Zoho lookup field or plain string
                        if isinstance(dept, dict):
                            dept_name = dept.get("display_value") or str(dept.get("ID", ""))
                            if dept_name:
                                departments.add(dept_name)
                        else:
                            departments.add(str(dept))
                    origin = metadata.get("Photo_Origin")
                    if origin:
                        photo_origins.add(str(origin))

            if len(result.data) < batch_size:
                break  # No more data

            offset += batch_size

        result_data = {
            "job_captain_timesheets": sorted(list(job_captain_timesheets)),
            "project_names": sorted(list(project_names)),
            "departments": sorted(list(departments)),
            "photo_origins": sorted(list(photo_origins)),
        }

        # Cache the result
        _filter_cache["data"] = result_data
        _filter_cache["timestamp"] = time.time()

        return result_data
    except Exception as e:
        import logging
        logging.warning(f"Failed to fetch filter values: {e}")
        return {
            "job_captain_timesheets": [],
            "project_names": [],
            "departments": [],
            "photo_origins": [],
        }
