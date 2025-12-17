import httpx
from typing import AsyncGenerator, Optional
from datetime import datetime
import logging

from .auth import ZohoAuth

logger = logging.getLogger(__name__)


class ZohoCreatorClient:
    BASE_URL = "https://creator.zoho.com/api/v2"
    
    def __init__(self, auth: ZohoAuth, account_owner: str, app_link_name: str):
        self.auth = auth
        self.account_owner = account_owner
        self.app_link_name = app_link_name
    
    async def _get_headers(self) -> dict:
        token = await self.auth.get_access_token()
        return {"Authorization": f"Zoho-oauthtoken {token}"}
    
    async def fetch_records(
        self,
        report_link_name: str,
        modified_since: Optional[datetime] = None,
        page_size: int = 200,
        limit: Optional[int] = None
    ) -> AsyncGenerator[dict, None]:
        """Fetch records from a report, paginated.

        Args:
            report_link_name: Name of the Zoho report to fetch from
            modified_since: Optional datetime to filter records modified after this time
            page_size: Number of records per API call
            limit: Optional total limit of records to return
        """
        url = f"{self.BASE_URL}/{self.account_owner}/{self.app_link_name}/report/{report_link_name}"

        from_index = 0
        total_yielded = 0
        while True:
            params = {
                "from": from_index,
                "limit": page_size,
            }

            # Add criteria for modified records if provided
            if modified_since:
                criteria = f"Modified_Time >= '{modified_since.strftime('%d-%b-%Y %H:%M:%S')}'"
                params["criteria"] = criteria

            async with httpx.AsyncClient(timeout=60) as client:
                headers = await self._get_headers()
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()

            records = data.get("data", [])
            if not records:
                break

            for record in records:
                yield record
                total_yielded += 1
                if limit and total_yielded >= limit:
                    return

            from_index += page_size
            logger.info(f"Fetched {from_index} records so far")
    
    async def download_image(self, download_url: str) -> bytes:
        """Download an image from Zoho Creator."""
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            headers = await self._get_headers()
            response = await client.get(download_url, headers=headers)
            response.raise_for_status()
            return response.content
    
    def _normalize_url(self, url: str) -> str:
        """Ensure URL has proper protocol."""
        if not url:
            return url
        url = url.strip()
        if url.startswith("//"):
            return f"https:{url}"
        if not url.startswith(("http://", "https://")):
            # Assume it's a Zoho URL if it contains zoho
            if "zoho" in url.lower():
                return f"https://{url}"
            # Otherwise it might be a relative path - prefix with Zoho Creator base
            return f"https://creator.zoho.com{url}" if url.startswith("/") else url
        return url

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
            ".jpg", ".jpeg", ".png", ".gif", ".heic", ".webp",
        ]

        for field_name, value in record.items():
            # Skip system fields
            if field_name in ("ID", "Added_Time", "Modified_Time", "Added_User", "Modified_User"):
                continue

            download_url = None
            filename = None

            if isinstance(value, str):
                # Check if it's an image URL
                if any(pattern in value.lower() for pattern in image_url_patterns):
                    download_url = self._normalize_url(value)
                    # Try to extract filename from base64 cli-msg if present
                    filename = self._extract_filename_from_url(value, record.get("ID"), field_name)

            elif isinstance(value, dict):
                # Nested object with file info
                download_url = value.get("download_url") or value.get("filepath") or value.get("url")
                filename = value.get("filename") or value.get("display_value")

                # Sometimes the URL is in a nested 'file' key
                if not download_url and "file" in value:
                    download_url = value["file"]

                if download_url:
                    download_url = self._normalize_url(download_url)

            elif isinstance(value, list) and len(value) > 0:
                # Multiple files in a single field
                for i, item in enumerate(value):
                    if isinstance(item, str) and any(p in item.lower() for p in image_url_patterns):
                        images.append({
                            "field_name": f"{field_name}_{i}",
                            "download_url": self._normalize_url(item),
                            "filename": f"{record.get('ID', 'unknown')}_{field_name}_{i}"
                        })
                    elif isinstance(item, dict):
                        item_url = item.get("download_url") or item.get("filepath") or item.get("url")
                        if item_url:
                            images.append({
                                "field_name": f"{field_name}_{i}",
                                "download_url": self._normalize_url(item_url),
                                "filename": item.get("filename", f"{record.get('ID', 'unknown')}_{field_name}_{i}")
                            })
                continue  # Already added to images list

            if download_url:
                images.append({
                    "field_name": field_name,
                    "download_url": download_url,
                    "filename": filename or f"{record.get('ID', 'unknown')}_{field_name}"
                })

        return images
    
    def _extract_filename_from_url(self, url: str, record_id: str, field_name: str) -> str:
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
