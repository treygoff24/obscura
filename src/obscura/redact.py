"""PDF redaction engine — stateless, path-agnostic.

Uses word-level text extraction to map keyword matches to rectangles
directly, avoiding fragile extract->match->re-search flows and ensuring
case-insensitive, whole-word redaction for plain and prefix keywords.

Tracks "redaction coverage" — keywords where a match was found but no
rectangle could be mapped are recorded as warnings in the result.
"""

from __future__ import annotations

import dataclasses
import hashlib
import logging
import pathlib
import tempfile
import unicodedata

import fitz
import regex

from obscura.keywords import KeywordSet, _normalize
from obscura.runtime import configure_ocr_runtime, parse_tesseract_languages

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class _WordSpan:
    rect: fitz.Rect
    start: int
    end: int


@dataclasses.dataclass(frozen=True)
class _LineWords:
    text: str
    words: list[_WordSpan]


@dataclasses.dataclass
class RedactionResult:
    """Structured result from a single PDF redaction run."""

    file: str
    status: str  # "ok", "password_protected", "corrupt"
    source_hash: str
    redaction_count: int
    ocr_redaction_count: int
    page_count: int
    ocr_used: bool
    pages_with_redactions: list[int]
    missed_keywords: list[dict]  # [{"keyword": str, "page": int}]

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def _file_hash(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


_TOKEN_JOINER_PUNCT = frozenset({
    "'",
    "’",
    "-",
    "_",
    ".",
    ",",
    "@",
    "+",
    "&",
    "/",
    "\\",
})
_KNOWN_FUSED_SEPARATORS = frozenset({"¶"})


def _should_split_token_char(ch: str) -> bool:
    """Return True when a character should split a PDF-extracted token.

    We split known "fusing" characters (e.g., superscript digits) that can
    normalize into word characters and break \\b boundaries, while preserving
    punctuation commonly used inside real keywords (emails, hyphenated names).
    """
    if ch in _TOKEN_JOINER_PUNCT:
        return False
    if ch in _KNOWN_FUSED_SEPARATORS:
        return True

    category = unicodedata.category(ch)
    if category in {"No", "Nl", "Sk", "Sc"}:
        return True
    if category.startswith("Z") or category.startswith("C"):
        return True
    return False


def _split_fused_token(text: str) -> list[str]:
    """Split a PDF-extracted token on likely Unicode fusion separators."""
    if not text:
        return []

    parts: list[str] = []
    buffer: list[str] = []
    for ch in text:
        if _should_split_token_char(ch):
            if buffer:
                parts.append("".join(buffer))
                buffer.clear()
        else:
            buffer.append(ch)
    if buffer:
        parts.append("".join(buffer))
    return parts


def _extract_line_words(
    page: fitz.Page, textpage: fitz.TextPage | None = None
) -> list[_LineWords]:
    """Extract normalized words grouped by line for reliable matching."""
    words = page.get_text("words", textpage=textpage) or []
    if not words:
        return []

    words.sort(key=lambda w: (w[5], w[6], w[7]))
    grouped: dict[tuple[int, int], list[tuple[str, fitz.Rect]]] = {}
    for w in words:
        raw_text = str(w[4])
        rect = fitz.Rect(w[:4])
        key = (int(w[5]), int(w[6]))
        parts = _split_fused_token(raw_text)
        for part in parts:
            norm = _normalize(part).lower()
            if norm:
                grouped.setdefault(key, []).append((norm, rect))

    lines: list[_LineWords] = []
    for key in sorted(grouped.keys()):
        entries = grouped[key]
        line_text = ""
        spans: list[_WordSpan] = []
        for idx, (text, rect) in enumerate(entries):
            if idx > 0:
                line_text += " "
            start = len(line_text)
            line_text += text
            end = len(line_text)
            spans.append(_WordSpan(rect=rect, start=start, end=end))
        lines.append(_LineWords(text=line_text, words=spans))

    return lines


def _rects_for_match(words: list[_WordSpan], start: int, end: int) -> list[fitz.Rect]:
    rects: list[fitz.Rect] = []
    for w in words:
        if w.start < end and w.end > start:
            rects.append(w.rect)
    return rects


def _search_keywords_on_page(
    page: fitz.Page,
    keywords: KeywordSet,
    textpage: fitz.TextPage | None = None,
) -> tuple[list[tuple[str, fitz.Rect]], list[dict]]:
    """Search for all keywords on a page using word-level extraction.

    Returns:
        Tuple of (hits, misses) where hits are (keyword, rect) pairs
        and misses are keywords that matched text but got no rectangle.
    """

    hits: list[tuple[str, fitz.Rect]] = []
    misses: list[dict] = []
    seen: set[tuple[str, float, float, float, float]] = set()

    lines = _extract_line_words(page, textpage=textpage)
    if not lines:
        return hits, misses

    plain_patterns = [
        (kw, regex.compile(r"\b" + regex.escape(kw) + r"\b", regex.IGNORECASE))
        for kw in keywords.plain_keywords
    ]
    prefix_patterns = [
        (prefix, regex.compile(r"\b" + regex.escape(prefix) + r"[\w-]*", regex.IGNORECASE))
        for prefix in keywords.prefix_keywords
    ]

    def add_rects(label: str, rects: list[fitz.Rect]) -> None:
        for rect in rects:
            key = (label, rect.x0, rect.y0, rect.x1, rect.y1)
            if key in seen:
                continue
            seen.add(key)
            hits.append((label, rect))

    for line in lines:
        for kw, pattern in plain_patterns:
            for m in pattern.finditer(line.text, timeout=5):
                rects = _rects_for_match(line.words, m.start(), m.end())
                if rects:
                    add_rects(kw, rects)
                else:
                    misses.append({"keyword": kw, "page": page.number + 1})

        for prefix, pattern in prefix_patterns:
            for m in pattern.finditer(line.text, timeout=5):
                rects = _rects_for_match(line.words, m.start(), m.end())
                if rects:
                    add_rects(f"{prefix}*", rects)
                else:
                    misses.append({"keyword": f"{prefix}*", "page": page.number + 1})

        for pattern_str, compiled in keywords.regex_patterns:
            for m in compiled.finditer(line.text, timeout=5):
                rects = _rects_for_match(line.words, m.start(), m.end())
                if rects:
                    add_rects(f"regex:{pattern_str}", rects)
                else:
                    misses.append({
                        "keyword": f"regex:{pattern_str}",
                        "page": page.number + 1,
                    })

    return hits, misses


def _ocr_redact_pass(
    page: fitz.Page,
    keywords: KeywordSet,
    language: str,
    dpi: int = 150,
) -> tuple[int, list[dict]]:
    """OCR second pass: rasterize page, OCR it, redact any remaining keyword matches."""
    try:
        pix = page.get_pixmap(dpi=dpi)
    except Exception:
        logger.warning("OCR redaction: rasterization failed on page %d", page.number + 1)
        return 0, []

    img_doc = fitz.open()
    try:
        img_page = img_doc.new_page(width=pix.width, height=pix.height)
        img_page.insert_image(img_page.rect, pixmap=pix)

        try:
            tp = img_page.get_textpage_ocr(language=language, full=True)
        except Exception:
            logger.warning("OCR redaction: OCR init failed on page %d", page.number + 1)
            return 0, []
        if tp is None:
            return 0, []

        try:
            hits, misses = _search_keywords_on_page(img_page, keywords, textpage=tp)
        except Exception:
            logger.warning("OCR redaction: keyword search failed on page %d", page.number + 1)
            return 0, []
        if not hits:
            return 0, misses

        sx = page.rect.width / pix.width
        sy = page.rect.height / pix.height

        for _keyword, rect in hits:
            scaled = fitz.Rect(
                rect.x0 * sx, rect.y0 * sy,
                rect.x1 * sx, rect.y1 * sy,
            )
            expanded = scaled + (-2, -2, 2, 2)
            page.add_redact_annot(expanded, fill=(0, 0, 0))

        page.apply_redactions(graphics=2)
        return len(hits), misses
    finally:
        img_doc.close()


def redact_pdf(
    input_path: pathlib.Path,
    output_path: pathlib.Path,
    keywords: KeywordSet,
    language: str = "eng",
) -> RedactionResult:
    """Redact keywords from a PDF file.

    Uses word-level text extraction with regex matching to map keywords
    to bounding rectangles for case-insensitive, whole-word redaction.

    Args:
        input_path: Path to the source PDF.
        output_path: Path to write the redacted PDF.
        keywords: A KeywordSet defining what to redact.
        language: Tesseract language code for OCR.

    Returns:
        RedactionResult with status and redaction details.
    """
    configure_ocr_runtime(parse_tesseract_languages(language))
    source_hash = _file_hash(input_path)

    try:
        doc = fitz.open(str(input_path))
    except Exception:
        return RedactionResult(
            file=input_path.name,
            status="corrupt",
            source_hash=source_hash,
            redaction_count=0,
            ocr_redaction_count=0,
            page_count=0,
            ocr_used=False,
            pages_with_redactions=[],
            missed_keywords=[],
        )

    if doc.is_encrypted:
        doc.close()
        return RedactionResult(
            file=input_path.name,
            status="password_protected",
            source_hash=source_hash,
            redaction_count=0,
            ocr_redaction_count=0,
            page_count=0,
            ocr_used=False,
            pages_with_redactions=[],
            missed_keywords=[],
        )

    total_redactions = 0
    pages_with_redactions: list[int] = []
    all_missed: list[dict] = []
    ocr_used = False

    for page_num in range(doc.page_count):
        page = doc[page_num]
        text = page.get_text()

        textpage = None
        if not text.strip():
            try:
                textpage = page.get_textpage_ocr(language=language, full=True)
            except Exception:
                logger.warning("OCR initialization failed on page %d of %s", page_num + 1, input_path.name)
                continue
            if textpage is None:
                logger.warning("OCR returned None on page %d of %s", page_num + 1, input_path.name)
                continue
            try:
                text = page.get_text(textpage=textpage)
                if text.strip():
                    ocr_used = True
            except Exception:
                logger.warning("OCR text extraction failed on page %d of %s", page_num + 1, input_path.name)
                continue

        hits, misses = _search_keywords_on_page(page, keywords, textpage=textpage)
        all_missed.extend(misses)

        if not hits:
            continue

        for keyword, rect in hits:
            page.add_redact_annot(rect, fill=(0, 0, 0))

        page.apply_redactions()
        total_redactions += len(hits)
        pages_with_redactions.append(page_num + 1)

    # Second pass: OCR-based redaction for vector text, image text, etc.
    ocr_redaction_count = 0
    for page_num in range(doc.page_count):
        page = doc[page_num]
        ocr_count, ocr_misses = _ocr_redact_pass(page, keywords, language)
        if ocr_count > 0:
            ocr_redaction_count += ocr_count
            if page_num + 1 not in pages_with_redactions:
                pages_with_redactions.append(page_num + 1)
            ocr_used = True
        all_missed.extend(ocr_misses)

    if all_missed:
        logger.warning(
            "Redaction coverage gaps in %s: %d keyword instances had no rectangle",
            input_path.name, len(all_missed),
        )

    page_count = doc.page_count
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=output_path.parent, suffix=".pdf.tmp"
    )
    try:
        import os
        os.close(tmp_fd)
        doc.save(tmp_path)
        doc.close()
        pathlib.Path(tmp_path).replace(output_path)
    except Exception:
        doc.close()
        pathlib.Path(tmp_path).unlink(missing_ok=True)
        raise

    return RedactionResult(
        file=input_path.name,
        status="ok",
        source_hash=source_hash,
        redaction_count=total_redactions,
        ocr_redaction_count=ocr_redaction_count,
        page_count=page_count,
        ocr_used=ocr_used,
        pages_with_redactions=pages_with_redactions,
        missed_keywords=all_missed,
    )
