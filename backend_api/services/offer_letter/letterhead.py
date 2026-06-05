import logging
import os
import uuid
import tempfile
import urllib.request
import urllib.error
from io import BytesIO
from pathlib import Path
from typing import Optional

from PIL import Image
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings

logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
LETTERHEAD_PDF_PATH = _BACKEND_ROOT / "assets" / "NIRL_Letter_Head_Mar_2026.pdf"


class ProcessedLetterhead:
    def __init__(self, source: str | Path | bytes):
        self.pdf_source: str | Path | bytes = source
        self.header_image: Optional[Image.Image] = None
        self.footer_image: Optional[Image.Image] = None
        self.header_bytes: Optional[BytesIO] = None
        self.footer_bytes: Optional[BytesIO] = None
        self.header_path: Optional[Path] = None
        self.footer_path: Optional[Path] = None
        self.available: bool = False
        self._process(source)

    def _process(self, source: str | Path | bytes) -> None:
        try:
            from pdf2image import convert_from_bytes, convert_from_path

            if isinstance(source, bytes):
                pages = convert_from_bytes(source, dpi=150, first_page=1, last_page=1)
            else:
                pages = convert_from_path(str(source), dpi=150, first_page=1, last_page=1)

            if not pages:
                logger.warning("Letterhead PDF produced no pages.")
                return

            page = pages[0]
            width, height = page.size
            header_bottom = int(height * 0.35)
            footer_top = int(height * 0.90)

            self.header_image = page.crop((0, 0, width, header_bottom))
            self.footer_image = page.crop((0, footer_top, width, height))

            self.header_bytes = BytesIO()
            self.footer_bytes = BytesIO()
            self.header_image.save(self.header_bytes, format="PNG")
            self.footer_image.save(self.footer_bytes, format="PNG")
            self.header_bytes.seek(0)
            self.footer_bytes.seek(0)

            temp_dir = Path(tempfile.gettempdir()) / "paperlessboss_letterhead"
            temp_dir.mkdir(parents=True, exist_ok=True)
            unique_id = uuid.uuid4().hex
            self.header_path = temp_dir / f"header_{unique_id}.png"
            self.footer_path = temp_dir / f"footer_{unique_id}.png"

            self.header_image.save(self.header_path, format="PNG")
            self.footer_image.save(self.footer_path, format="PNG")

            self.available = True
        except Exception as exc:
            logger.exception("Failed to process letterhead: %s", exc)

    def cleanup(self) -> None:
        try:
            if self.header_path and Path(self.header_path).exists():
                Path(self.header_path).unlink()
            if self.footer_path and Path(self.footer_path).exists():
                Path(self.footer_path).unlink()
        except Exception as e:
            logger.warning("Error cleaning up temp letterhead files: %s", e)


def upload_letterhead_to_supabase(file_bytes: bytes, filename: str, content_type: str) -> str:
    if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
        logger.warning("SUPABASE_URL or SUPABASE_KEY not configured. Mocking upload path.")
        return filename

    bucket = settings.SUPABASE_BUCKET
    supabase_url = settings.SUPABASE_URL.rstrip('/')
    url = f"{supabase_url}/storage/v1/object/{bucket}/{filename}"

    headers = {
        "Authorization": f"Bearer {settings.SUPABASE_KEY}",
        "apikey": settings.SUPABASE_KEY,
        "Content-Type": content_type
    }

    req = urllib.request.Request(url, data=file_bytes, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as response:
            return filename
    except urllib.error.HTTPError as e:
        error_msg = e.read().decode("utf-8")
        logger.error("Supabase letterhead upload failed: %s", error_msg)
        raise HTTPException(
            status_code=502,
            detail=f"Failed to save file to Supabase Storage: {error_msg}"
        )
    except Exception as e:
        logger.error("Supabase letterhead upload exception: %s", str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error uploading file to storage: {str(e)}"
        )


def download_from_supabase(filename: str) -> bytes:
    if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
        raise ValueError("Supabase URL or Key is not configured.")

    bucket = settings.SUPABASE_BUCKET
    supabase_url = settings.SUPABASE_URL.rstrip('/')
    url = f"{supabase_url}/storage/v1/object/{bucket}/{filename}"

    headers = {
        "Authorization": f"Bearer {settings.SUPABASE_KEY}",
        "apikey": settings.SUPABASE_KEY,
    }

    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req) as response:
            return response.read()
    except urllib.error.HTTPError as e:
        error_msg = e.read().decode("utf-8")
        logger.error("Supabase letterhead download failed: %s", error_msg)
        raise e


