from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime

from db.models import ImageRepository, SyncRunRepository, get_supabase_client
from config import get_settings

router = APIRouter()


def extract_zoho_value(value: Any) -> Optional[str]:
    """
    Extract a displayable string from a Zoho field value.
    Handles lookup fields which return objects like {display_value: "...", ID: "..."}
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value if value else None
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        # Zoho lookup fields return objects with display_value
        if "display_value" in value:
            return extract_zoho_value(value["display_value"])
        if "name" in value:
            return extract_zoho_value(value["name"])
        # Return first non-ID string value as fallback
        for k, v in value.items():
            if k not in ("ID", "id") and isinstance(v, str) and v:
                return v
        return None
    if isinstance(value, list) and len(value) > 0:
        # Handle multi-select or array fields
        return extract_zoho_value(value[0])
    return str(value) if value else None


class ConfigUpdate(BaseModel):
    """Configuration update request (read-only for env-based settings)"""
    sync_cron: Optional[str] = None
    image_max_size_mb: Optional[int] = None
    image_max_dimension: Optional[int] = None
    image_quality: Optional[int] = None


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
        # Uses extract_zoho_value to handle Zoho lookup objects
        metadata = img.get("zoho_metadata", {}) or {}
        if not img.get("job_captain_timesheet"):
            img["job_captain_timesheet"] = extract_zoho_value(metadata.get("Add_Job_Captain_Time_Sheet_Number"))
        if not img.get("project_name"):
            img["project_name"] = extract_zoho_value(metadata.get("Project"))
        if not img.get("department"):
            img["department"] = extract_zoho_value(metadata.get("Project_Department"))

    # Get total count for pagination
    total_count = await images_repo.get_count(
        tags=tag_list,
        category=category,
        job_captain_timesheet=job_captain_timesheet,
        project_name=project_name,
        department=department,
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

        for row in result.data:
            metadata = row.get("zoho_metadata", {})
            if metadata:
                # Use extract_zoho_value to handle lookup objects
                jct = extract_zoho_value(metadata.get("Add_Job_Captain_Time_Sheet_Number"))
                if jct:
                    job_captain_timesheets.add(jct)
                proj = extract_zoho_value(metadata.get("Project"))
                if proj:
                    project_names.add(proj)
                dept = extract_zoho_value(metadata.get("Project_Department"))
                if dept:
                    departments.add(dept)

        return {
            "job_captain_timesheets": sorted(list(job_captain_timesheets)),
            "project_names": sorted(list(project_names)),
            "departments": sorted(list(departments)),
        }
    except Exception as e:
        return {
            "job_captain_timesheets": [],
            "project_names": [],
            "departments": [],
        }
