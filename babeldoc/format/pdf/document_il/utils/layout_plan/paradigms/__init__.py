"""Catalog of claim modules.

A directory is a paradigm only when it defines ``claim``. The category
folders do not.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

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
