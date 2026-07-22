from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import logging
import os

from config import get_settings
from api.routes import router as api_router
from api.auth_routes import router as auth_router, get_current_user
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
            # TODO: Configure these based on your Zoho form
            tag_fields=["Tags", "Category", "Project1"],  # Adjust to your fields
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


# Authentication Middleware
class AuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce authentication on protected routes.

    - /api/auth/* routes are always accessible (login/callback/check)
    - /api/health is accessible (for health checks)
    - All other /api/* routes require authentication
    - Frontend routes (/, /gallery, etc.) redirect to /login if not authenticated
    """

    # Routes that don't require authentication
    PUBLIC_PATHS = {
        "/api/auth/login",
        "/api/auth/callback",
        "/api/auth/check",
        "/api/auth/logout",
        "/api/health",
        "/login",
    }

    # Prefixes that are always public
    PUBLIC_PREFIXES = ("/assets/", "/favicon")

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Always allow public paths
        if path in self.PUBLIC_PATHS:
            return await call_next(request)

        # Always allow static assets
        for prefix in self.PUBLIC_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        # Check authentication
        user = get_current_user(request)

        if not user:
            # For API routes, return 401
            if path.startswith("/api/"):
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Not authenticated"},
                )
            # For frontend routes, redirect to login
            return RedirectResponse(url="/login", status_code=302)

        # User is authenticated, continue
        return await call_next(request)


# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add auth middleware (after CORS to ensure CORS headers are set)
app.add_middleware(AuthMiddleware)

# API routes
app.include_router(auth_router, prefix="/api")
app.include_router(api_router, prefix="/api")

# Serve frontend static files if they exist
frontend_dist = os.path.join(os.path.dirname(__file__), "frontend", "dist")
frontend_index = os.path.join(frontend_dist, "index.html")
if os.path.exists(frontend_dist):
    # Mount assets directory for JS/CSS files
    assets_path = os.path.join(frontend_dist, "assets")
    if os.path.exists(assets_path):
        app.mount("/assets", StaticFiles(directory=assets_path), name="assets")

    @app.get("/")
    async def serve_frontend():
        return FileResponse(frontend_index)

    # Catch-all for SPA routing
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Don't intercept API routes
        if full_path.startswith("api/"):
            return {"detail": "Not found"}
        return FileResponse(frontend_index)
else:
    @app.get("/")
    async def root():
        return {"message": "Zoho Pictures Sync API", "docs": "/docs"}

