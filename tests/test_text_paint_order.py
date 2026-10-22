"""Translated glyphs paint after an image that would cover them."""

from babeldoc.format.pdf.document_il.backend.pdf_creater import CharacterRenderUnit
from babeldoc.format.pdf.document_il.backend.pdf_creater import FormRenderUnit
from babeldoc.format.pdf.document_il.backend.pdf_creater import (
    lift_text_above_covering_images,
)
from babeldoc.format.pdf.document_il.il_version_1 import Box
from babeldoc.format.pdf.document_il.il_version_1 import PdfCharacter
from babeldoc.format.pdf.document_il.il_version_1 import PdfForm


def _char(x, y, x2, y2, order, sub=1, xobj_id=1):
    char = PdfCharacter()
    char.box = Box(x=x, y=y, x2=x2, y2=y2)
    char.xobj_id = xobj_id
    char.char_unicode = "字"
    return CharacterRenderUnit(char, order, sub)


def _image(x, y, x2, y2, order, sub=0, xobj_id=1, form_type="image"):
    form = PdfForm()
    form.box = Box(x=x, y=y, x2=x2, y2=y2)
    form.xobj_id = xobj_id
    form.form_type = form_type
    return FormRenderUnit(form, order, sub)


def test_a_glyph_on_a_later_image_paints_after_it():
    glyph = _char(221, 270, 233, 288, order=10, sub=4)
    photo = _image(221.7, 194, 399, 292, order=500)
    plain = _char(113, 270, 125, 288, order=10, sub=1)
    lift_text_above_covering_images([glyph, photo, plain])
    assert glyph.render_order == 501
    assert glyph.sub_render_order == 4
    assert plain.render_order == 10
    assert glyph.get_sort_key() > photo.get_sort_key()


def test_a_glyph_already_above_the_image_stays():
    glyph = _char(230, 270, 242, 288, order=800, sub=2)
    photo = _image(221, 194, 399, 292, order=500)
    lift_text_above_covering_images([glyph, photo])
    assert glyph.render_order == 800


def test_a_form_that_is_not_an_image_does_not_lift_text():
    glyph = _char(10, 10, 22, 28, order=3)
    form = _image(0, 0, 100, 100, order=40, form_type="form")
    lift_text_above_covering_images([glyph, form])
    assert glyph.render_order == 3


def test_an_image_in_another_xobject_does_not_lift_text():
    glyph = _char(10, 10, 22, 28, order=3, xobj_id=1)
    photo = _image(0, 0, 100, 100, order=40, xobj_id=2)
    lift_text_above_covering_images([glyph, photo])
    assert glyph.render_order == 3


def test_two_glyphs_keep_their_order_after_the_lift():
    first = _char(230, 270, 242, 288, order=10, sub=1)
    second = _char(242, 270, 254, 288, order=10, sub=2)
    photo = _image(200, 190, 400, 300, order=20)
    lift_text_above_covering_images([second, photo, first])
    assert first.get_sort_key() < second.get_sort_key()
    assert first.render_order == second.render_order == 21
