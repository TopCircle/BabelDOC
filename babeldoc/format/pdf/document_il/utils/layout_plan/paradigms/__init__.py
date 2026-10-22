"""Catalog of layout paradigms.

A paradigm is maintained on its own, including the system ones. Adding a
layout mode does not change the main program or the pipeline. A directory
is a paradigm only when it defines ``claim``. The category folders do not.
"""

from __future__ import annotations

import importlib
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

from babeldoc.format.pdf.document_il.utils.layout_plan.paradigms.contract import (
    Paradigm,
)

_PACKAGE = __name__


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


def load_catalog(extra: Sequence[Paradigm] = ()) -> tuple[Paradigm, ...]:
    """System paradigms plus any that were passed in.

    ``extra`` is the inlet for a later file or UI. This function does not
    read a directory and does not replace a system name. Two claims that
    both match still conflict inside ``pick``.
    """
    found: dict[str, Paradigm] = {}
    for name, module in load_modules():
        fill = getattr(module, "fill", None)
        if not callable(fill):
            fill = None
        alignment = getattr(module, "ALIGNMENT", "left")
        flow = getattr(module, "FLOW", "edge")
        found[name] = Paradigm(
            name, module.THRESHOLD, module.claim, fill, alignment, flow
        )
    for item in extra:
        if item.name in found:
            raise ValueError(f"{item.name} is already registered")
        found[item.name] = item
    return tuple(found[name] for name in sorted(found))
