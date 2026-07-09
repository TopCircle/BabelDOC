"""Test Flow Debug SVG generation"""

import tempfile
from pathlib import Path

from babeldoc.format.pdf.document_il import il_version_1
from babeldoc.format.pdf.document_il.midend.flow_debug_svg import FlowDebugSvg, SvgBuilder


def test_svg_builder():
    """Test SvgBuilder basic functionality"""
    svg = SvgBuilder(612, 792)  # Letter size

    # Add some elements
    svg.add_rect(100, 100, 200, 150, stroke="blue", fill="rgba(0,0,255,0.1)")
    svg.add_text(150, 120, "Test Text", font_size=12, fill="red")
    svg.add_line(50, 50, 200, 200, stroke="green", stroke_width=2)
    svg.add_polygon([(300, 300), (400, 300), (350, 400)], stroke="purple", fill="rgba(128,0,128,0.2)")

    # Save to temporary file
    with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as f:
        svg.save(f.name)
        print(f"SVG saved to: {f.name}")

        # Verify file exists and has content
        assert Path(f.name).exists()
        content = Path(f.name).read_text()
        assert "svg" in content
        assert "rect" in content
        assert "text" in content
        assert "line" in content
        assert "polygon" in content
        print("SVG builder test passed!")


def test_flow_debug_svg():
    """Test FlowDebugSvg with mock data"""
    # Create mock page
    page = il_version_1.Page(
        cropbox=il_version_1.Cropbox(
            box=il_version_1.Box(x=0, y=0, x2=612, y2=792)
        ),
        mediabox=il_version_1.Mediabox(
            box=il_version_1.Box(x=0, y=0, x2=612, y2=792)
        ),
        page_number=0,
        unit="pt",
        pdf_character=[
            il_version_1.PdfCharacter(
                box=il_version_1.Box(x=100, y=700, x2=110, y2=710),
                char_unicode="A",
                pdf_style=il_version_1.PdfStyle(font_id="test", font_size=12),
                xobj_id=-1,
            ),
            il_version_1.PdfCharacter(
                box=il_version_1.Box(x=120, y=700, x2=130, y2=710),
                char_unicode="B",
                pdf_style=il_version_1.PdfStyle(font_id="test", font_size=12),
                xobj_id=-1,
            ),
        ],
        pdf_figure=[
            il_version_1.PdfFigure(
                box=il_version_1.Box(x=200, y=600, x2=400, y2=700)
            )
        ],
        page_layout=[
            il_version_1.PageLayout(
                box=il_version_1.Box(x=50, y=100, x2=562, y2=500),
                class_name="text",
            )
        ],
    )

    # Create mock document
    doc = il_version_1.Document(
        page=[page],
        total_pages=1,
    )

    # Create mock config
    class MockConfig:
        debug = True

    config = MockConfig()

    # Test SVG generation
    with tempfile.TemporaryDirectory() as tmpdir:
        svg_gen = FlowDebugSvg(config)
        svg_gen.process_page(page, tmpdir)

        svg_path = Path(tmpdir) / "flow_debug_page_1.svg"
        assert svg_path.exists(), f"SVG file not found: {svg_path}"

        content = svg_path.read_text()
        assert "Page 1" in content
        assert "figure" in content
        assert "text" in content
        print("FlowDebugSvg test passed!")


if __name__ == "__main__":
    test_svg_builder()
    test_flow_debug_svg()
    print("All tests passed!")
