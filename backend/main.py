from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import logging
import os

from config import get_settings
from api.routes import router as api_router
from zoho.auth import ZohoAuth
from zoho.client import ZohoCreatorClient
from sync.engine import SyncEngine
from sync.processor import ImageProcessor
from db.models import get_supabase_client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global sync engine instance
_sync_engine = None
scheduler = AsyncIOScheduler()


def get_sync_engine() -> SyncEngine:
    global _sync_engine
    if _sync_engine is None:
        settings = get_settings()
        
        auth = ZohoAuth(
            client_id=settings.zoho_client_id,
            client_secret=settings.zoho_client_secret,
            refresh_token=settings.zoho_refresh_token,
        )
        
        zoho_client = ZohoCreatorClient(
            auth=auth,
            account_owner=settings.zoho_account_owner_name,
            app_link_name=settings.zoho_app_link_name,
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
            # TODO: Configure these based on your Zoho form
            tag_fields=["Tags", "Category", "Project"],  # Adjust to your fields
            category_field="Category",
            description_field="Description",
        )
    
    return _sync_engine


async def scheduled_sync():
    """Run scheduled sync job."""
    logger.info("Starting scheduled sync")
    try:
        engine = get_sync_engine()
        stats = await engine.run_sync(full_sync=False)
        logger.info(f"Scheduled sync completed: {stats}")
    except Exception as e:
        logger.exception(f"Scheduled sync failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    settings = get_settings()
    
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
    
    yield
    
    # Shutdown
    scheduler.shutdown()


app = FastAPI(
    title="Zoho Pictures Sync",
    description="Sync images from Zoho Creator to Supabase Storage",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(api_router, prefix="/api")

# Serve frontend static files if they exist
frontend_path = os.path.join(os.path.dirname(__file__), "frontend")
frontend_index = os.path.join(frontend_path, "index.html")
if os.path.exists(frontend_index):
    @app.get("/")
    async def serve_frontend():
        return FileResponse(frontend_index)
else:
    @app.get("/")
    async def root():
        return {"message": "Zoho Pictures Sync API", "docs": "/docs"}
