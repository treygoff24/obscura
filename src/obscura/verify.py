"""Verification layer — residual scan, OCR confidence, image-only detection."""

from __future__ import annotations

import dataclasses
import hashlib
import pathlib
from datetime import datetime, timezone

import fitz

import obscura
from obscura.keywords import KeywordSet
from obscura.runtime import configure_ocr_runtime, parse_tesseract_languages


@dataclasses.dataclass
class VerificationReport:
    """Per-file verification report."""

    file: str
    status: str  # "clean", "needs_review", "unreadable"
    source_hash: str
    output_hash: str
    residual_matches: list[dict]
    low_confidence_pages: list[int]
    unreadable_pages: list[int]
    clean_pages: list[int]
    deep_verify: bool
    deep_verify_dpi: int | None
    engine_version: str
    keywords_hash: str
    language: str
    confidence_threshold: int
    timestamp: str

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        if self.unreadable_pages:
            pages_str = ", ".join(str(p) for p in self.unreadable_pages)
            d["unverified_warning"] = (
                f"Pages {pages_str} were not OCR-readable and could not be verified."
            )
        return d


def _file_hash(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _check_ocr_confidence(
    page: fitz.Page,
    textpage: fitz.TextPage,
    page_number: int,
    threshold: int,
    low_confidence_pages: list[int],
) -> None:
    """Check per-word OCR confidence and flag low-confidence pages."""
    try:
        words = page.get_text("words", textpage=textpage)
        if not words:
            return
        confidences = [float(w[8]) if len(w) > 8 else 100.0 for w in words]
        avg_confidence = sum(confidences) / len(confidences)
        if avg_confidence < threshold:
            low_confidence_pages.append(page_number)
    except Exception:
        pass


def verify_pdf(
    pdf_path: pathlib.Path,
    keywords: KeywordSet,
    confidence_threshold: int = 70,
    language: str = "eng",
    deep_verify: bool = False,
    deep_verify_dpi: int = 300,
    verbose: bool = False,
    source_hash: str | None = None,
) -> VerificationReport:
    """Run verification checks on a PDF.

    Args:
        pdf_path: Path to the PDF to verify.
        keywords: KeywordSet to check for residual matches.
        confidence_threshold: OCR confidence cutoff (0-100).
        language: Tesseract language code.
        deep_verify: If True, rasterize and re-scan pages.
        deep_verify_dpi: DPI for rasterization (150-600).
        verbose: If True, include context snippets in report.

    Returns:
        VerificationReport with findings.
    """
    configure_ocr_runtime(parse_tesseract_languages(language))

    if source_hash is None:
        source_hash = _file_hash(pdf_path)
    output_hash = _file_hash(pdf_path)
    doc = fitz.open(str(pdf_path))

    residual_matches: list[dict] = []
    low_confidence_pages: list[int] = []
    unreadable_pages: list[int] = []
    clean_pages: list[int] = []

    for page_num in range(doc.page_count):
        page = doc[page_num]
        page_number = page_num + 1
        text = page.get_text()

        if not text.strip():
            has_images = len(page.get_images()) > 0
            if has_images:
                try:
                    tp = page.get_textpage_ocr(language=language, full=True)
                except Exception:
                    unreadable_pages.append(page_number)
                    continue
                if tp is None:
                    unreadable_pages.append(page_number)
                    continue
                text = page.get_text(textpage=tp)
                if text.strip():
                    _check_ocr_confidence(
                        page, tp, page_number, confidence_threshold,
                        low_confidence_pages,
                    )
                else:
                    unreadable_pages.append(page_number)
                    continue
            else:
                unreadable_pages.append(page_number)
                continue

        matches = keywords.find_matches(text)
        if matches:
            for m in matches:
                entry: dict = {"keyword": m.keyword, "page": page_number}
                if verbose:
                    entry["context"] = m.matched_text
                residual_matches.append(entry)
        else:
            clean_pages.append(page_number)

    if deep_verify:
        for page_num in range(doc.page_count):
            page = doc[page_num]
            page_number = page_num + 1
            pix = page.get_pixmap(dpi=deep_verify_dpi)
            img_doc = fitz.open()
            img_page = img_doc.new_page(width=pix.width, height=pix.height)
            img_page.insert_image(img_page.rect, pixmap=pix)
            try:
                dv_tp = img_page.get_textpage_ocr(language=language, full=True)
            except Exception:
                img_doc.close()
                continue
            if dv_tp is None:
                img_doc.close()
                continue
            ocr_text = img_page.get_text()
            dv_matches = keywords.find_matches(ocr_text)
            for m in dv_matches:
                entry = {
                    "keyword": m.keyword,
                    "page": page_number,
                    "source": "deep_verify",
                }
                if entry not in residual_matches:
                    residual_matches.append(entry)
            img_doc.close()

    doc.close()

    if unreadable_pages:
        status = "unreadable"
    elif residual_matches or low_confidence_pages:
        status = "needs_review"
    else:
        status = "clean"

    return VerificationReport(
        file=pdf_path.name,
        status=status,
        source_hash=source_hash,
        output_hash=output_hash,
        residual_matches=residual_matches,
        low_confidence_pages=low_confidence_pages,
        unreadable_pages=unreadable_pages,
        clean_pages=clean_pages,
        deep_verify=deep_verify,
        deep_verify_dpi=deep_verify_dpi if deep_verify else None,
        engine_version=obscura.__version__,
        keywords_hash=keywords.keyword_hash(),
        language=language,
        confidence_threshold=confidence_threshold,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
