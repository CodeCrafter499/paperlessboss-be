import logging
import os
import uuid
import tempfile
import requests
from io import BytesIO
from pathlib import Path
from typing import Optional

from PIL import Image, ImageChops
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings

logger = logging.getLogger(__name__)

import subprocess
import shutil

_has_poppler: Optional[bool] = None

def check_poppler() -> bool:
    try:
        import fitz
        return True
    except ImportError:
        return False


def trim_vertical_whitespace(img: Image.Image) -> Image.Image:
    # If the image has an alpha channel, we can check if it has transparency
    if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
        alpha = img.convert('RGBA').split()[-1]
        bbox = alpha.getbbox()
        if bbox:
            # bbox is (left, top, right, bottom)
            # return cropped image keeping full width and trimmed height
            return img.crop((0, bbox[1], img.width, bbox[3]))

    # Fallback: check for white background (or close to white)
    rgb_img = img.convert('RGB')
    bg = Image.new('RGB', rgb_img.size, (255, 255, 255))
    diff = ImageChops.difference(rgb_img, bg)
    # Thresholding to ignore very minor noise
    diff = ImageChops.add(diff, diff, 2.0, -100)
    bbox = diff.getbbox()
    if bbox:
        return img.crop((0, bbox[1], img.width, bbox[3]))
    return img

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
LETTERHEAD_PDF_PATH = _BACKEND_ROOT / "assets" / "NIRL_Letter_Head_Mar_2026.pdf"
_local_fallback_cache: Optional[dict] = None


class ProcessedLetterhead:
    def __init__(self, source: str | Path | bytes):
        self.pdf_source: str | Path | bytes = source
        self.header_image: Optional[Image.Image] = None
        self.footer_image: Optional[Image.Image] = None
        self.header_bytes: Optional[BytesIO] = None
        self.footer_bytes: Optional[BytesIO] = None
        self.header_path: Optional[Path] = None
        self.footer_path: Optional[Path] = None
        self.available: bool = True
        self.images_available: bool = False
        self._process(source)

    def _process(self, source: str | Path | bytes) -> None:
        global _local_fallback_cache
        is_fallback = False
        if isinstance(source, (str, Path)) and str(source) == str(LETTERHEAD_PDF_PATH):
            is_fallback = True
            if _local_fallback_cache is not None:
                logger.info("Using cached local fallback letterhead images")
                self.header_image = _local_fallback_cache["header_image"]
                self.footer_image = _local_fallback_cache["footer_image"]
                self.header_bytes = BytesIO(_local_fallback_cache["header_bytes_val"])
                self.footer_bytes = BytesIO(_local_fallback_cache["footer_bytes_val"])
                self.header_path = _local_fallback_cache["header_path"]
                self.footer_path = _local_fallback_cache["footer_path"]
                self.images_available = True
                return

        if not check_poppler():
            logger.warning("Poppler is not installed. Skipping image extraction for DOCX/PDF header fallback.")
            return

        try:
            import fitz
            if isinstance(source, bytes):
                doc = fitz.open(stream=source, filetype="pdf")
            else:
                doc = fitz.open(str(source))

            if doc.page_count == 0:
                logger.warning("Letterhead PDF has no pages.")
                return

            page = doc.load_page(0)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img_data = pix.tobytes("png")
            page_image = Image.open(BytesIO(img_data))
            
            width, height = page_image.size
            header_bottom = int(height * 0.35)
            footer_top = int(height * 0.90)

            self.header_image = trim_vertical_whitespace(page_image.crop((0, 0, width, header_bottom)))
            self.footer_image = trim_vertical_whitespace(page_image.crop((0, footer_top, width, height)))

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

            self.images_available = True
            if is_fallback:
                _local_fallback_cache = {
                    "header_image": self.header_image,
                    "footer_image": self.footer_image,
                    "header_bytes_val": self.header_bytes.getvalue(),
                    "footer_bytes_val": self.footer_bytes.getvalue(),
                    "header_path": self.header_path,
                    "footer_path": self.footer_path
                }
        except Exception as exc:
            logger.exception("Failed to process letterhead images: %s", exc)

    def cleanup(self) -> None:
        if isinstance(self.pdf_source, (str, Path)) and str(self.pdf_source) == str(LETTERHEAD_PDF_PATH):
            # Do not delete cached local fallback files
            return
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

    try:
        response = requests.post(url, data=file_bytes, headers=headers, timeout=30)
        if response.status_code != 200:
            logger.error("Supabase letterhead upload failed: %s", response.text)
            raise HTTPException(
                status_code=502,
                detail=f"Failed to save file to Supabase Storage: {response.text}"
            )
        return filename
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
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

    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code != 200:
            logger.error("Supabase letterhead download failed: %s", response.text)
            response.raise_for_status()
        return response.content
    except Exception as e:
        logger.error("Supabase letterhead download failed: %s", str(e))
        raise e


async def get_processed_letterhead(
    db: AsyncSession,
    company_id: uuid.UUID,
    signatory_id: Optional[uuid.UUID] = None,
    letterhead_id: Optional[uuid.UUID] = None
) -> Optional[ProcessedLetterhead]:
    from sqlalchemy import select
    from db.models import CompanyLetterhead

    # Find mapping in DB
    if letterhead_id:
        stmt = select(CompanyLetterhead).where(
            CompanyLetterhead.company_id == company_id,
            CompanyLetterhead.id == letterhead_id
        )
    else:
        stmt = select(CompanyLetterhead).where(
            CompanyLetterhead.company_id == company_id,
            CompanyLetterhead.is_active == True
        )

    result = await db.execute(stmt)
    mapping = result.scalar_one_or_none()

    if mapping:
        try:
            logger.info("Found versioned letterhead in database at: %s", mapping.storage_file_location)
            pdf_bytes = download_from_supabase(mapping.storage_file_location)
            processed = ProcessedLetterhead(pdf_bytes)
            if processed.available:
                return processed
        except Exception as e:
            logger.error("Failed to download or process letterhead from Supabase: %s", e)

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
        import fitz
        doc = fitz.open(str(LETTERHEAD_PDF_PATH))
        if doc.page_count == 0:
            logger.warning("Letterhead PDF has no pages at %s", LETTERHEAD_PDF_PATH)
            return

        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img_data = pix.tobytes("png")
        page_image = Image.open(BytesIO(img_data))

        width, height = page_image.size
        header_bottom = int(height * 0.35)
        footer_top = int(height * 0.90)

        _header_image = trim_vertical_whitespace(page_image.crop((0, 0, width, header_bottom)))
        _footer_image = trim_vertical_whitespace(page_image.crop((0, footer_top, width, height)))

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
