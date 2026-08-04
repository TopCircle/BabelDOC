"""Title→body vertical gap: P1 limited repair + legacy cascade + relative EN gap."""

from __future__ import annotations

from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import Page
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraph
from babeldoc.format.pdf.document_il.il_version_1 import PdfParagraphComposition
from babeldoc.format.pdf.document_il.il_version_1 import PdfStyle
from babeldoc.format.pdf.document_il.il_version_1 import VisualBbox
from babeldoc.format.pdf.document_il.utils.gap_contract_pass import (
    apply_gap_contract_first_pass,
)
from babeldoc.format.pdf.document_il.utils.layout_audit import LayoutAuditReport
from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntent
from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntentRole
from babeldoc.format.pdf.document_il.utils.vertical_gap import (
    DEFAULT_MIN_GAP_PT,
    MAX_SINGLE_JUMP_DY_PT,
    RELATIVE_GAP_EPS_PT,
    boxes_x_overlap,
    enforce_title_body_gaps,
    enforce_title_body_gaps_legacy,
    gap_deficit,
    ink_box,
    is_display_title,
    measured_ink_gap,
    relative_gap_ok,
    resolve_en_gap_contract,
    shift_paragraph_y,
)

RELATIVE_TOL = RELATIVE_GAP_EPS_PT + 0.5


def _ch(u: str, x: float, y: float, *, size: float, w: float = 10.0) -> PdfCharacter:
    box = Box(x=x, y=y, x2=x + w, y2=y + size * 0.9)
    return PdfCharacter(
        char_unicode=u,
        box=box,
        visual_bbox=VisualBbox(box=Box(x=box.x, y=box.y, x2=box.x2, y2=box.y2)),
        pdf_style=PdfStyle(font_id="F", font_size=size, graphic_state=None),
        scale=1.0,
        advance=w,
    )


def _para(chars: list[PdfCharacter], *, label: str = "plain text") -> PdfParagraph:
    box = ink_box(
        PdfParagraph(
            pdf_paragraph_composition=[
                PdfParagraphComposition(pdf_character=c) for c in chars
            ]
        )
    )
    return PdfParagraph(
        box=box,
        layout_label=label,
        pdf_paragraph_composition=[
            PdfParagraphComposition(pdf_character=c) for c in chars
        ],
        unicode="".join(c.char_unicode or "" for c in chars),
    )


def _attach_intent(
    para: PdfParagraph,
    *,
    role: LayoutIntentRole = LayoutIntentRole.BODY,
    gap_contract: float | None = None,
    top_inset: float = 0.0,
    bottom_inset: float = 0.0,
) -> None:
    assert para.box is not None
    para.layout_intent = LayoutIntent(
        role=role,
        design_box=Box(x=para.box.x, y=para.box.y, x2=para.box.x2, y2=para.box.y2),
        top_inset=top_inset,
        bottom_inset=bottom_inset,
        gap_contract=gap_contract,
        is_chrome=(role is LayoutIntentRole.CHROME),
    )


def test_is_display_title_by_size():
    p = _para([_ch("成", 50, 600, size=56.0)], label="plain text")
    assert is_display_title(p)


def test_shift_paragraph_y():
    p = _para([_ch("a", 100, 400, size=12.0)])
    y0 = p.pdf_paragraph_composition[0].pdf_character.box.y
    shift_paragraph_y(p, -20.0)
    assert abs(p.pdf_paragraph_composition[0].pdf_character.box.y - (y0 - 20)) < 0.01


def test_boxes_x_overlap_public():
    a = Box(x=0, y=0, x2=100, y2=10)
    b = Box(x=90, y=0, x2=200, y2=10)
    assert boxes_x_overlap(a, b)
    c = Box(x=120, y=0, x2=200, y2=10)
    assert not boxes_x_overlap(a, c, slack=0)


def test_enforce_gap_shifts_overlapping_body():
    title_chars = [
        _ch(c, 50 + i * 40, 580, size=56.0, w=38.0) for i, c in enumerate("标题字")
    ]
    body_chars = [
        _ch(c, 100 + i * 12, 590 - 12, size=12.0, w=11.0)
        for i, c in enumerate("正文开始在这里足够长")
    ]
    title = _para(title_chars, label="title")
    body = _para(body_chars, label="plain text")
    _attach_intent(title, role=LayoutIntentRole.TITLE, gap_contract=14.0)
    _attach_intent(body, role=LayoutIntentRole.BODY)
    page = Page(
        page_number=0,
        mediabox=Box(x=0, y=0, x2=612, y2=792),
        pdf_paragraph=[title, body],
    )

    t_ink = ink_box(title)
    b_ink_before = ink_box(body)
    assert t_ink and b_ink_before
    assert b_ink_before.y2 > t_ink.y - DEFAULT_MIN_GAP_PT

    report = enforce_title_body_gaps(page, min_gap=DEFAULT_MIN_GAP_PT)
    assert isinstance(report, LayoutAuditReport)
    assert report.shifts >= 1
    assert report.cascade_len <= 1
    assert report.violations  # post-pass repairs are violations
    b_ink = ink_box(body)
    assert b_ink is not None
    assert b_ink.y2 <= t_ink.y - 14.0 + RELATIVE_TOL


