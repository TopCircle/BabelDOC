"""Catalog of layout paradigms.

A paradigm is maintained on its own, including the system ones. Adding a
layout mode does not change the main program or the pipeline. A directory
is a paradigm only when it defines ``claim``. The category folders do not.
"""

from __future__ import annotations

import importlib
from collections.abc import Sequence
from dataclasses import replace
from functools import cache
from pathlib import Path
from types import ModuleType

from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.activation import (
    ENABLED_SYSTEM_FILLS,
)
from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    Paradigm,
)

_PACKAGE = __name__


@cache
def load_modules() -> tuple[tuple[str, ModuleType], ...]:
    """Return ``(paradigm path, module)`` for every directory that claims."""
    root = Path(__file__).resolve().parent
    found: list[tuple[str, ModuleType]] = []
    for init in root.rglob("__init__.py"):
        relative = init.parent.relative_to(root)
        if not relative.parts:
            continue
        paradigm = relative.as_posix()
        module = importlib.import_module(f"{_PACKAGE}.{'.'.join(relative.parts)}")
        claim = getattr(module, "claim", None)
        if not callable(claim):
            continue
        threshold = getattr(module, "THRESHOLD", None)
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
            raise TypeError(f"{paradigm} THRESHOLD must be a float")
        found.append((paradigm, module))
    found.sort(key=lambda item: item[0])
    return tuple(found)


def load_catalog(
    extra: Sequence[Paradigm] = (),
    *,
    enabled_fills: frozenset[str] | None = None,
) -> tuple[Paradigm, ...]:
    """System paradigms plus any that were passed in.

    ``extra`` is the inlet for a later file or UI. This function does not
    read a directory and does not replace a system name. Two claims that
    both match still conflict inside ``pick``.

    A fill is attached only when its name is enabled. ``None`` uses the
    production allowlist. A name that is not in the catalog is refused.
    """
    allowed = ENABLED_SYSTEM_FILLS if enabled_fills is None else enabled_fills
    found: dict[str, Paradigm] = {}
    for name, module in load_modules():
        fill = getattr(module, "fill", None)
        if not callable(fill) or name not in allowed:
            fill = None
        alignment = getattr(module, "ALIGNMENT", "left")
        flow = getattr(module, "FLOW", "edge")
        found[name] = Paradigm(
            name, module.THRESHOLD, module.claim, fill, alignment, flow
        )
    for item in extra:
        if item.name in found:
            raise ValueError(f"{item.name} is already registered")
        if item.name not in allowed:
            item = replace(item, fill=None)
        found[item.name] = item
    unknown = sorted(allowed - found.keys())
    if unknown:
        raise ValueError("unknown enabled fill: " + ", ".join(unknown))
    return tuple(found[name] for name in sorted(found))
