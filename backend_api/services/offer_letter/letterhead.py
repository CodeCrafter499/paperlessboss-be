import logging
import os
from io import BytesIO
from pathlib import Path
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
LETTERHEAD_PDF_PATH = _BACKEND_ROOT / "assets" / "NIRL_Letter_Head_Mar_2026.pdf"

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
    """ReportLab needs a filesystem path or readable buffer; write temp if needed."""
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
