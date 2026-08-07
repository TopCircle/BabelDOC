"""LayoutIntent model tests (Layout-First P0, design doc §1.2/1.3/1.8).

Covers the role-enum value contract, the to_dict projection/roundtrip, the
runtime-only ``PdfParagraph.layout_intent`` default, and xml_converter omitting
the field (xsdata ``type="Ignore"`` metadata => never serialized).
"""

from dataclasses import fields

from babeldoc.format.pdf.document_il import il_version_1
from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntent
from babeldoc.format.pdf.document_il.utils.layout_intent import LayoutIntentRole
from babeldoc.format.pdf.document_il.utils.layout_intent import WrapMode
from babeldoc.format.pdf.document_il.xml_converter import XMLConverter


def test_role_enum_values():
    # Every member's value is its lowercase name.
    for member in LayoutIntentRole:
        assert member.value == member.name.lower()

    assert {member.value for member in LayoutIntentRole} == {
        "body",
        "title",
        "subtitle_overlay",
        "pull_quote",
        "callout",
        "figure_caption",
        "chrome",
        "wrap_column",
        "formula",
        "section_header",
        "list",
        "dropcap",
        "ocr",
    }

    # str Enum: value is usable directly as a plain string.
    assert LayoutIntentRole.BODY == "body"
    assert LayoutIntentRole("body") is LayoutIntentRole.BODY


def _from_dict(d: dict) -> LayoutIntent:
    """Rebuild a LayoutIntent from a to_dict() projection (roundtrip helper)."""
    return LayoutIntent(
        role=LayoutIntentRole(d["role"]),
        design_box=Box(*d["design_box"]),
        top_inset=d["top_inset"],
        bottom_inset=d["bottom_inset"],
        wrap_shape=(
            [tuple(pair) for pair in d["wrap_shape"]]
            if d["wrap_shape"] is not None
            else None
        ),
        wrap_mode=WrapMode(d["wrap_mode"]) if d.get("wrap_mode") else WrapMode.NONE,
        overlays_band=d["overlays_band"],
        stack=d["stack"],
        expansion_policy=tuple(d["expansion_policy"]),
        expansion_limits=tuple(d["expansion_limits"]),
        overflow_policy=d["overflow_policy"],
        min_scale=d["min_scale"],
        gap_contract=d["gap_contract"],
        is_chrome=d["is_chrome"],
        text_on_photo=d["text_on_photo"],
    )


def test_to_dict_roundtrip():
    intent = LayoutIntent(
        role=LayoutIntentRole.WRAP_COLUMN,
        design_box=Box(x=10.0, y=20.0, x2=210.0, y2=120.0),
        top_inset=2.5,
        bottom_inset=1.75,
        wrap_shape=[(4.0, 194.0), (6.5, 174.0)],
        wrap_mode=WrapMode.RIGHT_FIXED,
        overlays_band=None,
        stack=0,
        expansion_policy=("right", "down"),
        expansion_limits=("photo", "page_margin"),
        overflow_policy="scale_down",
        min_scale=0.55,
        gap_contract=12.3,
        is_chrome=False,
        text_on_photo=True,
    )
    d = intent.to_dict()
    # Box -> [x, y, x2, y2]; wrap_shape -> [[l, w], ...]; role -> value;
    # tuple policies -> JSON-friendly lists.
    assert d == {
        "role": "wrap_column",
        "design_box": [10.0, 20.0, 210.0, 120.0],
        "top_inset": 2.5,
        "bottom_inset": 1.75,
        "wrap_shape": [[4.0, 194.0], [6.5, 174.0]],
        "wrap_mode": "right_fixed",
        "overlays_band": None,
        "stack": 0,
        "expansion_policy": ["right", "down"],
        "expansion_limits": ["photo", "page_margin"],
        "overflow_policy": "scale_down",
        "min_scale": 0.55,
        "gap_contract": 12.3,
        "is_chrome": False,
        "text_on_photo": True,
    }
    # Roundtrip: a LayoutIntent rebuilt from the dict equals the original.
    assert _from_dict(d) == intent


def test_layout_intent_defaults():
    intent = LayoutIntent(
        role=LayoutIntentRole.BODY,
        design_box=Box(x=0.0, y=0.0, x2=100.0, y2=50.0),
        top_inset=0.0,
        bottom_inset=0.0,
    )
    assert intent.wrap_shape is None
    assert intent.overlays_band is None
    assert intent.stack == 0
    assert intent.expansion_policy == ("right", "down")
    assert intent.expansion_limits == ("page_margin",)
    assert intent.overflow_policy == "scale_down"
    assert intent.min_scale == 0.55
    assert intent.gap_contract is None
    assert intent.is_chrome is False
    assert intent.text_on_photo is False


def test_pdf_paragraph_layout_intent_default_none():
    paragraph = il_version_1.PdfParagraph(debug_id="p1", unicode="Hello")
    assert paragraph.layout_intent is None

    # Runtime-only: xsdata "Ignore" metadata makes xml_converter skip the
    # field even when it is set (a bare metadata-less field would be
    # serialized as an element once non-None).
    intent_field = next(
        f for f in fields(il_version_1.PdfParagraph) if f.name == "layout_intent"
    )
    assert intent_field.metadata == {"type": "Ignore"}

    intent = LayoutIntent(
        role=LayoutIntentRole.TITLE,
        design_box=Box(x=10.0, y=20.0, x2=210.0, y2=120.0),
        top_inset=0.0,
        bottom_inset=0.0,
    )
    paragraph.layout_intent = intent
    assert paragraph.layout_intent is intent


def test_xml_serialization_omits_layout_intent():
    paragraph = il_version_1.PdfParagraph(
        debug_id="p-with-intent",
        unicode="Hello",
        box=Box(x=10.0, y=20.0, x2=210.0, y2=120.0),
    )
    paragraph.layout_intent = LayoutIntent(
        role=LayoutIntentRole.PULL_QUOTE,
        design_box=Box(x=10.0, y=20.0, x2=210.0, y2=120.0),
        top_inset=1.0,
        bottom_inset=0.5,
        wrap_shape=[(4.0, 194.0)],
    )
    page = il_version_1.Page(
        mediabox=il_version_1.Mediabox(box=Box(x=0.0, y=0.0, x2=612.0, y2=792.0)),
        cropbox=il_version_1.Cropbox(box=Box(x=0.0, y=0.0, x2=612.0, y2=792.0)),
        pdf_paragraph=[paragraph],
    )
    document = il_version_1.Document(total_pages=1, page=[page])

    xml = XMLConverter().to_xml(document)
    # The paragraph itself is serialized...
    assert "p-with-intent" in xml
    # ...but the runtime-only field is omitted.
    assert "layout_intent" not in xml
