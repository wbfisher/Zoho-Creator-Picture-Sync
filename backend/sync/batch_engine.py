"""
Batch Sync Engine - Manageable, pausable sync with configurable batching.

Features:
- Configurable batch size (records per batch)
- Configurable delay between batches (prevent API overload)
- Pause/Resume capability (saves cursor position)
- Date range filtering
- Dry-run mode (preview without syncing)
- Detailed progress tracking
"""

import asyncio
from datetime import datetime
from typing import Optional
import logging

from supabase import Client

from zoho.client import ZohoCreatorClient
from db.models import ImageRepository, BatchSyncRepository
from sync.processor import ImageProcessor
import mimetypes

logger = logging.getLogger(__name__)

# Global flag for pause requests
_pause_requested = {}
_cancel_requested = {}


def request_pause(batch_id: str):
    """Request a pause for the given batch sync."""
    _pause_requested[batch_id] = True


def request_cancel(batch_id: str):
    """Request a cancel for the given batch sync."""
    _cancel_requested[batch_id] = True


def clear_requests(batch_id: str):
    """Clear pause/cancel requests for the given batch sync."""
    _pause_requested.pop(batch_id, None)
    _cancel_requested.pop(batch_id, None)


class BatchSyncEngine:
    """Engine for running batch syncs with pause/resume support."""

    def __init__(
        self,
        zoho_client: ZohoCreatorClient,
        supabase_client: Client,
        storage_bucket: str,
        image_processor: ImageProcessor,
        report_link_name: str,
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
        self.batch_repo = BatchSyncRepository(supabase_client)

    async def estimate_total_records(
        self,
        date_from: datetime = None,
        date_to: datetime = None,
    ) -> int:
        """Estimate the total number of records to process."""
        count = 0
        async for _ in self.zoho.fetch_records(
            self.report_link_name,
            modified_since=date_from,
            limit=10000,  # Count up to 10k for estimation
        ):
            count += 1
        return count

    async def run_batch_sync(self, batch_id: str) -> dict:
        """
        Run a batch sync session.

        This method processes records in batches, pausing between batches
        and checking for pause/cancel requests.
        """
        clear_requests(batch_id)

        # Get batch sync configuration
        batch_state = await self.batch_repo.get_batch_sync(batch_id)
        if not batch_state:
            raise ValueError(f"Batch sync {batch_id} not found")

        batch_size = batch_state.get("batch_size", 100)
        delay_seconds = batch_state.get("delay_between_batches", 2)
        date_from = self._parse_datetime(batch_state.get("date_from"))
        date_to = self._parse_datetime(batch_state.get("date_to"))
        dry_run = batch_state.get("dry_run", False)
        current_offset = batch_state.get("current_offset", 0)

        # Update status to running
        await self.batch_repo.set_status(batch_id, "running")

        # Stats
        stats = {
            "records_processed": batch_state.get("records_processed", 0),
            "images_synced": batch_state.get("images_synced", 0),
            "images_skipped": batch_state.get("images_skipped", 0),
            "errors": batch_state.get("errors", 0),
            "batches_completed": batch_state.get("batches_completed", 0),
        }
        error_log = []

        logger.info(
            f"Starting batch sync {batch_id}: batch_size={batch_size}, "
            f"offset={current_offset}, dry_run={dry_run}"
        )

        try:
            # Process records in batches
            batch_records = []
            record_index = 0

            async for record in self.zoho.fetch_records(
                self.report_link_name,
                modified_since=date_from,
            ):
                # Skip records before our current offset (for resume)
                if record_index < current_offset:
                    record_index += 1
                    continue

                # Check date_to filter
                if date_to:
                    modified_time = self._parse_zoho_datetime(record.get("Modified_Time"))
                    if modified_time and modified_time > date_to:
                        continue

                batch_records.append(record)
                record_index += 1

                # Process batch when full
                if len(batch_records) >= batch_size:
                    await self._process_batch(
                        batch_id, batch_records, stats, error_log, dry_run
                    )
                    batch_records = []
                    stats["batches_completed"] += 1

                    # Update progress
                    await self.batch_repo.update_batch_sync(
                        batch_id,
                        current_offset=record_index,
                        batches_completed=stats["batches_completed"],
                        records_processed=stats["records_processed"],
                        images_synced=stats["images_synced"],
                        images_skipped=stats["images_skipped"],
                        errors=stats["errors"],
                        last_batch_completed_at=datetime.utcnow(),
                    )

                    # Append new errors
                    if error_log:
                        await self.batch_repo.append_errors(batch_id, error_log)
                        error_log = []

                    # Check for pause/cancel requests
                    if _cancel_requested.get(batch_id):
                        logger.info(f"Batch sync {batch_id} cancelled")
                        await self.batch_repo.set_status(batch_id, "cancelled")
                        return stats

                    if _pause_requested.get(batch_id):
                        logger.info(f"Batch sync {batch_id} paused at offset {record_index}")
                        await self.batch_repo.set_status(batch_id, "paused")
                        return stats

                    # Delay between batches
                    if delay_seconds > 0:
                        logger.debug(f"Waiting {delay_seconds}s before next batch...")
                        await asyncio.sleep(delay_seconds)

            # Process remaining records
            if batch_records:
                await self._process_batch(
                    batch_id, batch_records, stats, error_log, dry_run
                )
                stats["batches_completed"] += 1

                await self.batch_repo.update_batch_sync(
                    batch_id,
                    current_offset=record_index,
                    batches_completed=stats["batches_completed"],
                    records_processed=stats["records_processed"],
                    images_synced=stats["images_synced"],
                    images_skipped=stats["images_skipped"],
                    errors=stats["errors"],
                    last_batch_completed_at=datetime.utcnow(),
                )

                if error_log:
                    await self.batch_repo.append_errors(batch_id, error_log)

            # Complete
            status = "completed" if stats["errors"] == 0 else "completed_with_errors"
            await self.batch_repo.set_status(batch_id, status)
            logger.info(f"Batch sync {batch_id} completed: {stats}")

        except Exception as e:
            logger.exception(f"Batch sync {batch_id} failed: {e}")
            error_log.append({
                "fatal_error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            })
            await self.batch_repo.append_errors(batch_id, error_log)
            await self.batch_repo.set_status(batch_id, "failed")
            raise

        finally:
            clear_requests(batch_id)

        return stats

    async def _process_batch(
        self,
        batch_id: str,
        records: list[dict],
        stats: dict,
        error_log: list,
        dry_run: bool,
    ):
        """Process a batch of records."""
        await self.batch_repo.update_batch_sync(
            batch_id,
            current_batch_started_at=datetime.utcnow(),
        )

        for record in records:
            stats["records_processed"] += 1

            try:
                await self._process_record(record, stats, error_log, dry_run)
            except Exception as e:
                stats["errors"] += 1
                error_log.append({
                    "record_id": record.get("ID"),
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat()
                })
                logger.error(f"Error processing record {record.get('ID')}: {e}")

    async def _process_record(
        self,
        record: dict,
        stats: dict,
        error_log: list,
        dry_run: bool,
    ):
        """Process a single record and sync its images."""
        record_id = str(record.get("ID"))

        # Extract metadata
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

        # Parse timestamps
        zoho_created = self._parse_zoho_datetime(record.get("Added_Time"))
        zoho_modified = self._parse_zoho_datetime(record.get("Modified_Time"))

        # Find image fields
        images = self.zoho.extract_image_fields(record)

        for img_info in images:
            field_name = img_info["field_name"]

            # Check if already synced
            if await self.images_repo.image_exists(record_id, field_name):
                stats["images_skipped"] += 1
                continue

            # Dry run - just count
            if dry_run:
                stats["images_synced"] += 1
                logger.debug(f"[DRY RUN] Would sync: {record_id}/{field_name}")
                continue

            try:
                download_url = img_info["download_url"]

                if not download_url or not download_url.startswith(("http://", "https://")):
                    logger.warning(f"Skipping invalid URL: {download_url}")
                    stats["errors"] += 1
                    error_log.append({
                        "record_id": record_id,
                        "field": field_name,
                        "error": f"Invalid URL: {download_url}",
                    })
                    continue

                # Download
                image_bytes = await self.zoho.download_image(download_url)
                filename = img_info["filename"]

                # Process
                processed_bytes, final_filename, was_processed = self.processor.process_if_needed(
                    image_bytes, filename
                )

                # Build storage path
                date_folder = zoho_created.strftime("%Y-%m") if zoho_created else "unknown"
                cat_folder = category or "uncategorized"
                storage_path = f"{cat_folder}/{date_folder}/{record_id}_{final_filename}"

                # Upload
                content_type = mimetypes.guess_type(final_filename)[0] or "image/webp"
                self.supabase.storage.from_(self.bucket).upload(
                    storage_path,
                    processed_bytes,
                    {"content-type": content_type}
                )

                # Save metadata
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
                logger.error(f"Failed to sync {record_id}/{field_name}: {e}")

    def _parse_datetime(self, value: str) -> Optional[datetime]:
        """Parse ISO datetime string."""
        if not value:
            return None
        try:
            # Handle ISO format with Z suffix
            if value.endswith("Z"):
                value = value[:-1] + "+00:00"
            return datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return None

    def _parse_zoho_datetime(self, value: str) -> Optional[datetime]:
        """Parse Zoho datetime strings in various formats."""
        if not value:
            return None

        formats = [
            "%d-%b-%Y %H:%M:%S",
            "%B %d %Y %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%d-%m-%Y %H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue

        logger.warning(f"Could not parse datetime: {value}")
        return None
