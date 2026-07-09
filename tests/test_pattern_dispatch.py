"""Test Pattern Dispatch"""

from babeldoc.format.pdf.document_il import il_version_1
from babeldoc.format.pdf.document_il.midend.flow_skeleton import (
    PublisherSkeleton,
    FlowRegion,
    FlowStateType,
    VisualObject,
    Padding,
    ConstraintPriority,
)
from babeldoc.format.pdf.document_il.midend.pattern_dispatch import (
    PatternDispatcher,
    PatternType,
    PatternMatch,
    PatternComposer,
)


def test_pattern_type():
    """Test PatternType enum"""
    assert PatternType.FULL_TEXT.value == "full_text"
    assert PatternType.RIGHT_FIGURE.value == "right_figure"
    assert PatternType.LEFT_FIGURE.value == "left_figure"
    assert PatternType.CENTER_FIGURE.value == "center_figure"
    assert PatternType.PULL_QUOTE.value == "pull_quote"
    assert PatternType.CAPTION.value == "caption"
    assert PatternType.SIDEBAR.value == "sidebar"
    assert PatternType.HEADER_FOOTER.value == "header_footer"
    assert PatternType.FULL_IMAGE.value == "full_image"
    assert PatternType.NUMBERED_STEP.value == "numbered_step"
    assert PatternType.ROUNDED_IMAGE.value == "rounded_image"
    assert PatternType.PERSON_CUTOUT.value == "person_cutout"
    print("PatternType test passed!")


def test_pattern_match():
    """Test PatternMatch dataclass"""
    match = PatternMatch(
        pattern=PatternType.FULL_TEXT,
        confidence=0.9,
        regions=[],
        objects=[],
        description="Test pattern",
    )
    assert match.pattern == PatternType.FULL_TEXT
    assert match.confidence == 0.9
    assert match.description == "Test pattern"
    print("PatternMatch test passed!")


def test_pattern_dispatcher_full_text():
    """Test PatternDispatcher with full text pattern"""
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
        objects=[],
        page_x_min=0,
        page_x_max=612,
        page_y_min=0,
        page_y_max=792,
    )

    dispatcher = PatternDispatcher(skeleton)
    match = dispatcher.detect_pattern()

    assert match.pattern == PatternType.FULL_TEXT
    assert match.confidence > 0.5
    print("PatternDispatcher full_text test passed!")


def test_pattern_dispatcher_right_figure():
    """Test PatternDispatcher with right figure pattern"""
    skeleton = PublisherSkeleton(
        regions=[
            FlowRegion(
                region_id=1,
                y_start=100,
                y_end=200,
                intervals=[(50, 300)],
                state=FlowStateType.LEFT_WRAP,
            ),
        ],
        objects=[
            VisualObject(
                kind="image",
                bbox=il_version_1.Box(x=300, y=100, x2=562, y2=200),
                padding=Padding.uniform(12),
                priority=ConstraintPriority.SOFT,
            ),
        ],
        page_x_min=0,
        page_x_max=612,
        page_y_min=0,
        page_y_max=792,
    )

    dispatcher = PatternDispatcher(skeleton)
    match = dispatcher.detect_pattern()

    assert match.pattern == PatternType.RIGHT_FIGURE
    assert match.confidence > 0.5
    print("PatternDispatcher right_figure test passed!")


def test_pattern_dispatcher_left_figure():
    """Test PatternDispatcher with left figure pattern"""
    skeleton = PublisherSkeleton(
        regions=[
            FlowRegion(
                region_id=1,
                y_start=100,
                y_end=200,
                intervals=[(300, 562)],
                state=FlowStateType.RIGHT_WRAP,
            ),
        ],
        objects=[
            VisualObject(
                kind="image",
                bbox=il_version_1.Box(x=50, y=100, x2=300, y2=200),
                padding=Padding.uniform(12),
                priority=ConstraintPriority.SOFT,
            ),
        ],
        page_x_min=0,
        page_x_max=612,
        page_y_min=0,
        page_y_max=792,
    )

    dispatcher = PatternDispatcher(skeleton)
    match = dispatcher.detect_pattern()

    assert match.pattern == PatternType.LEFT_FIGURE
    assert match.confidence > 0.5
    print("PatternDispatcher left_figure test passed!")


def test_pattern_dispatcher_center_figure():
    """Test PatternDispatcher with center figure pattern"""
    skeleton = PublisherSkeleton(
        regions=[
            FlowRegion(
                region_id=1,
                y_start=100,
                y_end=200,
                intervals=[(50, 200), (400, 562)],
                state=FlowStateType.MULTI_COLUMN,
            ),
        ],
        objects=[
            VisualObject(
                kind="image",
                bbox=il_version_1.Box(x=200, y=100, x2=400, y2=200),
                padding=Padding.uniform(12),
                priority=ConstraintPriority.SOFT,
            ),
        ],
        page_x_min=0,
        page_x_max=612,
        page_y_min=0,
        page_y_max=792,
    )

    dispatcher = PatternDispatcher(skeleton)
    match = dispatcher.detect_pattern()

    assert match.pattern == PatternType.CENTER_FIGURE
    assert match.confidence > 0.5
    print("PatternDispatcher center_figure test passed!")


def test_pattern_dispatcher_pull_quote():
    """Test PatternDispatcher with pull quote pattern"""
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
        objects=[
            VisualObject(
                kind="quote",
                bbox=il_version_1.Box(x=100, y=150, x2=500, y2=180),
                padding=Padding(left=24, right=8, top=8, bottom=8),
                priority=ConstraintPriority.SOFT,
            ),
        ],
        page_x_min=0,
        page_x_max=612,
        page_y_min=0,
        page_y_max=792,
    )

    dispatcher = PatternDispatcher(skeleton)
    match = dispatcher.detect_pattern()

    assert match.pattern == PatternType.PULL_QUOTE
    assert match.confidence > 0.5
    print("PatternDispatcher pull_quote test passed!")


def test_pattern_dispatcher_full_image():
    """Test PatternDispatcher with full image pattern"""
    skeleton = PublisherSkeleton(
        regions=[],
        objects=[
            VisualObject(
                kind="image",
                bbox=il_version_1.Box(x=0, y=0, x2=612, y2=792),
                padding=Padding.uniform(12),
                priority=ConstraintPriority.SOFT,
            ),
        ],
        page_x_min=0,
        page_x_max=612,
        page_y_min=0,
        page_y_max=792,
    )

    dispatcher = PatternDispatcher(skeleton)
    match = dispatcher.detect_pattern()

    assert match.pattern == PatternType.FULL_IMAGE
    assert match.confidence > 0.5
    print("PatternDispatcher full_image test passed!")


if __name__ == "__main__":
    test_pattern_type()
    test_pattern_match()
    test_pattern_dispatcher_full_text()
    test_pattern_dispatcher_right_figure()
    test_pattern_dispatcher_left_figure()
    test_pattern_dispatcher_center_figure()
    test_pattern_dispatcher_pull_quote()
    test_pattern_dispatcher_full_image()
    print("All tests passed!")
