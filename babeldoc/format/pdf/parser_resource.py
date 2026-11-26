"""Structured rejection and resource safety limits for PDF parsing."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

PARSER_RESOURCE_POLICY_VERSION = 1
DEFAULT_MAX_DECOMPRESSED_STREAM_BYTES = 128 * 1024 * 1024  # 128 MiB
DEFAULT_MAX_CMAP_RANGE_ENTRIES = 65536
DEFAULT_MAX_CMAP_TOTAL_ENTRIES = 262144

_DISABLE_PARSER_LIMITS: ContextVar[bool] = ContextVar(
    "babeldoc_disable_parser_resource_limits",
    default=False,
)


def parser_resource_limits_disabled() -> bool:
    return _DISABLE_PARSER_LIMITS.get()


@contextmanager
def parser_resource_limits_context(*, disabled: bool = False) -> Iterator[None]:
    token = _DISABLE_PARSER_LIMITS.set(bool(disabled))
    try:
        yield
    finally:
        _DISABLE_PARSER_LIMITS.reset(token)


class ParserResourceLimitError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        limit_name: str,
        limit: int,
        observed_or_requested: int,
        unit: str,
        scope: str,
        phase: str,
        page: int | None,
        object_ref: tuple[int, int] | None,
        policy_version: int,
    ) -> None:
        super().__init__(message)
        self.limit_name = limit_name
        self.limit = limit
        self.observed_or_requested = observed_or_requested
        self.unit = unit
        self.scope = scope
        self.phase = phase
        self.page = page
        self.object_ref = object_ref
        self.policy_version = policy_version

    def __reduce__(self):
        return (_restore_parser_resource_error, (self.args[0], self.__dict__))


def _restore_parser_resource_error(message, attributes):
    fields = (
        "limit_name",
        "limit",
        "observed_or_requested",
        "unit",
        "scope",
        "phase",
        "page",
        "object_ref",
        "policy_version",
    )
    error = ParserResourceLimitError(
        message, **{name: attributes[name] for name in fields}
    )
    error.__dict__.update(attributes)
    return error


def raise_stream_decompression_limit_error(
    observed_bytes: int,
    *,
    limit: int = DEFAULT_MAX_DECOMPRESSED_STREAM_BYTES,
    object_ref: tuple[int, int] | None = None,
) -> None:
    raise ParserResourceLimitError(
        f"PDF stream decompression exceeded limit ({observed_bytes} > {limit} bytes)",
        limit_name="max_decompressed_stream_bytes",
        limit=limit,
        observed_or_requested=observed_bytes,
        unit="bytes",
        scope="stream",
        phase="stream_decode",
        page=None,
        object_ref=object_ref,
        policy_version=PARSER_RESOURCE_POLICY_VERSION,
    )


def check_cmap_range_limit(
    span: int,
    total_after: int | None = None,
    *,
    phase: str = "tounicode_cmap",
    object_ref: tuple[int, int] | None = None,
) -> None:
    if parser_resource_limits_disabled():
        return
    if span > DEFAULT_MAX_CMAP_RANGE_ENTRIES:
        raise ParserResourceLimitError(
            f"CMap range span {span} exceeds limit {DEFAULT_MAX_CMAP_RANGE_ENTRIES}",
            limit_name="max_cmap_range_entries",
            limit=DEFAULT_MAX_CMAP_RANGE_ENTRIES,
            observed_or_requested=span,
            unit="entries",
            scope="cmap_range",
            phase=phase,
            page=None,
            object_ref=object_ref,
            policy_version=PARSER_RESOURCE_POLICY_VERSION,
        )
    if total_after is not None and total_after > DEFAULT_MAX_CMAP_TOTAL_ENTRIES:
        raise ParserResourceLimitError(
            f"Retained CMap mapping entries {total_after} exceed limit {DEFAULT_MAX_CMAP_TOTAL_ENTRIES}",
            limit_name="max_cmap_total_entries",
            limit=DEFAULT_MAX_CMAP_TOTAL_ENTRIES,
            observed_or_requested=total_after,
            unit="entries",
            scope="cmap",
            phase=phase,
            page=None,
            object_ref=object_ref,
            policy_version=PARSER_RESOURCE_POLICY_VERSION,
        )
