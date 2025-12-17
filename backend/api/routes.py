from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from typing import Optional
from datetime import datetime

from ..db.models import ImageRepository, SyncRunRepository, get_supabase_client
from ..config import get_settings

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
    full_sync: bool = Query(False, description="Run full sync instead of incremental")
):
    """Trigger a sync operation."""
    from ..main import get_sync_engine
    
    images_repo, runs_repo = get_repos()
    recent_runs = await runs_repo.get_recent_runs(limit=1)
    
    if recent_runs and recent_runs[0].get("status") == "running":
        raise HTTPException(status_code=409, detail="Sync already in progress")
    
    async def run_sync():
        engine = get_sync_engine()
        await engine.run_sync(full_sync=full_sync)
    
    background_tasks.add_task(run_sync)
    
    return {"message": "Sync started", "full_sync": full_sync}


@router.get("/images")
async def list_images(
    tags: Optional[str] = Query(None, description="Comma-separated tags to filter by"),
    category: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List synced images with optional filtering."""
    images_repo, _ = get_repos()
    
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    
    images = await images_repo.get_images(
        tags=tag_list,
        category=category,
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
    
    return {"images": images, "count": len(images)}


@router.get("/runs")
async def list_runs(limit: int = Query(20, ge=1, le=100)):
    """List recent sync runs."""
    _, runs_repo = get_repos()
    runs = await runs_repo.get_recent_runs(limit=limit)
    return {"runs": runs}


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
