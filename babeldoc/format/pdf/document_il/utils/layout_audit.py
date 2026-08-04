"""Structured layout audit (Layout-First P1).

Mirrors ``skip_report.json`` style. Distinguishes:

* **actions / reservations** — intentional first-pass design spacing
* **violations / repairs** — post-typeset emergency fixes

Optional debug dump as ``layout_audit.json``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LayoutAuditReport:
    """Page- or document-level layout repair audit.

    ``target_rule`` documents the P1 acceptance contract: relative EN ink gap
    (via :func:`vertical_gap.gap_deficit`), never a hard-coded absolute like 25.7pt.
    """

    actions: list[dict[str, Any]] = field(default_factory=list)
    violations: list[dict[str, Any]] = field(default_factory=list)
    shifts: int = 0
    max_shift_pt: float = 0.0
    cascade_len: int = 0  # P1 allows ≤1 (single hop; no follower chains)
    target_rule: str = "ink_gap_relative"
    pages: dict[str, dict[str, Any]] = field(default_factory=dict)

    def record_action(
        self,
        *,
        debug_id: str | None,
        kind: str,
        delta_pt: float,
        policy: str,
        page_number: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Intentional layout step (e.g. first-pass gap reservation)."""
        entry: dict[str, Any] = {
            "debug_id": debug_id,
            "kind": kind,
            "delta_pt": round(float(delta_pt), 3),
            "policy": policy,
            "page_number": page_number,
        }
        if extra:
            entry.update(extra)
        self.actions.append(entry)

    def record_violation(
        self,
        *,
        debug_id: str | None,
        kind: str,
        delta_pt: float,
        policy: str,
        page_number: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Contract miss / emergency repair."""
        entry: dict[str, Any] = {
            "debug_id": debug_id,
            "kind": kind,
            "delta_pt": round(float(delta_pt), 3),
            "policy": policy,
            "page_number": page_number,
        }
        if extra:
            entry.update(extra)
        self.violations.append(entry)

    def record_shift(self, dy: float, *, cascade: int = 1) -> None:
        if abs(dy) < 0.05:
            return
        self.shifts += 1
        self.max_shift_pt = max(self.max_shift_pt, abs(float(dy)))
        self.cascade_len = max(self.cascade_len, int(cascade))

    def merge(self, other: LayoutAuditReport) -> None:
        self.actions.extend(other.actions)
        self.violations.extend(other.violations)
        self.shifts += other.shifts
        self.max_shift_pt = max(self.max_shift_pt, other.max_shift_pt)
        self.cascade_len = max(self.cascade_len, other.cascade_len)
        for k, v in other.pages.items():
            existing = self.pages.get(k)
            if existing is None:
                self.pages[k] = dict(v)
            else:
                # Preserve phase keys (first_pass / post_pass) when both present.
                merged = dict(existing)
                merged.update(v)
                self.pages[k] = merged

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_rule": self.target_rule,
            "shifts": self.shifts,
            "max_shift_pt": round(self.max_shift_pt, 3),
            "cascade_len": self.cascade_len,
            "actions": list(self.actions),
            "violations": list(self.violations),
            "pages": dict(self.pages),
        }

    def dump(self, path: Path) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception:
            logger.warning("layout_audit: dump failed path=%s", path, exc_info=True)
