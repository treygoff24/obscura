"""PDF redaction engine — stateless, path-agnostic.

Uses page.search_for() per keyword directly to get bounding rectangles,
rather than extract->match->re-search. This avoids fragility from divergent
text extraction paths and ensures accurate rectangle placement.

Tracks "redaction coverage" — keywords where no rectangle was found on
a page are recorded as warnings in the result.
"""

from __future__ import annotations

import dataclasses
import hashlib
import logging
import pathlib
import tempfile

import fitz

from obscura.keywords import KeywordSet, _normalize

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class RedactionResult:
    """Structured result from a single PDF redaction run."""

    file: str
    status: str  # "ok", "password_protected", "corrupt"
    source_hash: str
    redaction_count: int
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


def _search_keywords_on_page(
    page: fitz.Page, keywords: KeywordSet
) -> tuple[list[tuple[str, fitz.Rect]], list[dict]]:
    """Search for all keywords on a page using page.search_for() directly.

    Returns:
        Tuple of (hits, misses) where hits are (keyword, rect) pairs
        and misses are keywords that matched text but got no rectangle.
    """
    hits: list[tuple[str, fitz.Rect]] = []
    misses: list[dict] = []

    for kw in keywords.plain_keywords:
        rects = page.search_for(kw)
        if rects:
            for rect in rects:
                hits.append((kw, rect))
        else:
            text = _normalize(page.get_text()).lower()
            if kw in text:
                misses.append({"keyword": kw, "page": page.number + 1})

    for prefix in keywords.prefix_keywords:
        rects = page.search_for(prefix)
        for rect in rects:
            hits.append((f"{prefix}*", rect))

    text = _normalize(page.get_text())
    for pattern_str, compiled in keywords.regex_patterns:
        import regex
        for m in compiled.finditer(text, timeout=5):
            rects = page.search_for(m.group())
            if rects:
                for rect in rects:
                    hits.append((f"regex:{pattern_str}", rect))
            else:
                misses.append({
                    "keyword": f"regex:{pattern_str}",
                    "page": page.number + 1,
                })

    return hits, misses


def redact_pdf(
    input_path: pathlib.Path,
    output_path: pathlib.Path,
    keywords: KeywordSet,
    language: str = "eng",
) -> RedactionResult:
    """Redact keywords from a PDF file.

    Uses page.search_for() per keyword to get accurate bounding rectangles
    directly from PyMuPDF, avoiding fragile extract->match->re-search patterns.

    Args:
        input_path: Path to the source PDF.
        output_path: Path to write the redacted PDF.
        keywords: A KeywordSet defining what to redact.
        language: Tesseract language code for OCR.

    Returns:
        RedactionResult with status and redaction details.
    """
    source_hash = _file_hash(input_path)

    try:
        doc = fitz.open(str(input_path))
    except Exception:
        return RedactionResult(
            file=input_path.name,
            status="corrupt",
            source_hash=source_hash,
            redaction_count=0,
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

        if not text.strip():
            try:
                page.get_textpage_ocr(language=language, full=True)
                text = page.get_text()
                if text.strip():
                    ocr_used = True
            except Exception:
                logger.warning("OCR failed on page %d of %s", page_num + 1, input_path.name)
                continue

        hits, misses = _search_keywords_on_page(page, keywords)
        all_missed.extend(misses)

        if not hits:
            continue

        for keyword, rect in hits:
            page.add_redact_annot(rect, fill=(0, 0, 0))

        page.apply_redactions()
        total_redactions += len(hits)
        pages_with_redactions.append(page_num + 1)

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
        page_count=page_count,
        ocr_used=ocr_used,
        pages_with_redactions=pages_with_redactions,
        missed_keywords=all_missed,
    )