def test_no_shift_when_gap_already_enough():
    title = _para(
        [_ch(c, 50 + i * 40, 600, size=56.0, w=38.0) for i, c in enumerate("大标题")],
        label="title",
    )
    body = _para(
        [
            _ch(c, 100 + i * 12, 500 - 12, size=12.0, w=11.0)
            for i, c in enumerate("正文足够远")
        ],
        label="plain text",
    )
    _attach_intent(title, role=LayoutIntentRole.TITLE, gap_contract=14.0)
    page = Page(page_number=0, pdf_paragraph=[title, body])
    report = enforce_title_body_gaps(page, min_gap=14.0)
    assert report.shifts == 0


def test_chrome_footer_not_shifted():
    title = _para(
        [_ch("标", 50, 661.5, size=56.0), _ch("题", 100, 661.5, size=56.0)],
        label="title",
    )
    body = _para([_ch("正", 100, 620.0, size=12.0) for _ in range(6)], label="plain text")
    footer = _para([_ch("w", 100, 41.3, size=11.0)], label="abandon")
    footer.unicode = "www.GabrielleMoore.com"
    page = Page(
        page_number=0,
        mediabox=Box(x=0, y=0, x2=612, y2=792),
        pdf_paragraph=[title, body, footer],
    )
    y0 = footer.pdf_paragraph_composition[0].pdf_character.box.y
    enforce_title_body_gaps(page)
    assert footer.pdf_paragraph_composition[0].pdf_character.box.y == y0


def test_subtitle_inside_title_band_not_gapped():
    title = _para([_ch("章", 50, 661.5, size=32.0)], label="title")
    subtitle = _para([_ch("副", 50, 668.6, size=15.0)], label="title")
    body = _para([_ch("正", 100, 620.0, size=12.0)], label="plain text")
    page = Page(
        page_number=0,
        mediabox=Box(x=0, y=0, x2=612, y2=792),
        pdf_paragraph=[title, subtitle, body],
    )
    y0 = subtitle.pdf_paragraph_composition[0].pdf_character.box.y
    report = enforce_title_body_gaps(page)
    assert report.shifts == 0
    assert subtitle.pdf_paragraph_composition[0].pdf_character.box.y == y0


def test_enforce_single_jump_dy_le_24():
    title = _para(
        [_ch(c, 50 + i * 40, 580, size=56.0, w=38.0) for i, c in enumerate("标题字")],
        label="title",
    )
    body = _para(
        [
            _ch(c, 100 + i * 12, 560, size=12.0, w=11.0)
            for i, c in enumerate("正文严重重叠需要大位移")
        ],
        label="plain text",
    )
    _attach_intent(title, role=LayoutIntentRole.TITLE, gap_contract=50.0)
    page = Page(
        page_number=0,
        mediabox=Box(x=0, y=0, x2=612, y2=792),
        pdf_paragraph=[title, body],
    )
    assert ink_box(body).y < ink_box(title).y
    y0 = body.pdf_paragraph_composition[0].pdf_character.box.y
    report = enforce_title_body_gaps(page)
    assert report.shifts >= 1
    assert report.max_shift_pt <= MAX_SINGLE_JUMP_DY_PT + 0.05
    assert report.cascade_len <= 1
    y1 = body.pdf_paragraph_composition[0].pdf_character.box.y
    assert y0 - y1 <= MAX_SINGLE_JUMP_DY_PT + 0.05
    assert y0 - y1 >= 0.5


def test_gap_contract_first_pass_no_follower_shift():
    title = _para(
        [_ch(c, 50 + i * 40, 600, size=56.0, w=38.0) for i, c in enumerate("大标题")],
        label="title",
    )
    body = _para(
        [
            _ch(c, 100 + i * 12, 590 - 12, size=12.0, w=11.0)
            for i, c in enumerate("第一段正文")
        ],
        label="plain text",
    )
    follower = _para(
        [
            _ch(c, 100 + i * 12, 540 - 12, size=12.0, w=11.0)
            for i, c in enumerate("第二段跟随")
        ],
        label="plain text",
    )
    _attach_intent(
        title,
        role=LayoutIntentRole.TITLE,
        gap_contract=25.0,
        bottom_inset=0.0,
        top_inset=0.0,
    )
    _attach_intent(body, role=LayoutIntentRole.BODY, top_inset=0.0, bottom_inset=0.0)
    _attach_intent(follower, role=LayoutIntentRole.BODY)
    page = Page(
        page_number=0,
        mediabox=Box(x=0, y=0, x2=612, y2=792),
        pdf_paragraph=[title, body, follower],
    )
    f_y0 = follower.box.y
    report = apply_gap_contract_first_pass(page)
    assert report.cascade_len <= 1
    assert abs(follower.box.y - f_y0) < 0.05
    # reservations are actions, not violations
    assert report.actions
    assert not report.violations


