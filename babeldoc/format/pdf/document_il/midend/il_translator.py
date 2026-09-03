from __future__ import annotations

import copy
import json
import logging
import re
import threading
from pathlib import Path
from string import Template

import tiktoken
from tqdm import tqdm

import babeldoc.format.pdf.document_il.il_version_1 as il_version_1
from babeldoc.babeldoc_exception.BabelDOCException import ContentFilterError
from babeldoc.format.pdf.document_il import Document
from babeldoc.format.pdf.document_il import GraphicState
from babeldoc.format.pdf.document_il import Page
from babeldoc.format.pdf.document_il import PdfFont
from babeldoc.format.pdf.document_il import PdfFormula
from babeldoc.format.pdf.document_il import PdfParagraph
from babeldoc.format.pdf.document_il import PdfParagraphComposition
from babeldoc.format.pdf.document_il import PdfSameStyleCharacters
from babeldoc.format.pdf.document_il import PdfSameStyleUnicodeCharacters
from babeldoc.format.pdf.document_il import PdfStyle
from babeldoc.format.pdf.document_il.utils.fontmap import FontMapper
from babeldoc.format.pdf.document_il.utils.layout_helper import FIGURE_TEXT_COVERAGE_THRESHOLD
from babeldoc.format.pdf.document_il.utils.drop_cap import is_drop_cap_style_span
from babeldoc.format.pdf.document_il.utils.layout_helper import (
    assemble_midcap_title_unicode,
)
from babeldoc.format.pdf.document_il.utils.layout_helper import flatten_composition_pdf_chars
from babeldoc.format.pdf.document_il.utils.layout_helper import get_char_unicode_string
from babeldoc.format.pdf.document_il.utils.layout_helper import visual_known_split_char_ids
from babeldoc.format.pdf.document_il.utils.layout_helper import get_paragraph_unicode
from babeldoc.format.pdf.document_il.utils.layout_helper import is_figure_text_paragraph
from babeldoc.format.pdf.document_il.utils.layout_helper import strip_ascii_controls
from babeldoc.format.pdf.document_il.utils.layout_helper import is_same_style
from babeldoc.format.pdf.document_il.utils.layout_helper import (
    is_same_style_except_font,
)
from babeldoc.format.pdf.document_il.utils.layout_helper import (
    is_same_style_except_size,
)
from babeldoc.format.pdf.document_il.utils.mt_token_sanitize import (
    normalize_translated_text,
)
from babeldoc.format.pdf.document_il.utils.paragraph_helper import (
    is_placeholder_only_paragraph,
)
from babeldoc.format.pdf.document_il.utils.side_callout_skip import (
    find_pullquote_host,
)
from babeldoc.format.pdf.document_il.utils.side_callout_skip import (
    is_near_full_pullquote,
)
from babeldoc.format.pdf.document_il.utils.side_callout_skip import (
    is_ultra_narrow_side_callout,
)
from babeldoc.format.pdf.document_il.utils.side_callout_skip import (
    normalize_narrow_callout_mode,
)
from babeldoc.format.pdf.document_il.utils.side_callout_skip import (
    side_callout_debug_extra,
)
from babeldoc.format.pdf.document_il.utils.region_skip import (
    classify_header_footer_skip,
)
from babeldoc.format.pdf.document_il.utils.region_skip import (
    should_skip_header_footer,
)
from babeldoc.format.pdf.document_il.utils.skip_audit import SkipReason
from babeldoc.format.pdf.document_il.utils.skip_audit import SkipReport
from babeldoc.format.pdf.document_il.utils.style_marker_recover import StyleSpan
from babeldoc.format.pdf.document_il.utils.style_marker_recover import (
    coalesce_emphasis_style_run,
)
from babeldoc.format.pdf.document_il.utils import text_recovery
from babeldoc.format.pdf.document_il.utils.style_marker_recover import (
    rewrap_styles_from_source,
)
from babeldoc.format.pdf.document_il.utils.style_marker_recover import style_by_id
from babeldoc.format.pdf.document_il.utils.paragraph_helper import (
    is_pure_numeric_paragraph,
)
from babeldoc.format.pdf.document_il.utils.style_helper import GRAY80
from babeldoc.format.pdf.translation_config import TitleContextSnapshot
from babeldoc.format.pdf.translation_config import TranslationConfig
from babeldoc.translator.translator import BaseTranslator
from babeldoc.utils.priority_thread_pool_executor import PriorityThreadPoolExecutor

logger = logging.getLogger(__name__)


PROMPT_TEMPLATE = Template(
    """$role_block

## Rules

1. Keep the structure exactly unchanged: do NOT add/remove/reorder any tags, placeholders, or tokens.
2. Keep all tags unchanged (e.g., <style>, <b>, </style>).
   - Translate human-readable text inside tags.
   - Do NOT translate text inside <code>…</code>.
3. Do NOT translate or alter placeholders: {v1}, {name}, %s, %d, [[...]], %%...%%.
4. If the entire input is pure code/identifiers, return it unchanged.
5. Translate ALL human-readable content into $lang_out.

$glossary_block

$context_block

## Output

Output ONLY the translated $lang_out text. No explanations, no backticks, no extra text.

Now translate the following text:

$text_to_translate"""
)


class RichTextPlaceholder:
    def __init__(
        self,
        placeholder_id: int,
        composition: PdfSameStyleCharacters,
        left_placeholder: str,
        right_placeholder: str,
        left_regex_pattern: str = None,
        right_regex_pattern: str = None,
    ):
        self.id = placeholder_id
        self.composition = composition
        self.left_placeholder = left_placeholder
        self.right_placeholder = right_placeholder
        self.left_regex_pattern = left_regex_pattern
        self.right_regex_pattern = right_regex_pattern

    def to_dict(self) -> dict:
        return {
            "type": "rich_text",
            "id": self.id,
            "left_placeholder": self.left_placeholder,
            "right_placeholder": self.right_placeholder,
            "left_regex_pattern": self.left_regex_pattern,
            "right_regex_pattern": self.right_regex_pattern,
            "composition_chars": get_char_unicode_string(self.composition.pdf_character)
            if self.composition and self.composition.pdf_character
            else None,
        }


class FormulaPlaceholder:
    def __init__(
        self,
        placeholder_id: int,
        formula: PdfFormula,
        placeholder: str,
        regex_pattern: str,
    ):
        self.id = placeholder_id
        self.formula = formula
        self.placeholder = placeholder
        self.regex_pattern = regex_pattern

    def to_dict(self) -> dict:
        return {
            "type": "formula",
            "id": self.id,
            "placeholder": self.placeholder,
            "regex_pattern": self.regex_pattern,
            "formula_chars": get_char_unicode_string(self.formula.pdf_character)
            if self.formula and self.formula.pdf_character
            else None,
        }


class PbarContext:
    def __init__(self, pbar):
        self.pbar = pbar

    def __enter__(self):
        return self.pbar

    def __exit__(self, exc_type, exc_value, traceback):
        self.pbar.advance()


class DocumentTranslateTracker:
    def __init__(self):
        self.page = []
        self.cross_page = []
        # Track paragraphs that are combined due to cross-column detection within the same page
        self.cross_column = []

    def new_page(self):
        page = PageTranslateTracker()
        self.page.append(page)
        return page

    def new_cross_page(self):
        page = PageTranslateTracker()
        self.cross_page.append(page)
        return page

    def new_cross_column(self):
        """Create and return a new PageTranslateTracker dedicated to cross-column merging."""
        page = PageTranslateTracker()
        self.cross_column.append(page)
        return page

    def to_json(self):
        pages = []
        for page in self.page:
            paragraphs = self.convert_paragraph(page)
            pages.append({"paragraph": paragraphs})
        cross_page = []
        for page in self.cross_page:
            paragraphs = self.convert_paragraph(page)
            cross_page.append({"paragraph": paragraphs})
        cross_column = []
        for page in self.cross_column:
            paragraphs = self.convert_paragraph(page)
            cross_column.append({"paragraph": paragraphs})
        return json.dumps(
            {
                "cross_page": cross_page,
                "cross_column": cross_column,
                "page": pages,
            },
            ensure_ascii=False,
            indent=2,
        )

    def convert_paragraph(self, page):
        paragraphs = []
        for para in page.paragraph:
            i_str = getattr(para, "input", None)
            o_str = getattr(para, "output", None)
            pdf_unicode = getattr(para, "pdf_unicode", None)
            llm_translate_trackers = getattr(para, "llm_translate_trackers", None)
            placeholders = getattr(para, "placeholders", None)
            original_placeholders = getattr(para, "original_placeholders", None)
            removed_hallucinated_placeholders = getattr(
                para,
                "removed_hallucinated_placeholders",
                None,
            )

            llm_translate_trackers_json = []
            if llm_translate_trackers:
                for tracker in llm_translate_trackers:
                    llm_translate_trackers_json.append(tracker.to_dict())

            placeholders_json = []
            if placeholders:
                for placeholder in placeholders:
                    placeholders_json.append(placeholder.to_dict())

            if pdf_unicode is None or i_str is None:
                continue
            paragraph_json = {
                "input": i_str,
                "output": o_str,
                "pdf_unicode": pdf_unicode,
                "llm_translate_trackers": llm_translate_trackers_json,
                "placeholders": placeholders_json,
                "multi_paragraph_id": getattr(para, "multi_paragraph_id", None),
                "multi_paragraph_index": getattr(para, "multi_paragraph_index", None),
                "original_placeholders": original_placeholders,
                "removed_hallucinated_placeholders": removed_hallucinated_placeholders,
            }
            paragraphs.append(
                paragraph_json,
            )
        return paragraphs


class PageTranslateTracker:
    def __init__(self):
        self.paragraph = []

    def new_paragraph(self):
        paragraph = ParagraphTranslateTracker()
        self.paragraph.append(paragraph)
        return paragraph


