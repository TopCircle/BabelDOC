"""Document-scoped translation quality reports.

One collector belongs to one original file. Issues store counts and ids,
never paragraph text and never an exception repr.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

SCHEMA_VERSION = 1

_DETAIL_TYPES = (int, float, str)


def _clean_details(details: dict) -> dict[str, int | float | str]:
    cleaned: dict[str, int | float | str] = {}
    for key, value in dict(details or {}).items():
        if isinstance(value, bool) or not isinstance(value, _DETAIL_TYPES):
            raise TypeError(f"quality detail {key!r} must be int, float, or str")
        cleaned[str(key)] = value
    return cleaned


@dataclass(frozen=True, slots=True)
class QualityIssue:
    stage: str
    code: str
    page_index: int
    paragraph_id: str
    severity: Literal["warning", "error"]
    details: dict[str, int | float | str]

    def __post_init__(self) -> None:
        if self.severity not in ("warning", "error"):
            raise ValueError(f"unknown quality severity: {self.severity}")
        object.__setattr__(self, "stage", str(self.stage))
        object.__setattr__(self, "code", str(self.code))
        object.__setattr__(self, "page_index", int(self.page_index))
        object.__setattr__(self, "paragraph_id", str(self.paragraph_id))
        object.__setattr__(self, "details", _clean_details(self.details))

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "code": self.code,
            "page_index": self.page_index,
            "paragraph_id": self.paragraph_id,
            "severity": self.severity,
            "details": dict(self.details),
        }


class QualityReport:
    def __init__(self, *, run_id: str):
        self.run_id = str(run_id)
        self._lock = threading.Lock()
        self._issues: dict[tuple[str, str, int, str], QualityIssue] = {}

    def record(self, issue: QualityIssue) -> None:
        if not isinstance(issue, QualityIssue):
            raise TypeError("record() expects a QualityIssue")
        key = (issue.stage, issue.code, issue.page_index, issue.paragraph_id)
        with self._lock:
            self._issues.setdefault(key, issue)

    def _status_unlocked(self) -> str:
        severities = {issue.severity for issue in self._issues.values()}
        if "error" in severities:
            return "failed"
        if "warning" in severities:
            return "degraded"
        return "success"

    @property
    def status(self) -> str:
        with self._lock:
            return self._status_unlocked()

    @property
    def warning_count(self) -> int:
        with self._lock:
            return sum(
                1 for issue in self._issues.values() if issue.severity == "warning"
            )

    def to_dict(self) -> dict:
        with self._lock:
            issues = sorted(
                self._issues.values(),
                key=lambda issue: (
                    issue.page_index,
                    issue.paragraph_id,
                    issue.stage,
                    issue.code,
                ),
            )
            return {
                "schema_version": SCHEMA_VERSION,
                "run_id": self.run_id,
                "status": self._status_unlocked(),
                "issues": [issue.to_dict() for issue in issues],
            }

    def write_json(self, path: Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
        temporary = destination.with_name(destination.name + ".tmp")
        try:
            temporary.write_text(payload, encoding="utf-8")
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()


def ensure_document_quality_report(translation_config):
    """Create the original-file collector once. Split parts share it."""
    shared = translation_config.shared_context_cross_split_part
    report = getattr(shared, "quality_report", None)
    if report is None:
        report = QualityReport(run_id=uuid.uuid4().hex)
        shared.quality_report = report
    return report


def record_layout_incomplete(translation_config, exc) -> None:
    """Record a typesetting failure using the part's original page map."""
    if getattr(exc, "_quality_recorded", False):
        return
    report = getattr(
        translation_config.shared_context_cross_split_part, "quality_report", None
    )
    if report is None:
        return
    payload = exc.to_dict()
    local_page = int(payload["page_index"])
    try:
        page_index = int(translation_config.original_page_index(local_page))
    except Exception:
        page_index = local_page
    report.record(
        QualityIssue(
            "typesetting",
            "layout_incomplete",
            page_index,
            str(payload["paragraph_id"]),
            "error",
            {
                "reason": str(payload["reason"]),
                "requested_units": int(payload["requested_units"]),
                "placed_units": int(payload["placed_units"]),
            },
        )
    )
    exc._quality_recorded = True


def ensure_document_failure(translation_config) -> None:
    """Mark an aborted document failed without storing exception text."""
    report = getattr(
        translation_config.shared_context_cross_split_part, "quality_report", None
    )
    if report is None or report.status == "failed":
        return
    report.record(
        QualityIssue(
            "document",
            "document_failed",
            0,
            "",
            "error",
            {},
        )
    )


def publish_quality_report(translation_config, result=None) -> Path | None:
    """Write ``{stem}.{run_id}.quality.json`` for the original file."""
    report = getattr(
        translation_config.shared_context_cross_split_part, "quality_report", None
    )
    if report is None:
        return None
    destination = Path(translation_config.output_dir) / (
        f"{Path(translation_config.input_file).stem}.{report.run_id}.quality.json"
    )
    report.write_json(destination)
    if result is not None:
        result.quality_status = report.status
        result.quality_warning_count = report.warning_count
        result.quality_report_path = destination
    return destination
