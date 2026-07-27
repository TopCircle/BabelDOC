"""DeepLX garbage tokens must not survive into dual unicode (Day 6)."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.utils.mt_token_sanitize import sanitize_mt_output


class TestSanitizeMtOutput:
    def test_hex_brace_token(self):
        s = "{1cH00FFFFi1} 摩尔伽斯秘诀2. 告诉她加强性爱练习"
        assert sanitize_mt_output(s) == "摩尔伽斯秘诀2. 告诉她加强性爱练习"

    def test_qbs0_formula_debris(self):
        s = "为了确保她真正做到这一点，请与她一起努力QBS0。您需要这样做："
        out = sanitize_mt_output(s)
        assert "QBS0" not in out
        assert "努力。" in out or "努力" in out
        assert "您需要这样做" in out

    def test_bs5q(self):
        assert "BS5Q" not in sanitize_mt_output("达到 99.BS5Q% 的准确率")

    def test_orphan_brace_before_cjk(self):
        s = "{ 箴言 1. 治愈她的一意孤行"
        out = sanitize_mt_output(s)
        assert out.startswith("箴言") or "箴言" in out
        assert "{" not in out

    def test_preserves_normal_prose(self):
        s = "她说：\"如果 a > b，就选 A。\" 版本 v1 已发布。"
        assert sanitize_mt_output(s) == s

    def test_none_and_empty(self):
        assert sanitize_mt_output(None) is None
        assert sanitize_mt_output("") == ""
