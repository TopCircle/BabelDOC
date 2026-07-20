import logging

import cv2
import pymupdf
import regex
from skimage.metrics import structural_similarity

from babeldoc.babeldoc_exception.BabelDOCException import ScannedPDFError
from babeldoc.format.pdf.document_il import il_version_1
from babeldoc.format.pdf.document_il.backend.pdf_creater import PDFCreater
from babeldoc.format.pdf.document_il.utils.raster_geometry import with_pixel_budget
from babeldoc.format.pdf.document_il.utils.style_helper import BLACK
from babeldoc.format.pdf.document_il.utils.style_helper import GREEN
from babeldoc.format.pdf.translation_config import TranslationConfig

logger = logging.getLogger(__name__)

# Full-page (or near full-page) image used as the visible layer of a
# "searchable image" / dual-layer PDF (scan or Readdle-style export).
_FULLPAGE_IMAGE_AREA_RATIO = 0.85
# Fraction of pages that must look dual-layer before we auto-enable OCR mode.
_SEARCHABLE_IMAGE_PAGE_RATIO = 0.5


def page_has_fullpage_image(page: pymupdf.Page) -> bool:
    """True if any image covers most of the page media box."""
    page_area = abs(page.rect)
    if page_area <= 0:
        return False
    try:
        infos = page.get_image_info()
    except Exception:
        return False
    for info in infos:
        try:
            bbox = pymupdf.Rect(info["bbox"])
        except Exception:
            continue
        if bbox.get_area() / page_area >= _FULLPAGE_IMAGE_AREA_RATIO:
            return True
    return False


def page_has_invisible_text_layer(doc: pymupdf.Document, page: pymupdf.Page) -> bool:
    """True if content uses render-mode-3 text or an OCR text-layer mark.

    Dual-layer PDFs draw a page image for eyes and put copy/search text in an
    invisible layer (``3 Tr``), sometimes tagged ``OCRTextLayer`` / Readdle.
    """
    for index in page.get_contents() or []:
        try:
            contents = doc.xref_stream(index) or b""
        except Exception:
            continue
        if regex.search(rb"\s3\s+Tr\s", contents):
            return True
        if b"OCRTextLayer" in contents or b"ReaddleObject" in contents:
            return True
    return False