class ParagraphTranslateTracker:
    def __init__(self):
        self.llm_translate_trackers = []
        self.original_placeholders: dict[str, int] = {}
        self.removed_hallucinated_placeholders: dict[str, int] = {}

    def set_pdf_unicode(self, unicode: str):
        self.pdf_unicode = unicode

    def set_input(self, input_text: str):
        self.input = input_text

    def set_placeholders(
        self, placeholders: list[RichTextPlaceholder | FormulaPlaceholder]
    ):
        self.placeholders = placeholders

    def set_original_placeholders(self, placeholders: dict[str, int] | None):
        """Record original placeholder-like tokens from the source text."""
        self.original_placeholders = placeholders or {}

    def record_multi_paragraph_id(self, mid):
        self.multi_paragraph_id = mid

    def record_multi_paragraph_index(self, index):
        self.multi_paragraph_index = index

    def set_output(self, output: str):
        self.output = output

    def record_removed_hallucinated_placeholder(self, token: str):
        """Record placeholder-like tokens removed from translated text."""
        if not token:
            return
        self.removed_hallucinated_placeholders[token] = (
            self.removed_hallucinated_placeholders.get(token, 0) + 1
        )

    def new_llm_translate_tracker(self) -> LLMTranslateTracker:
        tracker = LLMTranslateTracker()
        self.llm_translate_trackers.append(tracker)
        return tracker

    def last_llm_translate_tracker(self) -> LLMTranslateTracker | None:
        if self.llm_translate_trackers:
            return self.llm_translate_trackers[-1]
        return None


class LLMTranslateTracker:
    def __init__(self):
        self.input = ""
        self.output = ""
        self.has_error = False
        self.error_message = ""
        self.placeholder_full_match = False
        self.fallback_to_translate = False

    def set_input(self, input_text: str):
        self.input = input_text

    def set_output(self, output_text: str):
        self.output = output_text

    def set_error_message(self, error_message: str):
        self.has_error = True
        self.error_message = error_message

    def set_placeholder_full_match(self):
        self.placeholder_full_match = True

    def set_fallback_to_translate(self):
        self.fallback_to_translate = True

    def to_dict(self):
        return {
            "input": self.input,
            "output": self.output,
            "has_error": self.has_error,
            "error_message": self.error_message,
            "placeholder_full_match": self.placeholder_full_match,
            "fallback_to_translate": self.fallback_to_translate,
        }


