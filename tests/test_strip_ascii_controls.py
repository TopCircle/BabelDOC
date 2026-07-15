"""Strip C0/C1 controls that leak as SOH (U+0001) spans in dual PDFs."""

from babeldoc.format.pdf.document_il.utils.layout_helper import strip_ascii_controls


class TestStripAsciiControls:
    def test_removes_soh(self):
        s = "气味\x01‑\x01点燃你最喜欢的香薰蜡"
        assert strip_ascii_controls(s) == "气味‑点燃你最喜欢的香薰蜡"
        assert "\x01" not in strip_ascii_controls(s)

    def test_removes_soh_around_numbers(self):
        s = "从\x015\x01组\x0110\x01快速抽动"
        assert strip_ascii_controls(s) == "从5组10快速抽动"

    def test_removes_soh_in_name(self):
        s = "在GABRIELLE\x01MOORE电子书中"
        assert strip_ascii_controls(s) == "在GABRIELLEMOORE电子书中"

    def test_keeps_newlines_and_tabs(self):
        s = "第一行\n第二行\t缩进"
        assert strip_ascii_controls(s) == s

    def test_empty_and_none(self):
        assert strip_ascii_controls("") == ""
        assert strip_ascii_controls(None) == ""

    def test_preserves_cjk_and_dashes(self):
        s = "延迟射精—— 许多男性；气味‑视线"
        assert strip_ascii_controls(s) == s
