import asyncio
from datetime import datetime
from typing import Optional
import logging
import mimetypes

from supabase import Client

from zoho.client import ZohoCreatorClient
from db.models import ImageRepository, SyncRunRepository
from sync.processor import ImageProcessor

logger = logging.getLogger(__name__)


class SyncEngine:
    def __init__(
        self,
        zoho_client: ZohoCreatorClient,
        supabase_client: Client,
        storage_bucket: str,
        image_processor: ImageProcessor,
        report_link_name: str,
        # Customize these based on your Zoho form fields
        tag_fields: list[str] = None,
        category_field: str = None,
        description_field: str = None,
    ):
        self.zoho = zoho_client
        self.supabase = supabase_client
        self.bucket = storage_bucket
        self.processor = image_processor
        self.report_link_name = report_link_name
        
        self.tag_fields = tag_fields or []
        self.category_field = category_field
        self.description_field = description_field
        
        self.images_repo = ImageRepository(supabase_client)
        self.runs_repo = SyncRunRepository(supabase_client)
    
    async def run_sync(self, full_sync: bool = False, max_records: int = None, run_id: str = None) -> dict:
        """Run a sync operation.

        Args:
            full_sync: If True, sync all records. If False, only sync since last run.
            max_records: If set, limit the number of records to process.
            run_id: If provided, use existing run_id instead of creating a new one.
        """
        if run_id is None:
            run_id = await self.runs_repo.start_run()

        stats = {
            "records_processed": 0,
            "images_synced": 0,
            "images_skipped": 0,
            "errors": 0,
        }
        error_log = []

        try:
            # Note: We don't use modified_since criteria because some Zoho reports
            # don't support it (returns 404). Instead, we always fetch all records
            # and skip images that already exist in the database (via image_exists check).
            logger.info(f"Starting sync (full={full_sync}, max_records={max_records})")

            async for record in self.zoho.fetch_records(self.report_link_name):
                stats["records_processed"] += 1

                # Check if we've reached the max_records limit
                if max_records and stats["records_processed"] > max_records:
                    logger.info(f"Reached max_records limit ({max_records}), stopping sync")
                    break

                try:
                    await self._process_record(record, stats, error_log)
                except Exception as e:
                    stats["errors"] += 1
                    error_log.append({
                        "record_id": record.get("ID"),
                        "error": str(e),
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    logger.error(f"Error processing record {record.get('ID')}: {e}")

                # Update progress periodically
                if stats["records_processed"] % 50 == 0:
                    await self.runs_repo.update_run(run_id, **stats)

            status = "completed" if stats["errors"] == 0 else "completed_with_errors"
            await self.runs_repo.complete_run(run_id, status, error_log if error_log else None)

        except Exception as e:
            logger.exception(f"Sync failed: {e}")
            error_log.append({"fatal_error": str(e), "timestamp": datetime.utcnow().isoformat()})
            await self.runs_repo.complete_run(run_id, "failed", error_log)
            raise

        logger.info(f"Sync completed: {stats}")
        return stats
    
    async def _process_record(self, record: dict, stats: dict, error_log: list):
        """Process a single Zoho record and sync its images."""
        record_id = str(record.get("ID"))
        
        # Extract metadata based on configured fields
        tags = []
        for field in self.tag_fields:
            value = record.get(field)
            if value:
                if isinstance(value, list):
                    tags.extend(value)
                else:
                    tags.append(str(value))
        
        category = record.get(self.category_field) if self.category_field else None
        description = record.get(self.description_field) if self.description_field else None
        
        # Parse Zoho timestamps
        zoho_created = self._parse_zoho_datetime(record.get("Added_Time"))
        zoho_modified = self._parse_zoho_datetime(record.get("Modified_Time"))
        
        # Find and process image fields
        images = self.zoho.extract_image_fields(record)
        
        for img_info in images:
            field_name = img_info["field_name"]
            
            # Check if already synced (skip if not modified)
            if await self.images_repo.image_exists(record_id, field_name):
                stats["images_skipped"] += 1
                continue
            
            try:
                # Download image
                download_url = img_info["download_url"]
                logger.debug(f"Downloading image from URL: {download_url}")

                # Skip if URL is empty or invalid
                if not download_url or not download_url.startswith(("http://", "https://")):
                    logger.warning(f"Skipping invalid URL for {record_id}/{field_name}: {download_url}")
                    stats["errors"] += 1
                    error_log.append({
                        "record_id": record_id,
                        "field": field_name,
                        "error": f"Invalid URL: {download_url}",
                    })
                    continue

                image_bytes = await self.zoho.download_image(download_url)
                filename = img_info["filename"]
                
                # Process if needed
                processed_bytes, final_filename, was_processed = self.processor.process_if_needed(
                    image_bytes, filename
                )
                
                # Build storage path: category/YYYY-MM/filename
                date_folder = zoho_created.strftime("%Y-%m") if zoho_created else "unknown"
                cat_folder = category or "uncategorized"
                storage_path = f"{cat_folder}/{date_folder}/{record_id}_{final_filename}"
                
                # Upload to Supabase Storage
                content_type = mimetypes.guess_type(final_filename)[0] or "image/webp"
                self.supabase.storage.from_(self.bucket).upload(
                    storage_path,
                    processed_bytes,
                    {"content-type": content_type}
                )
                
                # Save metadata to database
                await self.images_repo.upsert_image(
                    zoho_record_id=record_id,
                    field_name=field_name,
                    storage_path=storage_path,
                    original_filename=filename,
                    file_size_bytes=len(processed_bytes),
                    was_processed=was_processed,
                    tags=tags,
                    category=category,
                    description=description,
                    zoho_metadata=record,
                    zoho_created_at=zoho_created,
                    zoho_modified_at=zoho_modified,
                )
                
                stats["images_synced"] += 1
                logger.debug(f"Synced image: {storage_path}")
                
            except Exception as e:
                stats["errors"] += 1
                error_log.append({
                    "record_id": record_id,
                    "field": field_name,
                    "error": str(e),
                })
                logger.error(f"Failed to sync image {record_id}/{field_name}: {e}")
    
    def _parse_zoho_datetime(self, value: str) -> Optional[datetime]:
        """Parse Zoho datetime strings."""
        if not value:
            return None

        formats = [
            "%d-%b-%Y %H:%M:%S",      # 16-Dec-2025 17:08:38
            "%B %d %Y %H:%M:%S",       # December 16 2025 17:08:38
            "%Y-%m-%dT%H:%M:%S",       # 2025-12-16T17:08:38
            "%d-%m-%Y %H:%M:%S",       # 16-12-2025 17:08:38
            "%Y-%m-%d %H:%M:%S",       # 2025-12-16 17:08:38
        ]

        for fmt in formats:
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue

        logger.warning(f"Could not parse datetime: {value}")
        return None
