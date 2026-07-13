"""Test Flow Skeleton extraction"""

from babeldoc.format.pdf.document_il import il_version_1
from babeldoc.format.pdf.document_il.midend.flow_skeleton import (
    PublisherSkeleton,
    FlowRegion,
    FlowStateType,
    VisualObject,
    Padding,
    ConstraintPriority,
    extract_publisher_skeleton,
    extract_visual_objects,
    extract_glyph_lines,
    build_flow_regions,
    determine_flow_state,
    determine_intervals_from_glyphs,
    can_merge,
    analyze_topology,
)


def test_flow_state_type():
    """Test FlowStateType enum"""
    assert FlowStateType.FULL.value == "full"
    assert FlowStateType.LEFT_WRAP.value == "left_wrap"
    assert FlowStateType.RIGHT_WRAP.value == "right_wrap"
    assert FlowStateType.MULTI_COLUMN.value == "multi"
    print("FlowStateType test passed!")


def test_flow_region():
    """Test FlowRegion dataclass"""
    region = FlowRegion(
        region_id=1,
        y_start=100,
        y_end=200,
        intervals=[(50, 300)],
        state=FlowStateType.FULL,
    )
    assert region.region_id == 1
    assert region.y_start == 100
    assert region.y_end == 200
    assert region.intervals == [(50, 300)]
    assert region.state == FlowStateType.FULL
    print("FlowRegion test passed!")


def test_visual_object():
    """Test VisualObject dataclass"""
    obj = VisualObject(
        kind="image",
        bbox=il_version_1.Box(x=100, y=100, x2=200, y2=200),
        padding=Padding.uniform(12),
        priority=ConstraintPriority.SOFT,
    )
    assert obj.kind == "image"
    assert obj.bbox.x == 100
    assert obj.padding.left == 12
    assert obj.priority == ConstraintPriority.SOFT
    print("VisualObject test passed!")


def test_determine_flow_state():
    """Test determine_flow_state function"""
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
    )

    # Test FULL state
    state = determine_flow_state(50, 562, 612, page)
    assert state == FlowStateType.FULL, f"Expected FULL, got {state}"

    # Test LEFT_WRAP state (right side has image)
    state = determine_flow_state(50, 300, 612, page)
    assert state == FlowStateType.LEFT_WRAP, f"Expected LEFT_WRAP, got {state}"

    # Test RIGHT_WRAP state (left side has image)
    state = determine_flow_state(300, 562, 612, page)
    assert state == FlowStateType.RIGHT_WRAP, f"Expected RIGHT_WRAP, got {state}"

    print("determine_flow_state test passed!")


def test_can_merge():
    """Test can_merge function"""
    region = FlowRegion(
        region_id=1,
        y_start=100,
        y_end=200,
        intervals=[(50, 300)],
        state=FlowStateType.FULL,
    )

    # Test merge with same state and intervals
    assert can_merge(region, FlowStateType.FULL, [(50, 300)], 210) == True

    # Test merge with different state
    assert can_merge(region, FlowStateType.LEFT_WRAP, [(50, 300)], 210) == False

    # Test merge with different intervals
    assert can_merge(region, FlowStateType.FULL, [(50, 400)], 210) == False

    # Test merge with too far y distance
    assert can_merge(region, FlowStateType.FULL, [(50, 300)], 300) == False

    print("can_merge test passed!")


def test_analyze_topology():
    """Test analyze_topology function"""
    regions = [
        FlowRegion(
            region_id=1,
            y_start=100,
            y_end=200,
            intervals=[(50, 562)],
            state=FlowStateType.FULL,
        ),
        FlowRegion(
            region_id=2,
            y_start=200,
            y_end=300,
            intervals=[(50, 300)],
            state=FlowStateType.LEFT_WRAP,
        ),
        FlowRegion(
            region_id=3,
            y_start=300,
            y_end=400,
            intervals=[(50, 562)],
            state=FlowStateType.FULL,
        ),
    ]

    topology = analyze_topology(regions)
    assert len(topology.states) == 3
    assert len(topology.transitions) == 2
    assert topology.transitions[0].trigger == "image_start"
    assert topology.transitions[1].trigger == "image_end"
    print("analyze_topology test passed!")


def test_extract_publisher_skeleton():
    """Test extract_publisher_skeleton with mock data"""
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
                box=il_version_1.Box(x=50, y=700, x2=562, y2=710),
                char_unicode="A",
                pdf_style=il_version_1.PdfStyle(font_id="test", font_size=12),
                xobj_id=-1,
            ),
            il_version_1.PdfCharacter(
                box=il_version_1.Box(x=50, y=680, x2=562, y2=690),
                char_unicode="B",
                pdf_style=il_version_1.PdfStyle(font_id="test", font_size=12),
                xobj_id=-1,
            ),
        ],
        pdf_figure=[
            il_version_1.PdfFigure(
                box=il_version_1.Box(x=300, y=500, x2=500, y2=600)
            )
        ],
        pdf_paragraph=[
            il_version_1.PdfParagraph(
                box=il_version_1.Box(x=50, y=700, x2=562, y2=710),
                pdf_paragraph_composition=[],
                first_line_indent=0.0,
                vertical=False,
                xobj_id=-1,
            ),
        ],
    )

    skeleton = extract_publisher_skeleton(page)
    assert skeleton is not None
    assert len(skeleton.regions) > 0
    assert len(skeleton.objects) > 0
    assert skeleton.page_x_max == 612
    assert skeleton.page_y_max == 792
    print("extract_publisher_skeleton test passed!")


if __name__ == "__main__":
    test_flow_state_type()
    test_flow_region()
    test_visual_object()
    test_determine_flow_state()
    test_can_merge()
    test_analyze_topology()
    test_extract_publisher_skeleton()
    print("All tests passed!")
