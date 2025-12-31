from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import logging
import os

from .config import get_settings
from .api.routes import router as api_router
from .zoho.auth import ZohoAuth
from .zoho.client import ZohoCreatorClient
from .sync.engine import SyncEngine
from .sync.processor import ImageProcessor
from .db.models import get_supabase_client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global sync engine instance
_sync_engine = None
scheduler = AsyncIOScheduler()


def reset_sync_engine():
    """Reset the sync engine to pick up new settings."""
    global _sync_engine
    _sync_engine = None


def get_sync_engine() -> SyncEngine:
    global _sync_engine
    if _sync_engine is None:
        settings = get_settings()

        # Check if credentials are configured
        if not settings.zoho_client_id or not settings.zoho_refresh_token:
            logger.warning("Zoho credentials not configured - sync engine not initialized")
            return None

        auth = ZohoAuth(
            client_id=settings.zoho_client_id,
            client_secret=settings.zoho_client_secret,
            refresh_token=settings.zoho_refresh_token,
        )

        zoho_client = ZohoCreatorClient(
            auth=auth,
            account_owner=settings.zoho_account_owner_name,
            app_link_name=settings.zoho_app_link_name,
            rate_limit=settings.sync_rate_limit,
        )

        supabase = get_supabase_client(
            settings.supabase_url,
            settings.supabase_service_key,
        )

        processor = ImageProcessor(
            max_dimension=settings.image_max_dimension,
            quality=settings.image_quality,
            max_size_mb=settings.image_max_size_mb,
        )

        _sync_engine = SyncEngine(
            zoho_client=zoho_client,
            supabase_client=supabase,
            storage_bucket=settings.supabase_storage_bucket,
            image_processor=processor,
            report_link_name=settings.zoho_report_link_name,
        )

    return _sync_engine


async def scheduled_sync():
    """Run scheduled sync job."""
    logger.info("Starting scheduled sync")
    try:
        engine = get_sync_engine()
        if engine:
            stats = await engine.run_sync(full_sync=False)
            logger.info(f"Scheduled sync completed: {stats}")
        else:
            logger.warning("Sync engine not available - skipping scheduled sync")
    except Exception as e:
        logger.exception(f"Scheduled sync failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    settings = get_settings()

    # Only schedule if credentials are configured
    if settings.zoho_client_id and settings.zoho_refresh_token:
        # Parse cron expression and schedule job
        # Default: "0 2 * * *" = 2 AM daily
        cron_parts = settings.sync_cron.split()
        if len(cron_parts) == 5:
            trigger = CronTrigger(
                minute=cron_parts[0],
                hour=cron_parts[1],
                day=cron_parts[2],
                month=cron_parts[3],
                day_of_week=cron_parts[4],
            )
            scheduler.add_job(scheduled_sync, trigger, id="daily_sync")
            scheduler.start()
            logger.info(f"Scheduled sync job: {settings.sync_cron}")
    else:
        logger.info("Zoho credentials not configured - scheduler not started")

    yield

    # Shutdown
    if scheduler.running:
        scheduler.shutdown()


app = FastAPI(
    title="Zoho Pictures Sync",
    description="Sync images from Zoho Creator to Supabase Storage",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(api_router, prefix="/api")

# Determine frontend path (works in both dev and Docker)
frontend_path = None
possible_paths = [
    os.path.join(os.path.dirname(__file__), "..", "frontend", "dist"),  # Dev
    "/app/frontend/dist",  # Docker
]
for path in possible_paths:
    if os.path.exists(path) and os.path.isdir(path):
        frontend_path = os.path.abspath(path)
        break

if frontend_path:
    logger.info(f"Serving frontend from: {frontend_path}")

    # Mount static assets
    assets_path = os.path.join(frontend_path, "assets")
    if os.path.exists(assets_path):
        app.mount("/assets", StaticFiles(directory=assets_path), name="assets")

    # Serve index.html for SPA routes
    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        # Don't intercept API routes
        if full_path.startswith("api/"):
            return {"detail": "Not found"}

        # Serve static files if they exist
        file_path = os.path.join(frontend_path, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)

        # Otherwise serve index.html for SPA routing
        return FileResponse(os.path.join(frontend_path, "index.html"))
else:
    logger.info("Frontend not found - API only mode")

    @app.get("/")
    async def root():
        return {
            "message": "Zoho Pictures Sync API",
            "docs": "/docs",
            "health": "/api/health"
        }