def is_searchable_image_pdf(doc: pymupdf.Document | None) -> bool:
    """Detect searchable dual-layer PDFs (full-page image + OCR text layer).

    Born-digital vector PDFs (including arXiv pages with ordinary figure
    XObjects) return False. Used to auto-enable ``ocr_workaround`` so mono/dual
    paints white fills under translated text instead of leaving English
    page-image pixels showing through.
    """
    if not doc or doc.page_count == 0:
        return False
    hits = 0
    for page in doc:
        if page_has_fullpage_image(page) and page_has_invisible_text_layer(doc, page):
            hits += 1
    # Majority of pages (ceil half); single-page dual-layer always qualifies.
    need = max(1, (doc.page_count + 1) // 2)
    return hits >= need and (hits / doc.page_count >= _SEARCHABLE_IMAGE_PAGE_RATIO)


def enable_ocr_workaround_for_searchable_image(
    translation_config: TranslationConfig,
    doc: pymupdf.Document | None,
) -> bool:
    """If *doc* is dual-layer, turn on OCR white-fill mode. Returns True if enabled.

    Independent of ``auto_enable_ocr_workaround`` / SSIM scanned detection.
    Idempotent once ``ocr_workaround`` is already True.
    """
    if translation_config.ocr_workaround:
        return False
    if not is_searchable_image_pdf(doc):
        return False
    logger.warning(
        "Searchable image PDF detected (full-page image + invisible OCR text "
        "layer). Enabling OCR workaround so translated text covers the page "
        "image background."
    )
    translation_config.ocr_workaround = True
    translation_config.shared_context_cross_split_part.auto_enabled_ocr_workaround = (
        True
    )
    # Match DetectScannedFile auto path: skip SSIM scan stage, keep text black.
    translation_config.skip_scanned_detection = True
    translation_config.disable_rich_text_translate = True
    return True


class DetectScannedFile:
    stage_name = "DetectScannedFile"

    def __init__(self, translation_config: TranslationConfig):
        self.translation_config = translation_config

    def _save_debug_box_to_page(self, page: il_version_1.Page, similarity: float):
        """Save debug boxes and text labels to the PDF page."""
        if not self.translation_config.debug:
            return

        color = GREEN

        # Create text label at top-left corner
        # Note: PDF coordinates are from bottom-left,
        # so we use y2 for top position
        style = il_version_1.PdfStyle(
            font_id="base",
            font_size=4,
            graphic_state=color,
        )
        page_width = page.cropbox.box.x2 - page.cropbox.box.x
        page_height = page.cropbox.box.y2 - page.cropbox.box.y
        unicode = f"scanned score: {similarity * 100:.2f} %"
        page.pdf_paragraph.append(
            il_version_1.PdfParagraph(
                first_line_indent=0.0,
                box=il_version_1.Box(
                    x=page.cropbox.box.x + page_width * 0.03,
                    y=page.cropbox.box.y,
                    x2=page.cropbox.box.x2,
                    y2=page.cropbox.box.y2 - page_height * 0.03,
                ),
                vertical=False,
                pdf_style=style,
                unicode=unicode,
                pdf_paragraph_composition=[
                    il_version_1.PdfParagraphComposition(
                        pdf_same_style_unicode_characters=il_version_1.PdfSameStyleUnicodeCharacters(
                            unicode=unicode,
                            pdf_style=style,
                            debug_info=True,
                        ),
                    ),
                ],
                xobj_id=-1,
            ),
        )

    def fast_check(self, doc: pymupdf.Document) -> bool:
        if doc:
            hit_list = [0] * len(doc)
            for page in doc:
                contents_list = page.get_contents()
                for index in contents_list:
                    contents = doc.xref_stream(index)
                    if regex.search(
                        rb"(/Artifact|/P)(\s*\<\<\s*/MCID\s+|\s+BDC)", contents
                    ):
                        hit_list[page.number] += 1
                    if regex.search(rb"\s3\s+Tr\s", contents):
                        hit_list[page.number] += 1
            return bool(sum(hit_list) > len(doc) * 0.8)
        return False

    def process(
        self, docs: il_version_1.Document, original_pdf_path, mediabox_data: dict
    ):
        """Generate layouts for all pages that need to be translated."""
        # Get pages that need to be translated

        pdf_creater = PDFCreater(
            original_pdf_path, docs, self.translation_config, mediabox_data
        )

        pages_to_translate = [
            page
            for page in docs.page
            if self.translation_config.should_translate_page(page.page_number + 1)
        ]
        if not pages_to_translate:
            return
        mupdf = pymupdf.open(self.translation_config.get_working_file_path("input.pdf"))
        total = len(pages_to_translate)
        threshold = 0.8 * total
        threshold = max(threshold, 1)
        scanned = 0
        non_scanned = 0
        non_scanned_threshold = total - threshold
        with self.translation_config.progress_monitor.stage_start(
            self.stage_name,
            total,
        ) as progress:
            for page in pages_to_translate:
                if scanned < threshold and non_scanned < non_scanned_threshold:
                    # Only continue detection if both counts are below thresholds
                    is_scanned = self.detect_page_is_scanned(page, mupdf, pdf_creater)
                    if is_scanned:
                        scanned += 1
                    else:
                        non_scanned += 1
                else:
                    # We have enough information to determine document type
                    non_scanned += 1
                progress.advance(1)

        if scanned >= threshold:
            if self.translation_config.auto_enable_ocr_workaround:
                logger.warning(
                    f"Detected {scanned} scanned pages, which is more than 80% of the total pages. "
                    "Turning on OCR workaround.",
                )
                self.translation_config.shared_context_cross_split_part.auto_enabled_ocr_workaround = True
                self.translation_config.ocr_workaround = True
                self.translation_config.skip_scanned_detection = True
                self.translation_config.disable_rich_text_translate = True
                self.clean_render_order_for_chars(docs)
                self.translation_config.remove_non_formula_lines = False
            else:
                logger.warning(
                    f"Detected {scanned} scanned pages, which is more than 80% of the total pages. "
                    "Please check the input PDF file.",
                )
                raise ScannedPDFError("Scanned PDF detected.")

    def clean_render_order_for_chars(self, docs: il_version_1.Document):
        for page in docs.page:
            for char in page.pdf_character:
                char.render_order = None
                if not char.debug_info:
                    char.pdf_style.graphic_state = BLACK

    def detect_page_is_scanned(
        self, page: il_version_1.Page, pdf: pymupdf.Document, pdf_creater: PDFCreater
    ) -> bool:
        geometry = with_pixel_budget(
            pdf[page.page_number],
            72,
            normalize_rotation=False,
        )
        before_page_image = geometry.image[:, :, ::-1]

        pdf_creater.update_page_content_stream(
            False, page, pdf, self.translation_config, True
        )

        after_page_image = geometry.render_at_dpi(
            pdf[page.page_number],
            normalize_rotation=False,
        )[:, :, ::-1]
        before_page_image = cv2.cvtColor(before_page_image, cv2.COLOR_RGB2GRAY)
        after_page_image = cv2.cvtColor(after_page_image, cv2.COLOR_RGB2GRAY)
        similarity = structural_similarity(before_page_image, after_page_image)
        return similarity > 0.95
