"""Unit tests for Typesetting recursion guard and LayoutAttempt cyclic prevention."""

from __future__ import annotations

import tempfile
import unittest
from unittest.mock import MagicMock

import numpy as np
import pymupdf
from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import Page
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting
from babeldoc.format.pdf.document_il.utils.line_interval_plan import LayoutAttempt
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import _INK_LO
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import _SKIN_WARMTH
from babeldoc.format.pdf.document_il.utils.rect_flow_stack import _ink_span
from babeldoc.format.pdf.translation_config import TranslationConfig


class TestTypesettingRecursionGuard(unittest.TestCase):
    def setUp(self):
        config = TranslationConfig(
            input_file="dummy.pdf",
            output_dir=tempfile.gettempdir(),
            translator=MagicMock(),
            lang_in="en",
            lang_out="zh-CN",
            doc_layout_model=MagicMock(),
        )
        self.typesetting = Typesetting(config)
        self.typesetting.is_cjk = True

    def test_depth_guard_prevents_recursion(self):
        """When depth limit is exceeded, return gracefully without crashing."""
        para = PdfParagraph(box=Box(x=10.0, y=10.0, x2=200.0, y2=100.0))
        page = Page(page_number=0)
        scale, units = self.typesetting._find_optimal_scale_and_layout(
            para,
            page,
            [],
            initial_scale=1.0,
            _depth=5,
        )
        self.assertEqual(scale, 1.0)
        self.assertIsNone(units)

    def test_full_measure_attempt_does_not_cycle(self):
        """Calling with layout_attempt=LayoutAttempt.FULL_MEASURE must not cycle."""
        para = PdfParagraph(box=Box(x=10.0, y=10.0, x2=200.0, y2=100.0))
        page = Page(page_number=0)
        scale, _ = self.typesetting._find_optimal_scale_and_layout(
            para,
            page,
            [],
            initial_scale=1.0,
            layout_attempt=LayoutAttempt.FULL_MEASURE,
        )
        self.assertIsNotNone(scale)


class TestPhotoInkNumPy(unittest.TestCase):
    def test_numpy_ink_span_equivalence(self):
        """NumPy ink mask computation yields same left/right as pure pixel loops."""
        width, height = 100, 100
        # Initialize with white (255) background
        samples = bytearray([255] * (width * height * 3))

        # Set pixel at (row=20, col=35) to dark ink
        idx1 = (20 * width + 35) * 3
        samples[idx1] = 50
        samples[idx1 + 1] = 50
        samples[idx1 + 2] = 50

        # Set pixel at (row=25, col=80) to skin tone ink (red - blue >= 15, blue < 248, darkest < 250)
        idx2 = (25 * width + 80) * 3
        samples[idx2] = 210
        samples[idx2 + 1] = 160
        samples[idx2 + 2] = 120

        pix = pymupdf.Pixmap(pymupdf.csRGB, width, height, bytes(samples), 0)

        old_left, old_right = _ink_span(pix, 10, 30)

        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape((height, width, 3))
        r = arr[:, :, 0].astype(np.int16)
        g = arr[:, :, 1].astype(np.int16)
        b = arr[:, :, 2].astype(np.int16)
        darkest = np.minimum(np.minimum(r, g), b)
        ink_mask = (darkest < _INK_LO) | (
            (r - b >= _SKIN_WARMTH) & (b < 248) & (darkest < 250)
        )

        band_cols = np.where(ink_mask[10:31].any(axis=0))[0]
        np_left = int(band_cols[0]) if band_cols.size > 0 else None
        np_right = int(band_cols[-1]) if band_cols.size > 0 else None

        self.assertEqual((old_left, old_right), (np_left, np_right))
        self.assertEqual(np_left, 35)
        self.assertEqual(np_right, 80)
