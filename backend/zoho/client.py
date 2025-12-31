import asyncio
import httpx
from typing import AsyncGenerator, Optional
from datetime import datetime
import logging
import time

from .auth import ZohoAuth

logger = logging.getLogger(__name__)

# Try to import tenacity for retry logic
try:
    from tenacity import (
        retry,
        stop_after_attempt,
        wait_exponential,
        retry_if_exception_type,
    )
    TENACITY_AVAILABLE = True
except ImportError:
    TENACITY_AVAILABLE = False
    logger.warning("tenacity not installed - retry logic disabled")


def with_retry(func):
    """Apply retry decorator if tenacity is available."""
    if TENACITY_AVAILABLE:
        return retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.RequestError)),
            reraise=True,
        )(func)
    return func


class RateLimiter:
    """Simple rate limiter for API calls."""

    def __init__(self, calls_per_second: float = 5.0):
        self.min_interval = 1.0 / calls_per_second
        self.last_call = 0.0
        self._lock = asyncio.Lock()

    async def wait(self):
        """Wait if necessary to respect rate limit."""
        async with self._lock:
            now = time.monotonic()
            wait_time = self.min_interval - (now - self.last_call)
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            self.last_call = time.monotonic()


class ZohoCreatorClient:
    BASE_URL = "https://creator.zoho.com/api/v2"

    def __init__(
        self,
        auth: ZohoAuth,
        account_owner: str,
        app_link_name: str,
        rate_limit: float = 5.0,
    ):
        self.auth = auth
        self.account_owner = account_owner
        self.app_link_name = app_link_name
        self.rate_limiter = RateLimiter(rate_limit)
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create a reusable HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0, read=120.0),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
                follow_redirects=True,
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _get_headers(self) -> dict:
        token = await self.auth.get_access_token()
        return {"Authorization": f"Zoho-oauthtoken {token}"}

    async def _make_request(
        self, method: str, url: str, **kwargs
    ) -> httpx.Response:
        """Make a rate-limited HTTP request."""
        await self.rate_limiter.wait()
        client = await self._get_client()
        headers = await self._get_headers()
        kwargs.setdefault("headers", {}).update(headers)

        response = await client.request(method, url, **kwargs)
        response.raise_for_status()
        return response

    async def fetch_records(
        self,
        report_link_name: str,
        modified_since: Optional[datetime] = None,
        page_size: int = 200,
    ) -> AsyncGenerator[dict, None]:
        """Fetch all records from a report, paginated."""
        url = f"{self.BASE_URL}/{self.account_owner}/{self.app_link_name}/report/{report_link_name}"

        from_index = 0
        while True:
            params = {
                "from": from_index,
                "limit": page_size,
            }

            # Add criteria for modified records if provided
            if modified_since:
                criteria = f"Modified_Time >= '{modified_since.strftime('%d-%b-%Y %H:%M:%S')}'"
                params["criteria"] = criteria

            try:
                response = await self._make_request("GET", url, params=params)
                data = response.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    # Rate limited - wait longer and retry
                    logger.warning("Rate limited by Zoho API, waiting 60s...")
                    await asyncio.sleep(60)
                    continue
                raise

            records = data.get("data", [])
            if not records:
                break

            for record in records:
                yield record

            from_index += page_size
            logger.info(f"Fetched {from_index} records so far")

    async def download_image(self, download_url: str) -> bytes:
        """Download an image from Zoho Creator."""
        await self.rate_limiter.wait()
        client = await self._get_client()
        headers = await self._get_headers()

        response = await client.get(download_url, headers=headers)
        response.raise_for_status()
        return response.content

    def extract_image_fields(self, record: dict) -> list[dict]:
        """Extract image/file upload fields from a record.

        Returns list of dicts with: field_name, filename, download_url

        Handles multiple Zoho URL formats:
        - Preview engine URLs (previewengine-accl.zoho.com)
        - Direct download URLs
        - Nested objects with filepath
        """
        images = []

        # Known image field patterns to check
        image_url_patterns = [
            "previewengine",
            "download",
            "zoho.com/image",
            "zoho.com/file",
        ]

        for field_name, value in record.items():
            # Skip system fields
            if field_name in (
                "ID",
                "Added_Time",
                "Modified_Time",
                "Added_User",
                "Modified_User",
            ):
                continue

            download_url = None
            filename = None

            if isinstance(value, str):
                # Check if it's an image URL
                if any(pattern in value.lower() for pattern in image_url_patterns):
                    download_url = value
                    # Try to extract filename from base64 cli-msg if present
                    filename = self._extract_filename_from_url(
                        value, record.get("ID"), field_name
                    )

            elif isinstance(value, dict):
                # Nested object with file info
                download_url = (
                    value.get("download_url")
                    or value.get("filepath")
                    or value.get("url")
                )
                filename = value.get("filename") or value.get("display_value")

                # Sometimes the URL is in a nested 'file' key
                if not download_url and "file" in value:
                    download_url = value["file"]

            elif isinstance(value, list) and len(value) > 0:
                # Multiple files in a single field
                for i, item in enumerate(value):
                    if isinstance(item, str) and any(
                        p in item.lower() for p in image_url_patterns
                    ):
                        images.append(
                            {
                                "field_name": f"{field_name}_{i}",
                                "download_url": item,
                                "filename": f"{record.get('ID', 'unknown')}_{field_name}_{i}",
                            }
                        )
                    elif isinstance(item, dict):
                        item_url = (
                            item.get("download_url")
                            or item.get("filepath")
                            or item.get("url")
                        )
                        if item_url:
                            images.append(
                                {
                                    "field_name": f"{field_name}_{i}",
                                    "download_url": item_url,
                                    "filename": item.get(
                                        "filename",
                                        f"{record.get('ID', 'unknown')}_{field_name}_{i}",
                                    ),
                                }
                            )
                continue  # Already added to images list

            if download_url:
                images.append(
                    {
                        "field_name": field_name,
                        "download_url": download_url,
                        "filename": filename
                        or f"{record.get('ID', 'unknown')}_{field_name}",
                    }
                )

        return images

    def _extract_filename_from_url(
        self, url: str, record_id: str, field_name: str
    ) -> str:
        """Try to extract original filename from Zoho preview URL."""
        import base64
        import json
        from urllib.parse import parse_qs, urlparse

        try:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)

            if "cli-msg" in params:
                cli_msg = params["cli-msg"][0]
                # Decode base64 JSON
                decoded = base64.b64decode(cli_msg).decode("utf-8")
                data = json.loads(decoded)

                if "filepath" in data:
                    # filepath is like "1765935737819997_Image.HEIC"
                    return data["filepath"]
        except Exception:
            pass

        return f"{record_id}_{field_name}"
