"""DeepLX garbage tokens must not survive into dual unicode (Day 6)."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.utils.mt_token_sanitize import (
    normalize_translated_text,
)
from babeldoc.format.pdf.document_il.utils.mt_token_sanitize import sanitize_mt_output


class TestNormalizeTranslatedText:
    def test_hex_brace_token(self):
        s = "{1cH00FFFFi1} 摩尔伽斯秘诀2. 告诉她加强性爱练习"
        assert normalize_translated_text(s) == "摩尔伽斯秘诀2. 告诉她加强性爱练习"

    def test_qbs0_formula_debris(self):
        s = "为了确保她真正做到这一点，请与她一起努力QBS0。您需要这样做："
        out = normalize_translated_text(s)
        assert "QBS0" not in out
        assert "努力。" in out or "努力" in out
        assert "您需要这样做" in out

    def test_bs5q(self):
        assert "BS5Q" not in normalize_translated_text("达到 99.BS5Q% 的准确率")

    def test_orphan_brace_before_cjk(self):
        s = "{ 箴言 1. 治愈她的一意孤行"
        out = normalize_translated_text(s)
        assert out.startswith("箴言") or "箴言" in out
        assert "{" not in out

    def test_style_markers_and_controls(self):
        s = "你好〖B1〗世界〖/B1〗\x01"
        out = normalize_translated_text(s)
        assert "〖B" not in out
        assert "\x01" not in out
        assert "你好" in out and "世界" in out

    def test_preserves_normal_prose(self):
        s = "她说：\"如果 a > b，就选 A。\" 版本 v1 已发布。"
        assert normalize_translated_text(s) == s

    def test_none_and_empty(self):
        assert normalize_translated_text(None) is None
        assert normalize_translated_text("") == ""

    def test_sanitize_alias(self):
        assert sanitize_mt_output("{1cH00FFFFi1}x") == normalize_translated_text(
            "{1cH00FFFFi1}x"
        )
