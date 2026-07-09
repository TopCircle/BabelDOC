"""Test Layout Composer"""

from babeldoc.format.pdf.document_il import il_version_1
from babeldoc.format.pdf.document_il.midend.flow_skeleton import (
    PublisherSkeleton,
    FlowRegion,
    FlowStateType,
    StyleRegion,
    VisualObject,
    Padding,
    ConstraintPriority,
)
from babeldoc.format.pdf.document_il.midend.layout_composer import (
    ConstraintComposer,
    TypesettingUnit,
    compute_avg_height,
    commit_line,
    create_typesetting_units_from_paragraph,
)


def test_typesetting_unit():
    """Test TypesettingUnit dataclass"""
    unit = TypesettingUnit(
        unicode="Hello",
        width=50.0,
        height=10.0,
        box=il_version_1.Box(x=100, y=200, x2=150, y2=210),
        font_size=12.0,
    )
    assert unit.unicode == "Hello"
    assert unit.width == 50.0
    assert unit.height == 10.0
    assert unit.font_size == 12.0
    print("TypesettingUnit test passed!")


def test_typesetting_unit_relocate():
    """Test TypesettingUnit.relocate"""
    unit = TypesettingUnit(
        unicode="Hello",
        width=50.0,
        height=10.0,
        box=il_version_1.Box(x=100, y=200, x2=150, y2=210),
        font_size=12.0,
    )

    relocated = unit.relocate(300, 400, 1.5)
    assert relocated.box.x == 300
    assert relocated.box.y == 400
    assert relocated.box.x2 == 300 + 50.0 * 1.5
    assert relocated.box.y2 == 400 + 10.0 * 1.5
    print("TypesettingUnit.relocate test passed!")


def test_constraint_composer():
    """Test ConstraintComposer initialization"""
    skeleton = PublisherSkeleton(
        regions=[
            FlowRegion(
                region_id=1,
                y_start=100,
                y_end=200,
                intervals=[(50, 562)],
                state=FlowStateType.FULL,
            ),
        ],
        style_regions=[
            StyleRegion(
                y_start=100,
                y_end=200,
                font_size=12.0,
                font_family="test",
                font_weight="normal",
                font_style="normal",
                leading=14.0,
                first_line_indent=0,
                left_indent=0,
                right_indent=0,
                alignment="left",
                space_before=0,
                space_after=0,
            ),
        ],
        objects=[],
        page_x_min=0,
        page_x_max=612,
        page_y_min=0,
        page_y_max=792,
    )

    composer = ConstraintComposer(skeleton)
    assert composer.skeleton is skeleton
    print("ConstraintComposer test passed!")


def test_compute_avg_height():
    """Test compute_avg_height function"""
    units = [
        TypesettingUnit(height=10.0),
        TypesettingUnit(height=12.0),
        TypesettingUnit(height=14.0),
    ]

    avg = compute_avg_height(units, 1.0)
    assert abs(avg - 12.0) < 0.01, f"Expected 12.0, got {avg}"

    avg_scaled = compute_avg_height(units, 1.5)
    assert abs(avg_scaled - 18.0) < 0.01, f"Expected 18.0, got {avg_scaled}"

    print("compute_avg_height test passed!")


def test_publisher_skeleton_get_intervals_at():
    """Test PublisherSkeleton.get_intervals_at"""
    skeleton = PublisherSkeleton(
        regions=[
            FlowRegion(
                region_id=1,
                y_start=100,
                y_end=200,
                intervals=[(50, 300)],
                state=FlowStateType.FULL,
            ),
            FlowRegion(
                region_id=2,
                y_start=200,
                y_end=300,
                intervals=[(50, 200), (400, 562)],
                state=FlowStateType.MULTI_COLUMN,
            ),
        ],
        page_x_min=0,
        page_x_max=612,
        page_y_min=0,
        page_y_max=792,
    )

    # Test y=150 (in first region)
    intervals = skeleton.get_intervals_at(150)
    assert intervals == [(50, 300)], f"Expected [(50, 300)], got {intervals}"

    # Test y=250 (in second region)
    intervals = skeleton.get_intervals_at(250)
    assert intervals == [(50, 200), (400, 562)], f"Expected [(50, 200), (400, 562)], got {intervals}"

    # Test y=50 (not in any region)
    intervals = skeleton.get_intervals_at(50)
    assert intervals == [], f"Expected [], got {intervals}"

    print("PublisherSkeleton.get_intervals_at test passed!")


def test_publisher_skeleton_get_style_at():
    """Test PublisherSkeleton.get_style_at"""
    skeleton = PublisherSkeleton(
        style_regions=[
            StyleRegion(
                y_start=100,
                y_end=200,
                font_size=12.0,
                font_family="test",
                font_weight="normal",
                font_style="normal",
                leading=14.0,
                first_line_indent=0,
                left_indent=0,
                right_indent=0,
                alignment="left",
                space_before=0,
                space_after=0,
            ),
        ],
        page_x_min=0,
        page_x_max=612,
        page_y_min=0,
        page_y_max=792,
    )

    # Test y=150 (in style region)
    style = skeleton.get_style_at(150)
    assert style is not None
    assert style.font_size == 12.0
    assert style.leading == 14.0

    # Test y=50 (not in any style region)
    style = skeleton.get_style_at(50)
    assert style is None

    print("PublisherSkeleton.get_style_at test passed!")


if __name__ == "__main__":
    test_typesetting_unit()
    test_typesetting_unit_relocate()
    test_constraint_composer()
    test_compute_avg_height()
    test_publisher_skeleton_get_intervals_at()
    test_publisher_skeleton_get_style_at()
    print("All tests passed!")