class ILTranslator:
    stage_name = "Translate Paragraphs"

    def __init__(
        self,
        translate_engine: BaseTranslator,
        translation_config: TranslationConfig,
        tokenizer=None,
    ):
        self.translate_engine = translate_engine
        self.translation_config = translation_config
        self.font_mapper = FontMapper(translation_config)
        self.shared_context_cross_split_part = (
            translation_config.shared_context_cross_split_part
        )
        if tokenizer is None:
            self.tokenizer = tiktoken.encoding_for_model("gpt-4o")
        else:
            self.tokenizer = tokenizer

        # Cache glossaries at initialization
        self._cached_glossaries = (
            self.shared_context_cross_split_part.get_glossaries_for_translation(
                self.translation_config.auto_extract_glossary
            )
        )

        self.support_llm_translate = False
        try:
            if translate_engine and hasattr(translate_engine, "do_llm_translate"):
                translate_engine.do_llm_translate(None)
                self.support_llm_translate = True
        except NotImplementedError:
            self.support_llm_translate = False

        self.use_as_fallback = False
        self.add_content_filter_hint_lock = threading.Lock()
        self.docs = None
        # PR-C1: observability only — does not change skip predicates.
        self.skip_report = SkipReport()
        # Near-full pull-quote → copy host ZH after the page pool finishes.
        # Keyed by id(quote); resolved by walking pages (do not re-match
        # on post-MT unicode).
        self._near_full_pullquotes: dict[int, dict] = {}

        # Pre-compile patterns for placeholder-like tokens that may be hallucinated by LLM.
        # We only consider the same shapes as our own formula & rich-text placeholders.
        self._formula_placeholder_pattern = re.compile(
            self.translate_engine.get_formular_placeholder(r"\d+")[1], re.IGNORECASE
        )
        self._style_left_placeholder_pattern = re.compile(
            self.translate_engine.get_rich_text_left_placeholder(r"\d+")[1],
            re.IGNORECASE,
        )
        self._style_right_placeholder_pattern = re.compile(
            self.translate_engine.get_rich_text_right_placeholder(r"\d+")[1],
            re.IGNORECASE,
        )

    def calc_token_count(self, text: str) -> int:
        try:
            return len(self.tokenizer.encode(text, disallowed_special=()))
        except Exception:
            return 0

    # Sentence terminators for completeness checks (EN→CJK body drop).
    # Avoid decimals (3.14) and ellipses counted as many ends.
    _EN_SENT_END_RE = re.compile(r"(?<!\d)[.!?](?!\d)(?=\s|$|[\"'”’）)])")
    _CJK_SENT_END_RE = re.compile(r"[。！？]")

    @classmethod
    def count_sentence_ends(cls, text: str) -> int:
        """Count sentence-ending punctuation (EN or CJK)."""
        if not text:
            return 0
        cjk_ends = len(cls._CJK_SENT_END_RE.findall(text))
        if cjk_ends > 0:
            return cjk_ends
        return len(cls._EN_SENT_END_RE.findall(text))

    @classmethod
    def translation_drops_sentences(cls, source: str, translated: str) -> bool:
        """True when MT/LLM clearly lost sentence(s) vs source.

        All Tied Up intro: EN 3 sentences (…ages? …phenomenon?) → ZH only 2
        (您想知道…？这是您幻想…？) with a large empty gap — layout empty, not
        overflow. Token-ratio 0.3 still accepts this; sentence count does not.
        """
        if not source or not translated:
            return False
        src_n = cls.count_sentence_ends(source)
        if src_n < 2:
            return False
        dst_n = cls.count_sentence_ends(translated)
        # Lost at least one full sentence (EN 3 → ZH 2, etc.)
        return dst_n <= src_n - 1

    #: Sentence terminator split for the same-sentence duplication gate.
    #: Splits after sentence-ending punctuation, consuming following spaces,
    #: when the next sentence starts with a letter/digit/CJK (no whitespace
    #: required — CJK sentences run together after 。/！/？).
    _DUP_SENT_SPLIT_RE = re.compile(
        r"(?<=[.!?。！？])\s*(?=[A-Za-z0-9\u4e00-\u9fff])"
    )
    #: Token extraction for normalized sentence comparison (EN + CJK).
    _DUP_TOKEN_RE = re.compile(r"[A-Za-z0-9\u4e00-\u9fff]+")

    @classmethod
    def split_sentences(cls, text: str) -> list[str]:
        """Split *text* into sentences on sentence-ending punctuation."""
        if not text:
            return []
        return [s.strip() for s in cls._DUP_SENT_SPLIT_RE.split(text) if s.strip()]

    @classmethod
    def _sentence_tokens(cls, sentence: str) -> tuple[str, list[str]]:
        tokens = cls._DUP_TOKEN_RE.findall(sentence.lower())
        return "".join(tokens), tokens

    @classmethod
    def find_consecutive_duplicate_sentences(
        cls,
        text: str,
        *,
        min_chars: int = 8,
        min_near_chars: int = 15,
        min_tokens: int = 3,
        near_overlap: float = 0.6,
    ) -> list[tuple[str, str]]:
        """Return ``[(sentence, kind)]`` for consecutive same-sentence runs.

        Acceptance V4: a translated paragraph must not contain the same
        sentence twice in a row (assembly bugs merge one span into the MT
        input repeatedly).  ``kind`` is ``"exact"`` (normalized equality) or
        ``"near"`` (a shorter fragment is token-covered by the adjacent
        sentence — catches pull-quote fragments glued to their host).
        """
        sentences = cls.split_sentences(text)
        out: list[tuple[str, str]] = []
        for a, b in zip(sentences, sentences[1:]):
            na, ta = cls._sentence_tokens(a)
            nb, tb = cls._sentence_tokens(b)
            if na and na == nb and len(na) >= min_chars:
                out.append((a, "exact"))
                continue
            if not ta or not tb:
                continue
            if min(len(ta), len(tb)) < min_tokens:
                continue
            if len(na) < min_near_chars and len(nb) < min_near_chars:
                continue
            inter = len(set(ta) & set(tb))
            if inter / min(len(ta), len(tb)) >= near_overlap:
                out.append((a, "near"))
        return out

    #: Untranslated "Chapter N" marker (chapter names are titles to translate,
    #: not chrome to keep EN; MT often leaves the marker English, e.g. p82
    #: "Chapter9直接卷曲").
    _CHAPTER_MARKER_RE = re.compile(r"\bChapter\s*(\d{1,3})(?!\d)", re.IGNORECASE)
    #: Rich-text bold markers that split a chapter marker ("Chapter " bold +
    #: "9" regular) and make MT fuse it into "Chapter9直接卷曲".
    _RICH_TEXT_MARKER_RE = re.compile(r"[〖\u3016]/?[Bb]\d+[〗\u3017]")
    #: A complete ``Chapter N`` marker can be translated without discarding
    #: its source style.  Split markers are handled by the legacy fallback
    #: below because there is no single style span to preserve.
    _RICH_TEXT_CHAPTER_RE = re.compile(
        r"(?P<open>[〖\u3016][Bb](?P<id>\d+)[〗\u3017])"
        r"(?P<lead>\s*)Chapter\s*(?P<number>\d{1,3})(?P<trail>\s*)"
        r"(?P<close>[〖\u3016]/[Bb](?P=id)[〗\u3017])",
        re.IGNORECASE,
    )
    # DeepLX leftover after 〖b0〗chapter〖/b0〗8 → 章b08 / 章节b05 / 章b012.
    # Span id is one digit (first emphasis run); the rest is the chapter index.
    _MANGLED_BN_CHAPTER_RE = re.compile(
        r"(?:章节|章)\s*[bB](?P<sid>\d)(?P<num>\d{1,3})(?!\d)"
    )
    # 〖b08〗 / 〖b012〗 is span 0 fused with the chapter index (embed never
    # zero-pads: span 8 is 〖B8〗). Rewrite before the generic marker strip
    # so the digits are not deleted as a fake span id.
    _FUSED_B0_MARKER_RE = re.compile(
        r"(?:章节|章)?\s*〖[Bb]0(?P<num>\d{1,3})〗(?:\s*〖/[Bb]0(?P=num)〗)?"
    )
    _CJK_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")
    _CN_DIGITS = "零一二三四五六七八九"

    @classmethod
    def _cn_numeral(cls, n: int) -> str:
        """Convert 1..999 to Chinese numerals (3 -> 三, 19 -> 十九, 120 -> 一百二十)."""
        if n <= 0 or n >= 1000:
            return str(n)
        if n < 10:
            return cls._CN_DIGITS[n]
        if n < 20:
            return "十" + (cls._CN_DIGITS[n - 10] if n % 10 else "")
        if n < 100:
            tens, ones = divmod(n, 10)
            return cls._CN_DIGITS[tens] + "十" + (cls._CN_DIGITS[ones] if ones else "")
        hundreds = n // 100
        rest = n % 100
        out = cls._CN_DIGITS[hundreds] + "百"
        if not rest:
            return out
        if rest < 10:
            return out + "零" + cls._CN_DIGITS[rest]
        return out + cls._cn_numeral(rest)

    @classmethod
    def fix_untranslated_chapter_markers(cls, text: str) -> str:
        """Replace ``Chapter N`` (plain or rich-text-split) with ``第N章``.

        Chapter names are titles to translate; MT often leaves the marker
        English (p82 "Chapter9直接卷曲").  A complete rich-text span keeps its
        style while a marker split across spans uses the compatibility fallback
        and is flattened before the engine sees a clean ``第N章`` input.
        """
        if not text:
            return text

        # Preserve a style span when it contains the complete chapter marker.
        # Placeholders avoid stripping these protected markers in the fallback
        # cleanup, while keeping the implementation independent of the marker
        # ids chosen by the upstream translator.
        protected: list[str] = []

        def _protect_rich_chapter(match: re.Match) -> str:
            try:
                n = int(match.group("number"))
            except (TypeError, ValueError):
                return match.group(0)
            token = f"__RICH_CHAPTER_{len(protected)}__"
            replacement = (
                match.group("open")
                + match.group("lead")
                + "第"
                + cls._cn_numeral(n)
                + "章"
                + match.group("trail")
                + match.group("close")
            )
            protected.append(replacement)
            return token

        protected_text = cls._RICH_TEXT_CHAPTER_RE.sub(
            _protect_rich_chapter, text
        )

        def _fused(m: re.Match) -> str:
            try:
                n = int(m.group("num"))
            except (TypeError, ValueError):
                return m.group(0)
            return "第" + cls._cn_numeral(n) + "章"

        protected_text = cls._FUSED_B0_MARKER_RE.sub(_fused, protected_text)
        cleaned = cls._RICH_TEXT_MARKER_RE.sub("", protected_text)

        def _repl(m: re.Match) -> str:
            try:
                n = int(m.group(1))
            except (TypeError, ValueError):
                return m.group(0)
            return "第" + cls._cn_numeral(n) + "章"

        fixed = cls._CHAPTER_MARKER_RE.sub(_repl, cleaned)
        for index, replacement in enumerate(protected):
            fixed = fixed.replace(f"__RICH_CHAPTER_{index}__", replacement)

        def _mangled(m: re.Match) -> str:
            try:
                n = int(m.group("num"))
            except (TypeError, ValueError):
                return m.group(0)
            return "第" + cls._cn_numeral(n) + "章"

        fixed = cls._MANGLED_BN_CHAPTER_RE.sub(_mangled, fixed)
        if fixed == text:
            return text  # nothing changed: keep markers untouched
        return fixed

    def _maybe_write_skip_report(self) -> None:
        """Write skip_report.json when debug/working_dir (same gate as tracking)."""
        if not (
            self.translation_config.debug
            or self.translation_config.working_dir is not None
        ):
            return
        path = self.translation_config.get_working_file_path("skip_report.json")
        try:
            self.skip_report.write_json(path)
            logger.debug(
                "save skip report to %s (%s events)",
                path,
                self.skip_report.to_dict().get("total", 0),
            )
        except Exception:
            logger.exception("failed to write skip_report.json to %s", path)

    def record_skip(
        self,
        page: Page | None,
        paragraph: PdfParagraph,
        reason: SkipReason | str,
        *,
        debug_extra: dict | None = None,
    ) -> None:
        """Record a skip event (thread-safe). No-op effect on translation."""
        extra = debug_extra if getattr(self.translation_config, "debug", False) else None
        self.skip_report.record(
            page=page,
            paragraph=paragraph,
            reason=reason,
            debug_extra=extra,
        )

    def _classify_near_full_pullquotes(self, page: Page) -> None:
        """Stash near-full quote→host pairs while unicode is still pre-MT EN."""
        stash = getattr(self, "_near_full_pullquotes", None)
        if stash is None:
            self._near_full_pullquotes = {}
            stash = self._near_full_pullquotes
        for paragraph in getattr(page, "pdf_paragraph", None) or []:
            host = find_pullquote_host(paragraph, page)
            if host is None or not is_near_full_pullquote(paragraph, host):
                continue
            stash[id(paragraph)] = {
                "host_obj_id": id(host),
                "quote_debug_id": getattr(paragraph, "debug_id", None),
                "host_debug_id": getattr(host, "debug_id", None),
                "kind": "near_full",
            }

    @staticmethod
    def _apply_zh_to_quote(quote: PdfParagraph, zh: str) -> None:
        """Replace quote text with host ZH; keep quote style/box, not host comps."""
        ssu = PdfSameStyleUnicodeCharacters(pdf_style=quote.pdf_style, unicode=zh)
        quote.unicode = zh
        quote.pdf_paragraph_composition = [
            PdfParagraphComposition(pdf_same_style_unicode_characters=ssu)
        ]

    def _apply_stashed_near_full_pullquotes(self) -> None:
        """Copy host ZH onto near-full quotes after MT. Match by id(), not text."""
        stash = getattr(self, "_near_full_pullquotes", None)
        if not stash:
            return
        docs = getattr(self, "docs", None)
        if docs is None:
            return
        by_id: dict[int, PdfParagraph] = {}
        for page in docs.page:
            for para in getattr(page, "pdf_paragraph", None) or []:
                by_id[id(para)] = para
        for quote_id, info in list(stash.items()):
            if info.get("kind") != "near_full":
                continue
            quote = by_id.get(quote_id)
            host = by_id.get(info.get("host_obj_id"))  # type: ignore[arg-type]
            if quote is None or host is None:
                continue
            host_zh = getattr(host, "unicode", None) or ""
            if self._CJK_CHAR_RE.search(host_zh):
                self._apply_zh_to_quote(quote, host_zh)
        stash.clear()

    def region_skip_reason(
        self,
        page: Page,
        paragraph: PdfParagraph,
    ) -> SkipReason | None:
        """Classify figure/header/footer skip (PR-C2 safer bounds)."""
        if self.should_skip_figure_text_paragraph(page, paragraph):
            return SkipReason.FIGURE_TEXT
        band = classify_header_footer_skip(
            page,
            paragraph,
            skip_header=self.translation_config.skip_header,
            skip_footer=self.translation_config.skip_footer,
            header_height=self.translation_config.header_height,
            footer_height=self.translation_config.footer_height,
            ocr_workaround=bool(
                getattr(self.translation_config, "ocr_workaround", False)
            ),
        )
        if band is None:
            return None
        return {
            "header": SkipReason.HEADER,
            "footer": SkipReason.FOOTER,
            "url_chrome": SkipReason.URL_CHROME,
            "page_number": SkipReason.PAGE_NUMBER,
        }.get(band)

    def translate(self, docs: Document):
        self.docs = docs
        self.skip_report.clear()
        self._near_full_pullquotes.clear()
        tracker = DocumentTranslateTracker()

        if not self.translation_config.shared_context_cross_split_part.first_paragraph:
            # Try to find the first title paragraph
            title_paragraph = self.find_title_paragraph(docs)
            self.translation_config.shared_context_cross_split_part.first_paragraph = (
                self.shared_context_cross_split_part.snapshot_title_paragraph(
                    title_paragraph
                )
            )
            self.translation_config.shared_context_cross_split_part.recent_title_paragraph = self.shared_context_cross_split_part.snapshot_title_paragraph(
                title_paragraph
            )
            if title_paragraph:
                logger.info(f"Found first title paragraph: {title_paragraph.unicode}")

        # count total paragraph
        total = sum(len(page.pdf_paragraph) for page in docs.page)
        with self.translation_config.progress_monitor.stage_start(
            self.stage_name,
            total,
        ) as pbar:
            with PriorityThreadPoolExecutor(
                max_workers=self.translation_config.pool_max_workers,
            ) as executor:
                for page in docs.page:
                    self.process_page(page, executor, pbar, tracker.new_page())

        self._apply_stashed_near_full_pullquotes()

        path = self.translation_config.get_working_file_path("translate_tracking.json")

        if (
            self.translation_config.debug
            or self.translation_config.working_dir is not None
        ):
            logger.debug(f"save translate tracking to {path}")
            with Path(path).open("w", encoding="utf-8") as f:
                f.write(tracker.to_json())
        self._maybe_write_skip_report()

    def find_title_paragraph(self, docs: Document) -> PdfParagraph | None:
        """Find the first paragraph with layout_label 'title' in the document.

        Args:
            docs: The document to search in

        Returns:
            The first title paragraph found, or None if no title paragraph exists
        """
        for page in docs.page:
            for paragraph in page.pdf_paragraph:
                if self.should_skip_region_paragraph(page, paragraph):
                    continue
                if paragraph.layout_label == "title":
                    logger.info(f"Found title paragraph: {paragraph.unicode}")
                    return paragraph
        return None

    def process_page(
        self,
        page: Page,
        executor: PriorityThreadPoolExecutor,
        pbar: tqdm | None = None,
        tracker: PageTranslateTracker = None,
    ):
        self.translation_config.raise_if_cancelled()
        # Decide near-full on pre-MT EN. Hosts submit first (longer →
        # lower priority number) and would make a later rematch miss.
        self._classify_near_full_pullquotes(page)
        for paragraph in page.pdf_paragraph:
            region_reason = self.region_skip_reason(page, paragraph)
            if region_reason is not None:
                self.record_skip(page, paragraph, region_reason)
                if pbar:
                    pbar.advance(1)
                continue
            page_font_map = {}
            for font in page.pdf_font:
                page_font_map[font.font_id] = font
            page_xobj_font_map = {}
            for xobj in page.pdf_xobject:
                page_xobj_font_map[xobj.xobj_id] = page_font_map.copy()
                for font in xobj.pdf_font:
                    page_xobj_font_map[xobj.xobj_id][font.font_id] = font
            # self.translate_paragraph(paragraph, pbar,tracker.new_paragraph(), page_font_map, page_xobj_font_map)
            paragraph_token_count = self.calc_token_count(paragraph.unicode)
            if paragraph.layout_label == "title":
                self.shared_context_cross_split_part.recent_title_paragraph = (
                    self.shared_context_cross_split_part.snapshot_title_paragraph(
                        paragraph
                    )
                )
            executor.submit(
                self.translate_paragraph,
                paragraph,
                page,
                pbar,
                tracker.new_paragraph(),
                page_font_map,
                page_xobj_font_map,
                priority=1048576 - paragraph_token_count,
                paragraph_token_count=paragraph_token_count,
                title_paragraph=self.translation_config.shared_context_cross_split_part.first_paragraph,
                local_title_paragraph=self.translation_config.shared_context_cross_split_part.recent_title_paragraph,
            )

    def should_skip_figure_text_paragraph(
        self,
        page: Page,
        paragraph: PdfParagraph,
    ) -> bool:
        """Skip MT for in-figure labels when ``translate_figure_text`` is off."""
        if self.translation_config.translate_figure_text:
            return False
        return is_figure_text_paragraph(
            paragraph,
            page,
            coverage_threshold=FIGURE_TEXT_COVERAGE_THRESHOLD,
        )

    def should_skip_header_footer_paragraph(
        self,
        page: Page,
        paragraph: PdfParagraph,
    ) -> bool:
        """Skip paragraphs fully inside configured header/footer bands.

        Never skips ``title`` / ``section_header``, or body-like long prose
        that only geometrically sits in the band (PR-C2). OCR dual-layer
        never uses header/footer skip (white-fill would blank ZH).
        """
        return should_skip_header_footer(
            page,
            paragraph,
            skip_header=self.translation_config.skip_header,
            skip_footer=self.translation_config.skip_footer,
            header_height=self.translation_config.header_height,
            footer_height=self.translation_config.footer_height,
            ocr_workaround=bool(
                getattr(self.translation_config, "ocr_workaround", False)
            ),
        )

    def should_skip_region_paragraph(
        self,
        page: Page,
        paragraph: PdfParagraph,
    ) -> bool:
        """Aggregate skip policies before MT (figure labels + header/footer)."""
        if self.should_skip_figure_text_paragraph(page, paragraph):
            return True
        return self.should_skip_header_footer_paragraph(page, paragraph)

    class TranslateInput:
        def __init__(
            self,
            unicode: str,
            placeholders: list[RichTextPlaceholder | FormulaPlaceholder],
            base_style: PdfStyle = None,
        ):
            self.unicode = unicode
            self.placeholders = placeholders
            self.base_style = base_style
            # Original placeholder-like tokens extracted from the source text.
            # Key: exact matched token string; Value: occurrence count.
            self.original_placeholder_tokens: dict[str, int] = {}
            # Non-LLM emphasis spans (〖Bn〗…〖/Bn〗 + source for rewrap).
            self.style_spans: list[StyleSpan] = []

        def set_original_placeholder_tokens(self, tokens: dict[str, int] | None):
            """Attach original placeholder-like tokens from source text."""
            self.original_placeholder_tokens = tokens or {}

        def get_placeholders_hint(self) -> dict[str, str] | None:
            hint = {}
            for placeholder in self.placeholders:
                if isinstance(placeholder, FormulaPlaceholder):
                    cid_count = 0
                    for char in placeholder.formula.pdf_character:
                        if re.match(r"^\(cid:\d+\)$", char.char_unicode):
                            cid_count += 1
                    if cid_count > len(placeholder.formula.pdf_character) * 0.8:
                        continue

                    hint[placeholder.placeholder] = get_char_unicode_string(
                        placeholder.formula.pdf_character
                    )
            if hint:
                return hint
            return None

    def create_formula_placeholder(
        self,
        formula: PdfFormula,
        formula_id: int,
        paragraph: PdfParagraph,
    ):
        placeholder = self.translate_engine.get_formular_placeholder(formula_id)
        if isinstance(placeholder, tuple):
            placeholder, regex_pattern = placeholder
        else:
            regex_pattern = re.escape(placeholder)
        if re.match(regex_pattern, paragraph.unicode, re.IGNORECASE):
            return self.create_formula_placeholder(formula, formula_id + 1, paragraph)

        return FormulaPlaceholder(formula_id, formula, placeholder, regex_pattern)

    def create_rich_text_placeholder(
        self,
        composition: PdfSameStyleCharacters,
        composition_id: int,
        paragraph: PdfParagraph,
    ):
        left_placeholder = self.translate_engine.get_rich_text_left_placeholder(
            composition_id,
        )
        right_placeholder = self.translate_engine.get_rich_text_right_placeholder(
            composition_id,
        )
        if isinstance(left_placeholder, tuple):
            left_placeholder, left_placeholder_regex_pattern = left_placeholder
        else:
            left_placeholder_regex_pattern = re.escape(left_placeholder)
        if isinstance(right_placeholder, tuple):
            right_placeholder, right_placeholder_regex_pattern = right_placeholder
        else:
            right_placeholder_regex_pattern = re.escape(right_placeholder)
        if re.match(
            f"{left_placeholder_regex_pattern}|{right_placeholder_regex_pattern}",
            paragraph.unicode,
            re.IGNORECASE,
        ):
            return self.create_rich_text_placeholder(
                composition,
                composition_id + 1,
                paragraph,
            )

        return RichTextPlaceholder(
            composition_id,
            composition,
            left_placeholder,
            right_placeholder,
            left_placeholder_regex_pattern,
            right_placeholder_regex_pattern,
        )

    def get_translate_input(
        self,
        paragraph: PdfParagraph,
        page_font_map: dict[str, PdfFont] = None,
        disable_rich_text_translate: bool | None = None,
        page: Page | None = None,
    ):
        if not paragraph.pdf_paragraph_composition:
            self.record_skip(page, paragraph, SkipReason.EMPTY_COMPOSITION)
            return

        # Skip pure numeric paragraphs
        if is_pure_numeric_paragraph(paragraph):
            self.record_skip(page, paragraph, SkipReason.PURE_NUMERIC)
            return None

        # Skip paragraphs with only placeholders
        if is_placeholder_only_paragraph(paragraph):
            self.record_skip(page, paragraph, SkipReason.PLACEHOLDER_ONLY)
            return None

        # Extract original placeholder-like tokens from the raw paragraph text
        original_placeholder_tokens: dict[str, int] = {}

        def scan_placeholder_tokens(text: str, tokens: dict[str, int]):
            for pattern in (
                self._formula_placeholder_pattern,
                self._style_left_placeholder_pattern,
                self._style_right_placeholder_pattern,
            ):
                for match in pattern.finditer(text):
                    token = match.group(0)
                    tokens[token] = tokens.get(token, 0) + 1

        if paragraph.unicode:
            scan_placeholder_tokens(paragraph.unicode, original_placeholder_tokens)
        if len(paragraph.pdf_paragraph_composition) == 1:
            # 如果整个段落只有一个组成部分，那么直接返回，不需要套占位符等
            composition = paragraph.pdf_paragraph_composition[0]
            if (
                composition.pdf_line
                or composition.pdf_same_style_characters
                or composition.pdf_character
            ):
                mt_chars = []
                if composition.pdf_line and composition.pdf_line.pdf_character:
                    mt_chars = list(composition.pdf_line.pdf_character)
                elif (
                    composition.pdf_same_style_characters
                    and composition.pdf_same_style_characters.pdf_character
                ):
                    mt_chars = list(
                        composition.pdf_same_style_characters.pdf_character
                    )
                elif composition.pdf_character:
                    mt_chars = [composition.pdf_character]
                mt_text = (
                    assemble_midcap_title_unicode(paragraph, mt_chars)
                    if mt_chars
                    else (paragraph.unicode or "")
                )
                translate_input = self.TranslateInput(
                    mt_text,
                    [],
                    paragraph.pdf_style,
                )
                translate_input.set_original_placeholder_tokens(
                    original_placeholder_tokens,
                )
                return translate_input
            elif composition.pdf_formula:
                # 不需要翻译纯公式
                return None
            elif composition.pdf_same_style_unicode_characters:
                # DEBUG INSERT CHAR, NOT TRANSLATE
                return None
            else:
                logger.error(
                    f"Unknown composition type. "
                    f"Composition: {composition}. "
                    f"Paragraph: {paragraph}. ",
                )
                return None

        # 如果没有指定 disable_rich_text_translate，使用配置中的值
        if disable_rich_text_translate is None:
            disable_rich_text_translate = (
                self.translation_config.disable_rich_text_translate
            )

        placeholder_id = 1
        placeholders = []
        chars = []
        style_spans: list[StyleSpan] = []
        compositions = list(paragraph.pdf_paragraph_composition or [])
        visual_split_ids = visual_known_split_char_ids(
            flatten_composition_pdf_chars(compositions)
        )
        i_comp = 0
        while i_comp < len(compositions):
            composition = compositions[i_comp]
            if composition.pdf_line:
                chars.extend(composition.pdf_line.pdf_character)
                i_comp += 1
            elif composition.pdf_formula:
                fchars = composition.pdf_formula.pdf_character or []
                frag = "".join(
                    text_recovery.expand_latin_ligatures(c.char_unicode or "")
                    for c in fchars
                )
                if text_recovery.should_join_hyphen_wrap(
                    text_recovery.mixed_chars_stem(chars), frag
                ) or (
                    visual_split_ids
                    and any(id(c) in visual_split_ids for c in fchars)
                ):
                    # Ligature / hyphen-wrap / visual-split tail as formula.
                    chars.extend(fchars)
                    i_comp += 1
                    continue
                formula_placeholder = self.create_formula_placeholder(
                    composition.pdf_formula,
                    placeholder_id,
                    paragraph,
                )
                placeholders.append(formula_placeholder)
                # 公式只需要一个占位符，所以 id+1
                placeholder_id = formula_placeholder.id + 1
                chars.extend(formula_placeholder.placeholder)
                i_comp += 1
            elif composition.pdf_character:
                chars.append(composition.pdf_character)
                i_comp += 1
            elif composition.pdf_same_style_characters:
                comp_style = composition.pdf_same_style_characters.pdf_style
                base_style = paragraph.pdf_style

                if disable_rich_text_translate:
                    # Non-LLM path: any different font_id implies intentional
                    # visual distinction (bold, italic, different typeface).
                    if (
                        is_same_style(comp_style, base_style)
                        or is_same_style_except_size(comp_style, base_style)
                    ):
                        chars.extend(
                            composition.pdf_same_style_characters.pdf_character,
                        )
                        i_comp += 1
                        continue

                    # Merge line-broken same-style runs, then wrap 〖Bn〗.
                    span_chars, span_style, i_comp = coalesce_emphasis_style_run(
                        compositions, i_comp, base_style
                    )
                    # OA p3 Trajan [space][W][space]: wrapping isolates W from
                    # elcome and DeepLX leaves a literal W in the ZH.
                    if is_drop_cap_style_span(span_chars):
                        chars.extend(span_chars)
                        continue
                    if text_recovery.should_join_hyphen_wrap(
                        text_recovery.mixed_chars_stem(chars),
                        get_char_unicode_string(span_chars),
                    ) or (
                        visual_split_ids
                        and any(id(c) in visual_split_ids for c in span_chars)
                    ):
                        # Do not isolate ``ﬀ`` / ``ly`` / visual-split tails.
                        chars.extend(span_chars)
                        continue
                    span_id = len(style_spans)
                    source_text = get_char_unicode_string(span_chars)
                    chars.append(f"〖B{span_id}〗")
                    chars.extend(span_chars)
                    chars.append(f"〖/B{span_id}〗")
                    style_spans.append(
                        StyleSpan(span_id, span_style, source_text)
                    )
                    continue

                fonta = self.font_mapper.map(
                    page_font_map[
                        composition.pdf_same_style_characters.pdf_style.font_id
                    ],
                    "1",
                )
                fontb = self.font_mapper.map(
                    page_font_map[paragraph.pdf_style.font_id],
                    "1",
                )
                if (
                    # 样式和段落基准样式一致，无需占位符
                    is_same_style(
                        composition.pdf_same_style_characters.pdf_style,
                        paragraph.pdf_style,
                    )
                    # 字号差异在 0.7-1.3 之间，可能是首字母变大效果，无需占位符
                    or is_same_style_except_size(
                        composition.pdf_same_style_characters.pdf_style,
                        paragraph.pdf_style,
                    )
                    or (
                        # 除了字体以外样式都和基准一样，并且字体都映射到同一个字体。无需占位符
                        is_same_style_except_font(
                            composition.pdf_same_style_characters.pdf_style,
                            paragraph.pdf_style,
                        )
                        and fonta
                        and fontb
                        and fonta.font_id == fontb.font_id
                    )
                    # or len(composition.pdf_same_style_characters.pdf_character) == 1
                ):
                    chars.extend(composition.pdf_same_style_characters.pdf_character)
                    i_comp += 1
                else:
                    placeholder = self.create_rich_text_placeholder(
                        composition.pdf_same_style_characters,
                        placeholder_id,
                        paragraph,
                    )
                    placeholders.append(placeholder)
                    # 样式需要一左一右两个占位符，所以 id+2
                    placeholder_id = placeholder.id + 2
                    chars.append(placeholder.left_placeholder)
                    chars.extend(
                        composition.pdf_same_style_characters.pdf_character
                    )
                    chars.append(placeholder.right_placeholder)
                    i_comp += 1
            else:
                logger.error(
                    "Unexpected PdfParagraphComposition type "
                    "in PdfParagraph during translation. "
                    f"Composition: {composition}. "
                    f"Paragraph: {paragraph}. ",
                )
                return None

            # 如果占位符数量超过阈值，且未禁用富文本翻译，则递归调用并禁用富文本翻译
            if len(placeholders) > 40 and not disable_rich_text_translate:
                logger.warning(
                    f"Too many placeholders ({len(placeholders)}) in paragraph[{paragraph.debug_id}], "
                    "disabling rich text translation for this paragraph",
                )
                return self.get_translate_input(
                    paragraph, page_font_map, True, page=page
                )

        # Climb + drop-cap prep is single-sourced in get_char_unicode_string.
        para_w = None
        box = getattr(paragraph, "box", None)
        if box is not None and box.x is not None and box.x2 is not None:
            para_w = float(box.x2 - box.x)
        text = assemble_midcap_title_unicode(
            paragraph, chars, para_width=para_w
        )
        translate_input = self.TranslateInput(text, placeholders, paragraph.pdf_style)
        translate_input.set_original_placeholder_tokens(original_placeholder_tokens)

        # Style spans now contain (span_id, PdfStyle) from marker wrapping.
        # The markers are already embedded in the text; style_spans info
        # is passed through for post-translation marker parsing.
        if style_spans:
            translate_input.style_spans = style_spans
            logger.debug(
                "Style markers embedded: %d span(s) in paragraph[%s]",
                len(style_spans),
                paragraph.debug_id,
            )

        return translate_input

    def process_formula(
        self,
        formula: PdfFormula,
        formula_id: int,
        paragraph: PdfParagraph,
    ):
        placeholder = self.create_formula_placeholder(formula, formula_id, paragraph)
        if placeholder.placeholder in paragraph.unicode:
            return self.process_formula(formula, formula_id + 1, paragraph)

        return placeholder

    def process_composition(
        self,
        composition: PdfSameStyleCharacters,
        composition_id: int,
        paragraph: PdfParagraph,
    ):
        placeholder = self.create_rich_text_placeholder(
            composition,
            composition_id,
            paragraph,
        )
        if (
            placeholder.left_placeholder in paragraph.unicode
            or placeholder.right_placeholder in paragraph.unicode
        ):
            return self.process_composition(
                composition,
                composition_id + 1,
                paragraph,
            )

        return placeholder


    _MARKER_RE = re.compile(r"〖[Bb]\d+〗|〖/[Bb]\d+〗")

    @staticmethod
    def _strip_style_markers(text: str) -> str:
        """Remove any residual style markers from text.

        Safety net for cases where markers survive translation but
        style_spans is empty (e.g. cached translations from a previous
        run where markers were embedded but the new TranslateInput has
        no style_spans).
        """
        return ILTranslator._MARKER_RE.sub("", text)

    # Heading patterns for CJK localization:
    # "第N课. 小事..." → "第N课：小事..."
    # "第5章. 内容..." → "第5章：内容..."
    _HEADING_PUNCT_RE = re.compile(
        r"^(第?\d+(?:课|章|节|天|部分|篇|讲|回))\.\s*"
    )

    @staticmethod
    def _localize_heading_punctuation(text: str) -> str:
        """Convert heading separator '.' to '：' for CJK output.

        Rules:
        - Only matches recognized heading patterns (第N课, 第N章, etc.)
        - Does NOT replace '.' between digits (e.g. "2.5", "v3.0")
        - Only replaces the FIRST '.' in the heading prefix
        """
        m = ILTranslator._HEADING_PUNCT_RE.match(text)
        if m:
            # Protect decimal numbers: check if '.' is between digits
            dot_pos = m.end() - 1  # position of the '.'
            if dot_pos > 0 and dot_pos < len(text) - 1:
                if text[dot_pos - 1].isdigit() and text[dot_pos + 1].isdigit():
                    return text  # "2.5" — don't replace
            return text[:m.end()].replace(".", "：", 1) + text[m.end():]

        # Also handle already-translated CJK heading + "."
        # Pattern: CJK chars + digits + "." + space/content
        m2 = re.match(r"^([一-鿿぀-ヿ]+\d+)\.\s+", text)
        if m2:
            return text[:m2.end()].replace(".", "：", 1) + text[m2.end():]

        return text

    @staticmethod
    def _is_cjk_char(ch: str) -> bool:
        """Check if a single character is CJK (Chinese/Japanese/Korean)."""
        cp = ord(ch)
        return (
            (0x4E00 <= cp <= 0x9FFF)  # CJK Unified Ideographs
            or (0x3400 <= cp <= 0x4DBF)  # CJK Unified Ideographs Extension A
            or (0x3000 <= cp <= 0x303F)  # CJK Symbols and Punctuation
            or (0x3040 <= cp <= 0x309F)  # Hiragana
            or (0x30A0 <= cp <= 0x30FF)  # Katakana
            or (0xAC00 <= cp <= 0xD7AF)  # Hangul Syllables
            or (0xFF00 <= cp <= 0xFFEF)  # Halfwidth and Fullwidth Forms
            or (0x2E80 <= cp <= 0x2EFF)  # CJK Radicals Supplement
            or (0xFE30 <= cp <= 0xFE4F)  # CJK Compatibility Forms
        )

    @classmethod
    def _snap_to_char_boundary(cls, text: str, pos: int, snap_left: bool) -> int:
        """Snap a position out of the middle of a Latin word.

        CJK characters are each one Python string index, so positions between
        CJK chars are already valid boundaries and need no snapping.  This
        method only adjusts positions that would split a Latin-script word.

        Args:
            text: The output text.
            pos: The position to snap.
            snap_left: If True, snap left (for start boundaries).
                       If False, snap right (for end boundaries).

        Returns:
            Snapped position in [0, len(text)].
        """
        pos = max(0, min(pos, len(text)))
        if pos == 0 or pos == len(text):
            return pos

        ch_before = text[pos - 1]
        ch_after = text[pos] if pos < len(text) else ""

        # At a CJK boundary → already valid
        if cls._is_cjk_char(ch_before) or cls._is_cjk_char(ch_after):
            return pos
        # At a space boundary → already valid
        if ch_before == " " or ch_after == " ":
            return pos

        # Inside a Latin word → snap to the nearest space or CJK boundary
        if snap_left:
            while pos > 0 and text[pos - 1] != " " and not cls._is_cjk_char(text[pos - 1]):
                pos -= 1
        else:
            while pos < len(text) and text[pos] != " " and not cls._is_cjk_char(text[pos]):
                pos += 1
        return pos

    def _parse_style_markers(
        self,
        output: str,
        input_text: TranslateInput,
    ) -> list[PdfParagraphComposition]:
        """Parse 〖Bn〗 spans from MT output; rewrap dropped markers first.

        See ``style_marker_recover.rewrap_styles_from_source`` for recovery
        when DeepLX strips QBS/QES but leaves the English term.
        """
        result: list[PdfParagraphComposition] = []
        marker_re = re.compile(r"〖[Bb](\d+)〗([\s\S]*?)〖/[Bb]\1〗")

        recovered = rewrap_styles_from_source(output, input_text.style_spans)
        if recovered:
            output = recovered

        styles = style_by_id(input_text.style_spans)
        last_end = 0
        for m in marker_re.finditer(output):
            span_id = int(m.group(1))
            styled_text = m.group(2)

            if m.start() > last_end:
                unstyled = ILTranslator._strip_style_markers(
                    output[last_end : m.start()]
                )
                if unstyled.strip():
                    comp = PdfParagraphComposition()
                    comp.pdf_same_style_unicode_characters = (
                        PdfSameStyleUnicodeCharacters()
                    )
                    comp.pdf_same_style_unicode_characters.unicode = unstyled
                    comp.pdf_same_style_unicode_characters.pdf_style = (
                        input_text.base_style
                    )
                    result.append(comp)

            if styled_text.strip():
                comp = PdfParagraphComposition()
                comp.pdf_same_style_unicode_characters = (
                    PdfSameStyleUnicodeCharacters()
                )
                comp.pdf_same_style_unicode_characters.unicode = styled_text
                style = styles.get(span_id)
                if style:
                    # Keep font_id + color; normalize size to body.
                    merged = copy.deepcopy(style)
                    if input_text.base_style and input_text.base_style.font_size:
                        merged.font_size = input_text.base_style.font_size
                    comp.pdf_same_style_unicode_characters.pdf_style = merged
                else:
                    comp.pdf_same_style_unicode_characters.pdf_style = (
                        input_text.base_style
                    )
                result.append(comp)

            last_end = m.end()

        if last_end < len(output):
            remaining = ILTranslator._strip_style_markers(output[last_end:])
            if remaining.strip():
                comp = PdfParagraphComposition()
                comp.pdf_same_style_unicode_characters = (
                    PdfSameStyleUnicodeCharacters()
                )
                comp.pdf_same_style_unicode_characters.unicode = remaining
                comp.pdf_same_style_unicode_characters.pdf_style = (
                    input_text.base_style
                )
                result.append(comp)

        if not result:
            if "〖B" in output or "〖b" in output:
                logger.warning(
                    "Markers NOT parsed but present in output (preview=%s)",
                    output[:200],
                )
            comp = PdfParagraphComposition()
            comp.pdf_same_style_unicode_characters = PdfSameStyleUnicodeCharacters()
            comp.pdf_same_style_unicode_characters.unicode = (
                ILTranslator._strip_style_markers(output)
            )
            comp.pdf_same_style_unicode_characters.pdf_style = (
                input_text.base_style
            )
            return [comp]

        for comp in result:
            uni = (
                comp.pdf_same_style_unicode_characters
                and comp.pdf_same_style_unicode_characters.unicode
            )
            if uni and ("〖B" in uni or "〖b" in uni):
                comp.pdf_same_style_unicode_characters.unicode = (
                    ILTranslator._strip_style_markers(uni)
                )
        return result

    def parse_translate_output(
        self,
        input_text: TranslateInput,
        output: str,
        tracker: ParagraphTranslateTracker | None = None,
        llm_translate_tracker: LLMTranslateTracker | None = None,
    ) -> [PdfParagraphComposition]:
        result = []

        # Trace translation I/O to file for diagnosis (Docker truncates logs)
        try:
            with open("/tmp/translation_io.log", "a", encoding="utf-8") as _f:
                _f.write(f"IN={input_text.unicode!r}\nOUT={output!r}\n---\n")
        except Exception:
            pass

        # 如果没有占位符，检查是否有 style_spans（非 LLM 翻译器的样式保留路径）
        if not input_text.placeholders:
            if input_text.style_spans:
                # Non-LLM path: parse marker-wrapped spans from translation output.
                # Markers like 〖B0〗...〖/B0〗 survive DeepLX/Google translation,
                # giving us word-level alignment instead of proportional guesswork.
                return self._parse_style_markers(output, input_text)

            # Strip any stray markers that survived (e.g. from cached translations
            # where style_spans was populated in a previous run but is now empty)
            output = self._strip_style_markers(output)
            comp = PdfParagraphComposition()
            comp.pdf_same_style_unicode_characters = PdfSameStyleUnicodeCharacters()
            comp.pdf_same_style_unicode_characters.unicode = output
            comp.pdf_same_style_unicode_characters.pdf_style = input_text.base_style
            if llm_translate_tracker:
                llm_translate_tracker.set_placeholder_full_match()
            return [comp]

        # 构建正则表达式模式
        patterns = []
        placeholder_patterns = []
        placeholder_map = {}

        for placeholder in input_text.placeholders:
            if isinstance(placeholder, FormulaPlaceholder):
                # 转义特殊字符
                # pattern = re.escape(placeholder.placeholder)
                pattern = placeholder.regex_pattern
                patterns.append(f"({pattern})")
                placeholder_patterns.append(f"({pattern})")
                placeholder_map[placeholder.placeholder] = placeholder
            else:
                left = placeholder.left_regex_pattern
                right = placeholder.right_regex_pattern
                patterns.append(f"({left}.*?{right})")
                placeholder_patterns.append(f"({left})")
                placeholder_patterns.append(f"({right})")
                placeholder_map[placeholder.left_placeholder] = placeholder
        all_match = True
        for pattern in patterns:
            if not re.search(pattern, output, flags=re.IGNORECASE):
                all_match = False
                break
        if all_match:
            if llm_translate_tracker:
                llm_translate_tracker.set_placeholder_full_match()
        else:
            logger.debug(f"Failed to match all placeholder for {input_text.unicode}")
        # 合并所有模式
        combined_pattern = "|".join(patterns)
        combined_placeholder_pattern = "|".join(placeholder_patterns)
        # Build allowed placeholder tokens: originals from source + placeholders we injected.
        allowed_placeholder_tokens: set[str] = set()
        if getattr(input_text, "original_placeholder_tokens", None):
            allowed_placeholder_tokens.update(input_text.original_placeholder_tokens)
        for placeholder in input_text.placeholders:
            if isinstance(placeholder, FormulaPlaceholder):
                allowed_placeholder_tokens.add(placeholder.placeholder)
            else:
                allowed_placeholder_tokens.add(placeholder.left_placeholder)
                allowed_placeholder_tokens.add(placeholder.right_placeholder)

        def remove_placeholder(text: str):
            """Remove placeholder artifacts and hallucinated placeholder-like tokens."""
            # First, remove any leftover placeholders built from our own regex patterns.
            if combined_placeholder_pattern:
                text = re.sub(
                    combined_placeholder_pattern,
                    "",
                    text,
                    flags=re.IGNORECASE,
                )

            # Then, detect placeholder-like tokens of the same shapes as our own
            # formula and rich-text placeholders. Only keep those in the allowed set.
            def _replace_token(match: re.Match) -> str:
                token = match.group(0)
                if token in allowed_placeholder_tokens:
                    return token
                if tracker is not None:
                    tracker.record_removed_hallucinated_placeholder(token)
                return ""

            text = self._formula_placeholder_pattern.sub(_replace_token, text)
            text = self._style_left_placeholder_pattern.sub(_replace_token, text)
            text = self._style_right_placeholder_pattern.sub(_replace_token, text)
            return text

        # 找到所有匹配
        last_end = 0
        for match in re.finditer(combined_pattern, output, flags=re.IGNORECASE):
            # 处理匹配之前的普通文本
            if match.start() > last_end:
                text = output[last_end : match.start()]
                if text:
                    comp = PdfParagraphComposition()
                    comp.pdf_same_style_unicode_characters = (
                        PdfSameStyleUnicodeCharacters()
                    )
                    comp.pdf_same_style_unicode_characters.unicode = remove_placeholder(
                        text,
                    )
                    comp.pdf_same_style_unicode_characters.pdf_style = (
                        input_text.base_style
                    )
                    result.append(comp)

            matched_text = match.group(0)

            # 处理占位符
            if any(
                isinstance(p, FormulaPlaceholder)
                and re.match(f"^{p.regex_pattern}$", matched_text, re.IGNORECASE)
                for p in input_text.placeholders
            ):
                # 处理公式占位符
                placeholder = next(
                    p
                    for p in input_text.placeholders
                    if isinstance(p, FormulaPlaceholder)
                    and re.match(f"^{p.regex_pattern}$", matched_text, re.IGNORECASE)
                )
                comp = PdfParagraphComposition()
                comp.pdf_formula = placeholder.formula
                result.append(comp)
            else:
                # 处理富文本占位符
                placeholder = next(
                    p
                    for p in input_text.placeholders
                    if not isinstance(p, FormulaPlaceholder)
                    and re.match(
                        f"^{p.left_regex_pattern}", matched_text, re.IGNORECASE
                    )
                )
                text = re.match(
                    f"^{placeholder.left_regex_pattern}(.*){placeholder.right_regex_pattern}$",
                    matched_text,
                    re.IGNORECASE,
                ).group(1)

                if isinstance(
                    placeholder.composition,
                    PdfSameStyleCharacters,
                ) and text.replace(" ", "") == "".join(
                    x.char_unicode for x in placeholder.composition.pdf_character
                ).replace(
                    " ",
                    "",
                ):
                    comp = PdfParagraphComposition(
                        pdf_same_style_characters=placeholder.composition,
                    )
                else:
                    comp = PdfParagraphComposition()
                    comp.pdf_same_style_unicode_characters = (
                        PdfSameStyleUnicodeCharacters()
                    )
                    comp.pdf_same_style_unicode_characters.pdf_style = (
                        placeholder.composition.pdf_style
                    )
                    comp.pdf_same_style_unicode_characters.unicode = remove_placeholder(
                        text,
                    )
                result.append(comp)

            last_end = match.end()

        # 处理最后的普通文本
        if last_end < len(output):
            text = output[last_end:]
            if text:
                comp = PdfParagraphComposition()
                comp.pdf_same_style_unicode_characters = PdfSameStyleUnicodeCharacters()
                comp.pdf_same_style_unicode_characters.unicode = remove_placeholder(
                    text,
                )
                comp.pdf_same_style_unicode_characters.pdf_style = input_text.base_style
                result.append(comp)

        # Final safety net: strip any residual markers from ALL compositions.
        # This catches edge cases where placeholders or cache-reuse paths
        # let markers leak into the final text.
        for comp in result:
            if (
                comp.pdf_same_style_unicode_characters
                and comp.pdf_same_style_unicode_characters.unicode
                and ("〖B" in comp.pdf_same_style_unicode_characters.unicode
                     or "〖b" in comp.pdf_same_style_unicode_characters.unicode)
            ):
                comp.pdf_same_style_unicode_characters.unicode = (
                    ILTranslator._strip_style_markers(
                        comp.pdf_same_style_unicode_characters.unicode
                    )
                )

        return result

    def pre_translate_paragraph(
        self,
        paragraph: PdfParagraph,
        tracker: ParagraphTranslateTracker,
        page_font_map: dict[str, PdfFont],
        xobj_font_map: dict[int, dict[str, PdfFont]],
        page: Page | None = None,
    ):
        """Pre-translation processing: prepare text for translation."""
        if paragraph.vertical:
            self.record_skip(page, paragraph, SkipReason.VERTICAL)
            return None, None
        tracker.set_pdf_unicode(paragraph.unicode)
        if paragraph.xobj_id in xobj_font_map:
            page_font_map = xobj_font_map[paragraph.xobj_id]
        disable_rich_text_translate = (
            self.translation_config.disable_rich_text_translate
        )
        if not self.support_llm_translate:
            disable_rich_text_translate = True

        translate_input = self.get_translate_input(
            paragraph, page_font_map, disable_rich_text_translate, page=page
        )
        if not translate_input:
            return None, None
        tracker.set_input(translate_input.unicode)
        tracker.set_placeholders(translate_input.placeholders)
        tracker.set_original_placeholders(
            getattr(translate_input, "original_placeholder_tokens", None),
        )
        text = translate_input.unicode
        if len(text) < self.translation_config.min_text_length:
            logger.debug(
                f"Text too short to translate, skip. Text: {text}. Paragraph id: {paragraph.debug_id}."
            )
            self.record_skip(page, paragraph, SkipReason.TOO_SHORT)
            return None, None
        return text, translate_input

    def post_translate_paragraph(
        self,
        paragraph: PdfParagraph,
        tracker: ParagraphTranslateTracker,
        translate_input,
        translated_text: str,
    ):
        """Post-translation processing: update paragraph with translated text."""
        tracker.set_output(translated_text)
        if translated_text == translate_input:
            if llm_translate_tracker := tracker.last_llm_translate_tracker():
                llm_translate_tracker.set_placeholder_full_match()
            return False
        # Keep {vN} until parse reattaches PdfFormula (OA p5 （,）).
        translated_text = normalize_translated_text(
            translated_text, keep_formula_placeholders=True
        )
        paragraph.pdf_paragraph_composition = self.parse_translate_output(
            translate_input,
            translated_text,
            tracker,
            tracker.last_llm_translate_tracker(),
        )
        # Rebuild unicode from parsed comps (formula glyphs, not leftover {vN}).
        paragraph.unicode = get_paragraph_unicode(paragraph)
        paragraph.unicode = normalize_translated_text(paragraph.unicode)

        # Heading punctuation localization for CJK targets.
        # English headings use "." as separator (e.g. "LESSON 6. Things..."),
        # but Chinese uses "：" (e.g. "第6课：小事……").  Only apply to title
        # paragraphs to avoid affecting body text, version numbers, etc.
        if (
            paragraph.layout_label == "title"
            and self.translation_config.lang_out in ("zh", "zh-CN", "zh-TW", "ja", "ko")
        ):
            paragraph.unicode = self._localize_heading_punctuation(
                paragraph.unicode
            )
        for composition in paragraph.pdf_paragraph_composition:
            ssu = composition.pdf_same_style_unicode_characters
            if ssu is None:
                continue
            if ssu.pdf_style is None:
                ssu.pdf_style = paragraph.pdf_style
            if ssu.unicode:
                ssu.unicode = normalize_translated_text(ssu.unicode)
        return True

    def _build_role_block(self) -> str:
        """Build the role block for LLM prompt.

        Returns:
            Role block string with custom_system_prompt or default role description.
        """
        custom_prompt = getattr(self.translation_config, "custom_system_prompt", None)
        if custom_prompt:
            role_block = custom_prompt.strip()
            if "Follow all rules strictly." not in role_block:
                if not role_block.endswith("\n"):
                    role_block += "\n"
                role_block += "Follow all rules strictly."
        else:
            role_block = (
                f"You are a professional {self.translation_config.lang_out} native translator who needs to fluently translate text "
                f"into {self.translation_config.lang_out}.\n\n"
                "Follow all rules strictly."
            )
        return role_block

    def _build_context_block(
        self,
        title_paragraph: TitleContextSnapshot | None = None,
        local_title_paragraph: TitleContextSnapshot | None = None,
        translate_input: TranslateInput | None = None,
    ) -> str:
        """Build the context/hints block for LLM prompt.

        Args:
            title_paragraph: First title paragraph in the document
            local_title_paragraph: Most recent title paragraph
            translate_input: TranslateInput containing placeholder hints

        Returns:
            Context block string, empty if no context hints available
        """
        context_lines: list[str] = []
        hint_idx = 1

        if title_paragraph:
            context_lines.append(
                f"{hint_idx}. First title in the full text: {title_paragraph.unicode}"
            )
            hint_idx += 1

        if local_title_paragraph:
            is_different_from_global = True
            if title_paragraph:
                if local_title_paragraph.debug_id == title_paragraph.debug_id:
                    is_different_from_global = False

            if is_different_from_global:
                context_lines.append(
                    f"{hint_idx}. The most recent title is: {local_title_paragraph.unicode}"
                )
                hint_idx += 1

        if translate_input and self.translation_config.add_formula_placehold_hint:
            placeholders_hint = translate_input.get_placeholders_hint()
            if placeholders_hint:
                context_lines.append(
                    f"{hint_idx}. Formula placeholder hint:\n{placeholders_hint}"
                )

        if context_lines:
            return "## Context / Hints\n" + "\n".join(context_lines) + "\n"
        return ""

    def _build_glossary_block(self, text: str) -> str:
        """Build the glossary block for LLM prompt.

        Args:
            text: Text to match against glossary entries

        Returns:
            Glossary block string with tables, empty if no active glossary entries
        """
        if not self._cached_glossaries:
            return ""

        glossary_entries_per_glossary: dict[str, list[tuple[str, str]]] = {}

        for glossary in self._cached_glossaries:
            active_entries = glossary.get_active_entries_for_text(text)
            if active_entries:
                glossary_entries_per_glossary[glossary.name] = sorted(active_entries)

        if not glossary_entries_per_glossary:
            return ""

        glossary_block_lines: list[str] = [
            "## Glossary",
            "",
            "Always use the glossary's **Target Term** for any occurrence of its **Source Term** "
            "(including variants, inside tags, or broken across lines).",
            "",
            "Unlisted terms are translated naturally.",
            "",
        ]

        for glossary_name, entries in glossary_entries_per_glossary.items():
            glossary_block_lines.append(f"### Glossary: {glossary_name}")
            glossary_block_lines.append("")
            glossary_block_lines.append(
                "| Source Term | Target Term |\n|-------------|-------------|"
            )
            for original_source, target_text in entries:
                glossary_block_lines.append(f"| {original_source} | {target_text} |")
            glossary_block_lines.append("")

        return "\n".join(glossary_block_lines)

    def generate_prompt_for_llm(
        self,
        text: str,
        title_paragraph: TitleContextSnapshot | None = None,
        local_title_paragraph: TitleContextSnapshot | None = None,
        translate_input: TranslateInput | None = None,
    ):
        """Generate LLM prompt using template-based approach.

        Args:
            text: Text to be translated
            title_paragraph: First title paragraph in the document
            local_title_paragraph: Most recent title paragraph
            translate_input: TranslateInput containing placeholder information

        Returns:
            Final LLM prompt string
        """
        role_block = self._build_role_block()
        context_block = self._build_context_block(
            title_paragraph, local_title_paragraph, translate_input
        )
        glossary_block = self._build_glossary_block(text)

        return PROMPT_TEMPLATE.substitute(
            role_block=role_block,
            glossary_block=glossary_block,
            context_block=context_block,
            lang_out=self.translation_config.lang_out,
            text_to_translate=text,
        )

    def add_content_filter_hint(self, page: Page, paragraph: PdfParagraph):
        with self.add_content_filter_hint_lock:
            new_box = il_version_1.Box(
                x=paragraph.box.x,
                y=paragraph.box.y2,
                x2=paragraph.box.x2,
                y2=paragraph.box.y2 + 1.1,
            )
            page.pdf_paragraph.append(
                self._create_text(
                    "翻译服务检测到内容可能包含不安全或敏感内容，请您避免翻译敏感内容，感谢您的配合。",
                    GRAY80,
                    new_box,
                    1,
                )
            )
            logger.info("success add content filter hint")

    def _create_text(
        self,
        text: str,
        color: GraphicState,
        box: il_version_1.Box,
        font_size: float = 4,
    ):
        style = il_version_1.PdfStyle(
            font_id="base",
            font_size=font_size,
            graphic_state=color,
        )
        return il_version_1.PdfParagraph(
            first_line_indent=0.0,
            box=box,
            vertical=False,
            pdf_style=style,
            unicode=text,
            pdf_paragraph_composition=[
                il_version_1.PdfParagraphComposition(
                    pdf_same_style_unicode_characters=il_version_1.PdfSameStyleUnicodeCharacters(
                        unicode=text,
                        pdf_style=style,
                        debug_info=True,
                    ),
                ),
            ],
            xobj_id=-1,
        )

    def translate_paragraph(
        self,
        paragraph: PdfParagraph,
        page: Page,
        pbar: tqdm | None = None,
        tracker: ParagraphTranslateTracker = None,
        page_font_map: dict[str, PdfFont] = None,
        xobj_font_map: dict[int, dict[str, PdfFont]] = None,
        paragraph_token_count: int = 0,
        title_paragraph: TitleContextSnapshot | None = None,
        local_title_paragraph: TitleContextSnapshot | None = None,
    ):
        """Translate a paragraph using pre and post processing functions."""
        self.translation_config.raise_if_cancelled()
        with PbarContext(pbar):
            try:
                if self.use_as_fallback:
                    # il translator llm only modifies unicode in some situations
                    paragraph.unicode = get_paragraph_unicode(paragraph)
                # Near-full: stash membership only (classified on EN
                # before submit). Do not rematch live host.unicode.
                if id(paragraph) in getattr(self, "_near_full_pullquotes", {}):
                    extra = None
                    if getattr(self.translation_config, "debug", False):
                        extra = side_callout_debug_extra(paragraph, page)
                    self.record_skip(
                        page,
                        paragraph,
                        SkipReason.PULLQUOTE,
                        debug_extra=extra,
                    )
                    logger.debug(
                        "skip side-callout MT: id=%s reason=%s text=%r",
                        paragraph.debug_id,
                        SkipReason.PULLQUOTE.value,
                        (paragraph.unicode or "")[:60],
                    )
                    return
                # Ultra-narrow keep_en: geometry only, no host rematch.
                _callout_mode = getattr(
                    self.translation_config, "narrow_callout_mode", "expand"
                )
                if (
                    is_ultra_narrow_side_callout(paragraph, page)
                    and normalize_narrow_callout_mode(_callout_mode) == "keep_en"
                ):
                    extra = None
                    if getattr(self.translation_config, "debug", False):
                        extra = side_callout_debug_extra(paragraph, page)
                    self.record_skip(
                        page,
                        paragraph,
                        SkipReason.ULTRA_NARROW,
                        debug_extra=extra,
                    )
                    logger.debug(
                        "skip side-callout MT: id=%s reason=%s mode=%s text=%r",
                        paragraph.debug_id,
                        SkipReason.ULTRA_NARROW.value,
                        _callout_mode,
                        (paragraph.unicode or "")[:60],
                    )
                    return
                # Pre-translation processing
                text, translate_input = self.pre_translate_paragraph(
                    paragraph, tracker, page_font_map, xobj_font_map, page=page
                )
                if text is None:
                    return
                # Acceptance V4 gate (source): a paragraph whose MT input
                # repeats the same sentence consecutively is an assembly bug —
                # translate it and the duplicate is magnified in the target.
                # Skip MT (keep source) and surface the warning.
                src_dups = self.find_consecutive_duplicate_sentences(text)
                if any(kind == "exact" for _, kind in src_dups):
                    logger.warning(
                        "Consecutive duplicate sentence in MT input "
                        "(paragraph id=%s, sentence=%r); skipping MT to keep "
                        "source.",
                        paragraph.debug_id,
                        src_dups[0][0][:60],
                    )
                    self.record_skip(page, paragraph, SkipReason.PULLQUOTE)
                    return
                if src_dups:
                    logger.warning(
                        "Near-duplicate consecutive sentences in MT input "
                        "(paragraph id=%s, sentence=%r).",
                        paragraph.debug_id,
                        src_dups[0][0][:60],
                    )
                # Chapter names are titles to translate (not chrome to keep
                # EN). Normalize "Chapter N" -> 第N章 on the MT input so a
                # rich-text-split marker never fuses into "Chapter9直接卷曲".
                text = self.fix_untranslated_chapter_markers(text)
                llm_translate_tracker = tracker.new_llm_translate_tracker()
                # Perform translation
                if self.support_llm_translate:
                    llm_prompt = self.generate_prompt_for_llm(
                        text,
                        title_paragraph,
                        local_title_paragraph,
                        translate_input,
                    )
                    llm_translate_tracker.set_input(llm_prompt)
                    translated_text = self.translate_engine.llm_translate(
                        llm_prompt,
                        rate_limit_params={
                            "paragraph_token_count": paragraph_token_count
                        },
                    )
                    llm_translate_tracker.set_output(translated_text)
                else:
                    # DeepLX/CLI: no LLM glossary table — protect terms with
                    # placeholders, translate, then restore targets.
                    term_maps: list[tuple[str, str]] = []
                    text_for_mt = text
                    for glossary in self._cached_glossaries or []:
                        text_for_mt, part = glossary.protect_terms_for_mt(
                            text_for_mt
                        )
                        term_maps.extend(part)
                    translated_text = self.translate_engine.translate(
                        text_for_mt,
                        rate_limit_params={
                            "paragraph_token_count": paragraph_token_count
                        },
                    )
                    if term_maps:
                        from babeldoc.glossary import Glossary as _Glossary

                        translated_text = _Glossary.restore_protected_terms(
                            translated_text, term_maps
                        )
                translated_text = re.sub(r"[. 。…，]{20,}", ".", translated_text)

                # Completeness: reject dropped sentences (e.g. EN 3 → ZH 2).
                # Retry once without cache — bad cache / flaky MT often recovers.
                if self.translation_drops_sentences(text, translated_text):
                    logger.warning(
                        "Translation drops sentences "
                        f"(src_ends={self.count_sentence_ends(text)}, "
                        f"dst_ends={self.count_sentence_ends(translated_text)}); "
                        f"retry once. paragraph id: {paragraph.debug_id}"
                    )
                    if self.support_llm_translate:
                        llm_prompt = self.generate_prompt_for_llm(
                            text,
                            title_paragraph,
                            local_title_paragraph,
                            translate_input,
                        )
                        translated_text = self.translate_engine.llm_translate(
                            llm_prompt,
                            ignore_cache=True,
                            rate_limit_params={
                                "paragraph_token_count": paragraph_token_count
                            },
                        )
                    else:
                        term_maps_r: list[tuple[str, str]] = []
                        text_retry = text
                        for glossary in self._cached_glossaries or []:
                            text_retry, part = glossary.protect_terms_for_mt(
                                text_retry
                            )
                            term_maps_r.extend(part)
                        translated_text = self.translate_engine.translate(
                            text_retry,
                            ignore_cache=True,
                            rate_limit_params={
                                "paragraph_token_count": paragraph_token_count
                            },
                        )
                        if term_maps_r:
                            from babeldoc.glossary import Glossary as _Glossary

                            translated_text = _Glossary.restore_protected_terms(
                                translated_text, term_maps_r
                            )
                    translated_text = re.sub(
                        r"[. 。…，]{20,}", ".", translated_text
                    )
                    if self.translation_drops_sentences(text, translated_text):
                        logger.warning(
                            "Translation still drops sentences after retry; "
                            f"keeping result. paragraph id: {paragraph.debug_id} "
                            f"output={translated_text[:80]!r}"
                        )

                # Chapter running titles: "Chapter N" and DeepLX-mangled
                # 章b08 residue on every MT output (not only the retry path).
                if self._CJK_CHAR_RE.search(translated_text):
                    translated_text = self.fix_untranslated_chapter_markers(
                        translated_text
                    )

                # Acceptance V4 gate (output): if MT/LLM duplicated a sentence
                # back-to-back in the target, fall back to the source so a
                # "same-sentence xN wall" is never shipped.
                out_dups = self.find_consecutive_duplicate_sentences(translated_text)
                if any(kind == "exact" for _, kind in out_dups):
                    logger.warning(
                        "Translation repeats a sentence consecutively "
                        "(paragraph id=%s, sentence=%r); falling back to "
                        "source text.",
                        paragraph.debug_id,
                        out_dups[0][0][:60],
                    )
                    translated_text = text
                elif out_dups:
                    logger.warning(
                        "Translation has near-duplicate consecutive sentences "
                        "(paragraph id=%s, sentence=%r).",
                        paragraph.debug_id,
                        out_dups[0][0][:60],
                    )

                # Post-translation processing
                self.post_translate_paragraph(
                    paragraph, tracker, translate_input, translated_text
                )
            except ContentFilterError as e:
                logger.warning(f"ContentFilterError: {e.message}")
                self.add_content_filter_hint(page, paragraph)
                return
            except Exception as e:
                logger.exception(
                    f"Error translating paragraph. Paragraph: {paragraph.debug_id} ({paragraph.unicode}). Error: {e}. ",
                )
                # ignore error and continue
                return
