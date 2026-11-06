"""Production fills that already have a closed acceptance record.

Discovering a ``fill`` callable does not enable it. ``hang/repeated``
stays identified and paused.
"""

from __future__ import annotations

ENABLED_SYSTEM_FILLS: frozenset[str] = frozenset(
    {
        "both/wider_below",
        "bow/left_bulge",
        "bow/left_inset",
        "bow/right_bulge",
        "bow/right_inset",
        "center/axis",
        "hang/deep",
        "hang/shallow",
        "indent/first_line",
        "mark/bullet_hang",
        "mark/bullet_plain",
        "mark/bullet_repeated",
        "mark/serial_hang",
        "mark/serial_plain",
        "mark/serial_repeated",
        "rag/deep_right",
        "rag/left_edge",
        "rag/right_edge",
        "rect/full_column",
        "rect/light_column",
        "step/left_lower_wide",
        "step/left_spur",
        "step/left_upper_wide",
        "step/right_lower_wide",
        "step/right_spur",
        "step/right_upper_wide",
        "taper/left_pin",
        "taper/right_pin",
        "toc/plain",
    }
)
