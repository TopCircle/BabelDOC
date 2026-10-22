"""Input gates copied from the placement prototype. Linguistic checks stay here."""

from __future__ import annotations

_SPREAD_WIDTH = 1000.0
_MIN_CHARS = 40
_MIN_LINGUISTIC = 0.45
_MIN_ASCII_SHARE = 0.40
_MIN_VOWEL_SHARE = 0.20


def input_gate(
    page_width: float, texts: list[str]
) -> tuple[str, float | None]:
    """Return ``(gate, linguistic_ratio)``.

    ``single_page`` is the only gate the first plugins may classify.
    """
    if page_width >= _SPREAD_WIDTH:
        return "spread", None
    chars = [char for text in texts for char in text if not char.isspace()]
    if len(chars) < _MIN_CHARS:
        return "image_only", None
    ascii_letters = [char for char in chars if char.isascii() and char.isalpha()]
    cjk = sum("\u4e00" <= char <= "\u9fff" for char in chars)
    linguistic = (len(ascii_letters) + cjk) / len(chars)
    if linguistic < _MIN_LINGUISTIC:
        return "bad_encoding", linguistic
    if len(ascii_letters) >= _MIN_ASCII_SHARE * len(chars):
        vowels = sum(char.lower() in "aeiou" for char in ascii_letters)
        if vowels / len(ascii_letters) < _MIN_VOWEL_SHARE:
            return "bad_encoding", linguistic
    return "single_page", linguistic
