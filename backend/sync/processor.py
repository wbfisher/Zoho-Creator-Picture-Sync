from PIL import Image
import io
import logging

# Register HEIC support
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIC_SUPPORTED = True
except ImportError:
    HEIC_SUPPORTED = False

logger = logging.getLogger(__name__)


class ImageProcessor:
    def __init__(self, max_dimension: int = 4000, quality: int = 85, max_size_mb: int = 5):
        self.max_dimension = max_dimension
        self.quality = quality
        self.max_size_bytes = max_size_mb * 1024 * 1024
    
    def needs_processing(self, image_bytes: bytes) -> bool:
        return len(image_bytes) > self.max_size_bytes
    
    def process(self, image_bytes: bytes, original_filename: str) -> tuple[bytes, str]:
        """Process image: resize if needed, convert to WebP.
        
        Returns (processed_bytes, new_filename)
        """
        original_size = len(image_bytes)
        
        try:
            img = Image.open(io.BytesIO(image_bytes))
        except Exception as e:
            logger.warning(f"Could not process image {original_filename}: {e}")
            return image_bytes, original_filename
        
        # Convert RGBA to RGB if needed (WebP handles both, but just in case)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        
        # Resize if larger than max dimension
        width, height = img.size
        if width > self.max_dimension or height > self.max_dimension:
            ratio = min(self.max_dimension / width, self.max_dimension / height)
            new_size = (int(width * ratio), int(height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            logger.info(f"Resized {original_filename} from {width}x{height} to {new_size[0]}x{new_size[1]}")
        
        # Save as WebP
        output = io.BytesIO()
        img.save(output, format="WEBP", quality=self.quality, method=4)
        processed_bytes = output.getvalue()
        
        # Update filename extension
        base_name = original_filename.rsplit(".", 1)[0] if "." in original_filename else original_filename
        new_filename = f"{base_name}.webp"
        
        logger.info(
            f"Processed {original_filename}: {original_size / 1024:.1f}KB -> {len(processed_bytes) / 1024:.1f}KB"
        )
        
        return processed_bytes, new_filename
    
    def process_if_needed(self, image_bytes: bytes, filename: str) -> tuple[bytes, str, bool]:
        """Process only if over size threshold.

        Returns (bytes, filename, was_processed)
        """
        if self.needs_processing(image_bytes):
            processed, new_name = self.process(image_bytes, filename)
            return processed, new_name, True

        # Even if not processed, ensure filename has an extension
        filename = self._ensure_extension(image_bytes, filename)
        return image_bytes, filename, False

    def _ensure_extension(self, image_bytes: bytes, filename: str) -> str:
        """Ensure filename has a proper extension based on image content."""
        # Check if filename already has an image extension
        lower_name = filename.lower()
        if any(lower_name.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic', '.bmp', '.tiff']):
            return filename

        # Detect image format from bytes
        ext = self._detect_format(image_bytes)

        # Remove any existing non-image extension and add detected one
        base_name = filename.rsplit(".", 1)[0] if "." in filename else filename
        return f"{base_name}{ext}"

    def _detect_format(self, image_bytes: bytes) -> str:
        """Detect image format from magic bytes."""
        if len(image_bytes) < 12:
            return ".jpg"  # Default fallback

        # Check magic bytes
        if image_bytes[:3] == b'\xff\xd8\xff':
            return ".jpg"
        elif image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
            return ".png"
        elif image_bytes[:6] in (b'GIF87a', b'GIF89a'):
            return ".gif"
        elif image_bytes[:4] == b'RIFF' and image_bytes[8:12] == b'WEBP':
            return ".webp"
        elif image_bytes[4:12] == b'ftypheic' or image_bytes[4:12] == b'ftypmif1':
            return ".heic"
        elif image_bytes[:2] == b'BM':
            return ".bmp"
        elif image_bytes[:4] in (b'II*\x00', b'MM\x00*'):
            return ".tiff"
        else:
            # Try to detect using PIL as fallback
            try:
                img = Image.open(io.BytesIO(image_bytes))
                format_map = {
                    'JPEG': '.jpg',
                    'PNG': '.png',
                    'GIF': '.gif',
                    'WEBP': '.webp',
                    'HEIC': '.heic',
                    'BMP': '.bmp',
                    'TIFF': '.tiff',
                }
                return format_map.get(img.format, '.jpg')
            except Exception:
                return ".jpg"  # Default fallback