def test_gap_contract_first_pass_never_moves_up():
    """Body already too low for EN gap → first pass must not pull it up."""
    title = _para(
        [_ch(c, 50 + i * 40, 600, size=56.0, w=38.0) for i, c in enumerate("大标题")],
        label="title",
    )
    # Far below: already large gap
    body = _para(
        [
            _ch(c, 100 + i * 12, 400, size=12.0, w=11.0)
            for i, c in enumerate("远处正文")
        ],
        label="plain text",
    )
    _attach_intent(title, role=LayoutIntentRole.TITLE, gap_contract=14.0)
    _attach_intent(body, role=LayoutIntentRole.BODY)
    page = Page(
        page_number=0,
        mediabox=Box(x=0, y=0, x2=612, y2=792),
        pdf_paragraph=[title, body],
    )
    y0 = body.box.y
    report = apply_gap_contract_first_pass(page)
    assert body.box.y == y0  # unchanged
    assert report.shifts == 0


def test_gap_contract_read_from_stack_bottom_not_only_title():
    """gap_contract on stack-bottom (subtitle) still resolves for the title."""
    title = _para(
        [_ch(c, 50 + i * 40, 580, size=56.0, w=38.0) for i, c in enumerate("标题字")],
        label="title",
    )
    # Stack-bottom carrier lower on page than title ink bottom? Same column,
    # slightly lower design box — carries the contract (extractor model).
    carrier = _para(
        [_ch("副", 50, 575, size=15.0)],
        label="plain text",
    )
    body = _para(
        [
            _ch(c, 100 + i * 12, 560, size=12.0, w=11.0)
            for i, c in enumerate("正文需要间距")
        ],
        label="plain text",
    )
    _attach_intent(title, role=LayoutIntentRole.TITLE, gap_contract=None)
    _attach_intent(
        carrier,
        role=LayoutIntentRole.BODY,
        gap_contract=20.0,
    )
    _attach_intent(body, role=LayoutIntentRole.BODY)
    page = Page(
        page_number=0,
        mediabox=Box(x=0, y=0, x2=612, y2=792),
        pdf_paragraph=[title, carrier, body],
    )
    assert resolve_en_gap_contract(title, page) == 20.0
    report = enforce_title_body_gaps(page)
    # With en=20 and tight body, should attempt repair
    assert report.shifts >= 1 or gap_deficit(
        measured_ink_gap(title, body) or 0, 20.0
    ) <= 0


def test_audit_report_json_shape():
    report = LayoutAuditReport()
    report.record_action(
        debug_id="p0",
        kind="gap_contract_reservation",
        delta_pt=-8.0,
        policy="first_pass_down_only",
        page_number=0,
    )
    report.record_violation(
        debug_id="p1",
        kind="gap",
        delta_pt=-12.5,
        policy="single_jump_clamp_24",
        page_number=0,
    )
    report.record_shift(-12.5, cascade=1)
    d = report.to_dict()
    assert d["target_rule"] == "ink_gap_relative"
    assert d["actions"][0]["kind"] == "gap_contract_reservation"
    assert d["violations"][0]["kind"] == "gap"
    assert d["shifts"] == 1


def test_gap_deficit_single_source():
    # en=25.7, zh=24 → within eps=2 → deficit 0
    assert gap_deficit(24.0, 25.7, eps=2.0) == 0.0
    # zh=20 → need ~3.7 more (25.7 - 2 - 20)
    assert abs(gap_deficit(20.0, 25.7, eps=2.0) - 3.7) < 0.01
    # no EN → fallback 14, zh=10 → deficit 2
    assert abs(gap_deficit(10.0, None, fallback=14.0, eps=2.0) - 2.0) < 0.01
    assert relative_gap_ok(24.0, 25.7, eps=2.0)
    assert not relative_gap_ok(10.0, 25.7, eps=2.0)


def test_legacy_still_cascades_for_delta_compare():
    title = _para(
        [_ch(c, 50 + i * 40, 580, size=56.0, w=38.0) for i, c in enumerate("标题字")],
        label="title",
    )
    body = _para(
        [
            _ch(c, 100 + i * 12, 590 - 12, size=12.0, w=11.0)
            for i, c in enumerate("正文开始在这里足够长")
        ],
        label="plain text",
    )
    follower = _para(
        [
            _ch(c, 100 + i * 12, 560 - 12, size=12.0, w=11.0)
            for i, c in enumerate("跟随段落同样在列")
        ],
        label="plain text",
    )
    page = Page(
        page_number=0,
        mediabox=Box(x=0, y=0, x2=612, y2=792),
        pdf_paragraph=[title, body, follower],
    )
    n = enforce_title_body_gaps_legacy(page, min_gap=14.0)
    assert isinstance(n, int)
    assert n >= 1


def test_measured_ink_gap():
    title = _para([_ch("T", 50, 600, size=56.0)], label="title")
    body = _para([_ch("B", 50, 500, size=12.0)], label="plain text")
    g = measured_ink_gap(title, body)
    assert g is not None
    assert g > 50
