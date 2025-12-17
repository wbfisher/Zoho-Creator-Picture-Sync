from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from fastapi.responses import StreamingResponse
from typing import Optional
from datetime import datetime
from pydantic import BaseModel
import io
import zipfile

from ..db.models import ImageRepository, SyncRunRepository, get_supabase_client
from ..config import get_settings, update_settings

router = APIRouter()


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
    max_records: Optional[int] = Query(None, description="Limit number of records to sync (for testing)")
):
    """Trigger a sync operation."""
    from ..main import get_sync_engine

    images_repo, runs_repo = get_repos()
    recent_runs = await runs_repo.get_recent_runs(limit=1)

    if recent_runs and recent_runs[0].get("status") == "running":
        raise HTTPException(status_code=409, detail="Sync already in progress")

    # Create run first to get ID
    run_id = await runs_repo.start_run()

    async def run_sync():
        engine = get_sync_engine()
        await engine.run_sync(full_sync=full_sync, run_id=run_id, max_records=max_records)

    background_tasks.add_task(run_sync)

    return {"message": "Sync started", "run_id": run_id, "full_sync": full_sync, "max_records": max_records}


@router.get("/images")
async def list_images(
    job_captain_timesheet: Optional[str] = None,
    project_name: Optional[str] = None,
    department: Optional[str] = None,
    search: Optional[str] = None,
    tags: Optional[str] = Query(None, description="Comma-separated tags to filter by"),
    category: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List synced images with optional filtering."""
    images_repo, _ = get_repos()

    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    images, total = await images_repo.get_images(
        job_captain_timesheet=job_captain_timesheet,
        project_name=project_name,
        department=department,
        search=search,
        tags=tag_list,
        category=category,
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
            signed = client.storage.from_(settings.supabase_storage_bucket).create_signed_url(
                img["storage_path"], 3600  # 1 hour expiry
            )
            img["url"] = signed.get("signedURL")

    return {"items": images, "total": total, "limit": limit, "offset": offset}


@router.get("/images/filters")
async def get_filter_values():
    """Get distinct values for filter dropdowns."""
    images_repo, _ = get_repos()
    return await images_repo.get_filter_values()


class DownloadRequest(BaseModel):
    image_ids: list[str]


@router.post("/images/download")
async def download_images(request: DownloadRequest):
    """Download multiple images as a ZIP file."""
    if not request.image_ids:
        raise HTTPException(status_code=400, detail="No images specified")

    if len(request.image_ids) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 images per download")

    settings = get_settings()
    client = get_supabase_client(settings.supabase_url, settings.supabase_service_key)
    images_repo = ImageRepository(client)

    # Create ZIP in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for image_id in request.image_ids:
            # Get image info
            result = client.table("images").select("*").eq("id", image_id).execute()
            if not result.data:
                continue

            img = result.data[0]
            if not img.get("storage_path"):
                continue

            # Download from storage
            try:
                file_data = client.storage.from_(settings.supabase_storage_bucket).download(
                    img["storage_path"]
                )
                filename = img.get("original_filename") or f"{image_id}.webp"
                zf.writestr(filename, file_data)
            except Exception as e:
                continue

    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=zoho-pictures.zip"}
    )


@router.get("/runs")
async def list_runs(limit: int = Query(20, ge=1, le=100)):
    """List recent sync runs."""
    _, runs_repo = get_repos()
    runs = await runs_repo.get_recent_runs(limit=limit)
    return runs


@router.get("/config")
async def get_config():
    """Get current configuration (sensitive values masked)."""
    settings = get_settings()
    return settings.to_safe_dict()


class ConfigUpdate(BaseModel):
    zoho_client_id: Optional[str] = None
    zoho_client_secret: Optional[str] = None
    zoho_refresh_token: Optional[str] = None
    zoho_account_owner_name: Optional[str] = None
    zoho_app_link_name: Optional[str] = None
    zoho_report_link_name: Optional[str] = None
    field_job_captain_timesheet: Optional[str] = None
    field_project_name: Optional[str] = None
    field_department: Optional[str] = None
    field_tags: Optional[str] = None
    field_description: Optional[str] = None
    sync_cron: Optional[str] = None
    image_max_size_mb: Optional[int] = None
    image_max_dimension: Optional[int] = None
    image_quality: Optional[int] = None
    supabase_storage_bucket: Optional[str] = None


@router.put("/config")
async def update_config_endpoint(config: ConfigUpdate):
    """Update configuration."""
    updates = {k: v for k, v in config.model_dump().items() if v is not None}

    # Don't update credentials if they're masked values
    for key in ["zoho_client_id", "zoho_client_secret", "zoho_refresh_token"]:
        if updates.get(key) == "***":
            del updates[key]

    updated = update_settings(updates)
    return updated.to_safe_dict()


@router.post("/config/test-zoho")
async def test_zoho_connection():
    """Test Zoho Creator connection with current credentials."""
    settings = get_settings()

    if not all([settings.zoho_client_id, settings.zoho_client_secret, settings.zoho_refresh_token]):
        return {"success": False, "message": "Zoho credentials not configured"}

    try:
        from ..zoho.auth import ZohoAuth
        from ..zoho.client import ZohoCreatorClient

        auth = ZohoAuth(
            settings.zoho_client_id,
            settings.zoho_client_secret,
            settings.zoho_refresh_token
        )

        client = ZohoCreatorClient(
            auth,
            settings.zoho_account_owner_name,
            settings.zoho_app_link_name
        )

        # Try to fetch first page of records
        count = 0
        async for _ in client.fetch_records(settings.zoho_report_link_name):
            count += 1
            if count >= 5:  # Just test first few records
                break

        return {
            "success": True,
            "message": f"Connected successfully! Found records in report.",
            "records_count": count
        }

    except Exception as e:
        return {"success": False, "message": str(e)}


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