async def get_processed_letterhead(
    db: AsyncSession,
    company_id: uuid.UUID,
    signatory_id: Optional[uuid.UUID]
) -> Optional[ProcessedLetterhead]:
    from sqlalchemy import select
    from db.models import StorageMapping

    # Find mapping in DB
    stmt = select(StorageMapping).where(
        StorageMapping.company_id == company_id,
        StorageMapping.document_type == "letterhead"
    )
    if signatory_id:
        stmt = stmt.where(StorageMapping.authorised_signatory_id == signatory_id)

    result = await db.execute(stmt)
    mapping = result.scalar_one_or_none()

    if mapping:
        try:
            logger.info("Found letterhead mapping in database at: %s", mapping.storage_file_location)
            pdf_bytes = download_from_supabase(mapping.storage_file_location)
            processed = ProcessedLetterhead(pdf_bytes)
            if processed.available:
                return processed
        except Exception as e:
            logger.error("Failed to download or process letterhead from Supabase: %s", e)

    # Fallback to local letterhead PDF
    if LETTERHEAD_PDF_PATH.is_file():
        logger.info("Falling back to local letterhead PDF at %s", LETTERHEAD_PDF_PATH)
        processed = ProcessedLetterhead(LETTERHEAD_PDF_PATH)
        if processed.available:
            return processed

    return None


# Global fallback helper functions (backward compatibility)
_header_image: Optional[Image.Image] = None
_footer_image: Optional[Image.Image] = None
_header_bytes: Optional[BytesIO] = None
_footer_bytes: Optional[BytesIO] = None
_letterhead_available = False
_load_attempted = False


def _load_letterhead() -> None:
    global _header_image, _footer_image, _header_bytes, _footer_bytes
    global _letterhead_available, _load_attempted

    if _load_attempted:
        return
    _load_attempted = True

    if not LETTERHEAD_PDF_PATH.is_file():
        logger.warning(
            "Letterhead PDF not found at %s — PDF/DOCX will use plain text header fallback.",
            LETTERHEAD_PDF_PATH,
        )
        return

    try:
        from pdf2image import convert_from_path

        pages = convert_from_path(str(LETTERHEAD_PDF_PATH), dpi=150, first_page=1, last_page=1)
        if not pages:
            logger.warning("Letterhead PDF produced no pages at %s", LETTERHEAD_PDF_PATH)
            return

        page = pages[0]
        width, height = page.size
        header_bottom = int(height * 0.35)
        footer_top = int(height * 0.90)

        _header_image = page.crop((0, 0, width, header_bottom))
        _footer_image = page.crop((0, footer_top, width, height))

        _header_bytes = BytesIO()
        _footer_bytes = BytesIO()
        _header_image.save(_header_bytes, format="PNG")
        _footer_image.save(_footer_bytes, format="PNG")
        _header_bytes.seek(0)
        _footer_bytes.seek(0)

        _letterhead_available = True
    except Exception as exc:
        logger.warning("Failed to load letterhead from %s: %s", LETTERHEAD_PDF_PATH, exc)


def is_letterhead_available() -> bool:
    _load_letterhead()
    return _letterhead_available


def get_header_image() -> Optional[Image.Image]:
    _load_letterhead()
    return _header_image


def get_footer_image() -> Optional[Image.Image]:
    _load_letterhead()
    return _footer_image


def get_header_bytes() -> Optional[BytesIO]:
    _load_letterhead()
    if _header_bytes is None:
        return None
    _header_bytes.seek(0)
    return _header_bytes


def get_footer_bytes() -> Optional[BytesIO]:
    _load_letterhead()
    if _footer_bytes is None:
        return None
    _footer_bytes.seek(0)
    return _footer_bytes


def get_header_path_for_reportlab() -> Optional[str]:
    header = get_header_image()
    if header is None:
        return None
    cache_dir = _BACKEND_ROOT / "assets" / ".letterhead_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / "header.png"
    if not path.exists() or (
        LETTERHEAD_PDF_PATH.is_file() and path.stat().st_mtime < LETTERHEAD_PDF_PATH.stat().st_mtime
    ):
        header.save(path, format="PNG")
    return str(path)


def get_footer_path_for_reportlab() -> Optional[str]:
    footer = get_footer_image()
    if footer is None:
        return None
    cache_dir = _BACKEND_ROOT / "assets" / ".letterhead_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / "footer.png"
    if not path.exists() or (
        LETTERHEAD_PDF_PATH.is_file() and path.stat().st_mtime < LETTERHEAD_PDF_PATH.stat().st_mtime
    ):
        footer.save(path, format="PNG")
    return str(path)
