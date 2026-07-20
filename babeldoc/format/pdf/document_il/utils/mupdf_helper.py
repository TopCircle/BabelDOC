import numpy as np
import pymupdf

from babeldoc.const import get_process_pool
from babeldoc.format.pdf.document_il.utils.raster_geometry import DEFAULT_MAX_PIXELS
from babeldoc.format.pdf.document_il.utils.raster_geometry import RasterGeometry
from babeldoc.format.pdf.document_il.utils.raster_geometry import (
    max_dpi_within_pixel_budget,
)
from babeldoc.format.pdf.document_il.utils.raster_geometry import with_pixel_budget


def get_no_rotation_img(page: pymupdf.Page, dpi: int = 72) -> pymupdf.Pixmap:
    """Legacy pixmap helper; DPI is capped to ``DEFAULT_MAX_PIXELS``.

    Prefer ``with_pixel_budget`` / ``with_target_long_edge`` for new code.
    """
    original_rotation = page.rotation
    page.set_rotation(0)
    try:
        rect = page.rect
        safe_dpi = max_dpi_within_pixel_budget(
            float(rect.width),
            float(rect.height),
            max(1, int(dpi)),
            DEFAULT_MAX_PIXELS,
        )
        return page.get_pixmap(dpi=safe_dpi)
    finally:
        page.set_rotation(original_rotation)


def get_no_rotation_img_multiprocess_internal(
    pdf_bytes: str, pagenum: int, dpi: int = 72
) -> np.ndarray:
    doc = pymupdf.open(pdf_bytes)
    try:
        page = doc[pagenum]
        original_rotation = page.rotation
        page.set_rotation(0)
        try:
            rect = page.rect
            safe_dpi = max_dpi_within_pixel_budget(
                float(rect.width),
                float(rect.height),
                max(1, int(dpi)),
                DEFAULT_MAX_PIXELS,
            )
            pix = page.get_pixmap(dpi=safe_dpi)
        finally:
            page.set_rotation(original_rotation)
        return np.frombuffer(pix.samples, np.uint8).reshape(
            pix.height,
            pix.width,
            3,
        )[:, :, ::-1]
    finally:
        doc.close()


def get_no_rotation_img_multiprocess(pdf_bytes: str, pagenum: int, dpi: int = 72):
    pool = get_process_pool()
    if pool is None:
        return get_no_rotation_img_multiprocess_internal(pdf_bytes, pagenum, dpi)
    return pool.apply(
        get_no_rotation_img_multiprocess_internal, (pdf_bytes, pagenum, dpi)
    )


def get_no_rotation_raster_geometry_multiprocess_internal(
    pdf_path: str,
    page_number: int,
    requested_dpi: int = 150,
    max_pixels: int = DEFAULT_MAX_PIXELS,
) -> RasterGeometry:
    """Render one temporary-PDF page with the shared pixel-budget contract."""

    with pymupdf.open(pdf_path) as doc:
        return with_pixel_budget(
            doc[page_number],
            requested_dpi,
            max_pixels,
            normalize_rotation=True,
        )


def get_no_rotation_raster_geometry_multiprocess(
    pdf_path: str,
    page_number: int,
    requested_dpi: int = 150,
    max_pixels: int = DEFAULT_MAX_PIXELS,
) -> RasterGeometry:
    """Return a picklable, budgeted RGB raster geometry for one PDF page."""

    pool = get_process_pool()
    args = (pdf_path, page_number, requested_dpi, max_pixels)
    if pool is None:
        return get_no_rotation_raster_geometry_multiprocess_internal(*args)
    return pool.apply(get_no_rotation_raster_geometry_multiprocess_internal, args)
