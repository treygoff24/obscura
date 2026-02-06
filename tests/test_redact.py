"""Tests for PDF redaction engine."""

import pathlib
import shutil

import fitz
import pytest

from obscura.keywords import KeywordSet
from obscura.redact import (
    RedactionResult,
    _ocr_redact_pass,
    _search_keywords_on_page,
    redact_pdf,
)


def _create_pdf(path: pathlib.Path, pages: list[str]) -> pathlib.Path:
    """Create a simple PDF with text on each page."""
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=12)
    doc.save(str(path))
    doc.close()
    return path


def _make_keywords(tmp_dir: pathlib.Path, lines: list[str]) -> KeywordSet:
    kw_file = tmp_dir / "keywords.txt"
    kw_file.write_text("\n".join(lines) + "\n")
    return KeywordSet.from_file(kw_file)


class TestRedactPdf:
    def test_redacts_keyword_from_text(self, tmp_dir):
        input_path = _create_pdf(
            tmp_dir / "input.pdf",
            ["This document is confidential and private."],
        )
        output_path = tmp_dir / "output.pdf"
        keywords = _make_keywords(tmp_dir, ["confidential"])

        result = redact_pdf(input_path, output_path, keywords)

        assert result.redaction_count > 0
        assert output_path.exists()

        doc = fitz.open(str(output_path))
        text = doc[0].get_text()
        doc.close()
        assert "confidential" not in text.lower()

    def test_case_insensitive_redaction(self, tmp_dir):
        input_path = _create_pdf(
            tmp_dir / "input.pdf",
            ["This document is CONFIDENTIAL."],
        )
        output_path = tmp_dir / "output.pdf"
        keywords = _make_keywords(tmp_dir, ["confidential"])

        redact_pdf(input_path, output_path, keywords)

        doc = fitz.open(str(output_path))
        text = doc[0].get_text()
        doc.close()
        assert "confidential" not in text.lower()

    def test_prefix_redacts_full_token(self, tmp_dir):
        input_path = _create_pdf(
            tmp_dir / "input.pdf",
            ["The investor-relations team met today."],
        )
        output_path = tmp_dir / "output.pdf"
        keywords = _make_keywords(tmp_dir, ["investor*"])

        redact_pdf(input_path, output_path, keywords)

        doc = fitz.open(str(output_path))
        text = doc[0].get_text().lower()
        doc.close()
        assert "investor" not in text
        assert "relations" not in text

    def test_text_removed_from_content_stream(self, tmp_dir):
        """Regression: verify apply_redactions removes text, not just overlays."""
        input_path = _create_pdf(
            tmp_dir / "input.pdf",
            ["The secret password is hunter2."],
        )
        output_path = tmp_dir / "output.pdf"
        keywords = _make_keywords(tmp_dir, ["hunter2"])

        redact_pdf(input_path, output_path, keywords)

        doc = fitz.open(str(output_path))
        all_text = ""
        for page in doc:
            all_text += page.get_text()
            blocks = page.get_text("rawdict")["blocks"]
            for block in blocks:
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            assert "hunter2" not in span.get("text", "").lower()
        doc.close()
        assert "hunter2" not in all_text.lower()

    def test_returns_structured_result(self, tmp_dir):
        input_path = _create_pdf(
            tmp_dir / "input.pdf",
            ["Secret document with secret data."],
        )
        output_path = tmp_dir / "output.pdf"
        keywords = _make_keywords(tmp_dir, ["secret"])

        result = redact_pdf(input_path, output_path, keywords)

        assert isinstance(result, RedactionResult)
        assert result.redaction_count >= 2
        assert result.page_count == 1
        assert result.status == "ok"

    def test_multi_page_redaction(self, tmp_dir):
        input_path = _create_pdf(
            tmp_dir / "input.pdf",
            [
                "Page one has confidential info.",
                "Page two has secret data.",
                "Page three is clean.",
            ],
        )
        output_path = tmp_dir / "output.pdf"
        keywords = _make_keywords(tmp_dir, ["confidential", "secret"])

        result = redact_pdf(input_path, output_path, keywords)

        assert result.redaction_count >= 2
        assert result.page_count == 3

    def test_no_matches_still_produces_output(self, tmp_dir):
        input_path = _create_pdf(
            tmp_dir / "input.pdf",
            ["This is a clean document."],
        )
        output_path = tmp_dir / "output.pdf"
        keywords = _make_keywords(tmp_dir, ["nonexistent"])

        result = redact_pdf(input_path, output_path, keywords)

        assert result.redaction_count == 0
        assert output_path.exists()

    def test_atomic_write(self, tmp_dir):
        """Output should not exist as a partial file if something goes wrong."""
        input_path = _create_pdf(tmp_dir / "input.pdf", ["Test content."])
        output_path = tmp_dir / "output.pdf"
        keywords = _make_keywords(tmp_dir, ["test"])

        redact_pdf(input_path, output_path, keywords)

        assert output_path.exists()
        doc = fitz.open(str(output_path))
        assert doc.page_count == 1
        doc.close()

    def test_password_protected_pdf(self, tmp_dir):
        input_path = tmp_dir / "protected.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Secret text")
        perm = fitz.PDF_PERM_ACCESSIBILITY
        encrypt_meth = fitz.PDF_ENCRYPT_AES_256
        doc.save(
            str(input_path),
            encryption=encrypt_meth,
            owner_pw="owner",
            user_pw="user",
            permissions=perm,
        )
        doc.close()

        output_path = tmp_dir / "output.pdf"
        keywords = _make_keywords(tmp_dir, ["secret"])

        result = redact_pdf(input_path, output_path, keywords)

        assert result.status == "password_protected"
        assert not output_path.exists()

    def test_corrupt_pdf(self, tmp_dir):
        input_path = tmp_dir / "corrupt.pdf"
        input_path.write_bytes(b"this is not a pdf")
        output_path = tmp_dir / "output.pdf"
        keywords = _make_keywords(tmp_dir, ["secret"])

        result = redact_pdf(input_path, output_path, keywords)

        assert result.status == "corrupt"
        assert not output_path.exists()

    def test_source_hash_in_result(self, tmp_dir):
        input_path = _create_pdf(tmp_dir / "input.pdf", ["Content."])
        output_path = tmp_dir / "output.pdf"
        keywords = _make_keywords(tmp_dir, ["content"])

        result = redact_pdf(input_path, output_path, keywords)

        assert result.source_hash.startswith("sha256:")
        assert len(result.source_hash) == 71  # "sha256:" + 64 hex chars

    def test_ocr_text_extraction_exception_skips_page(self, tmp_dir, monkeypatch):
        """Regression: OCR extraction failures should not abort the full file."""
        input_path = _create_pdf(tmp_dir / "input.pdf", [""])
        output_path = tmp_dir / "output.pdf"
        keywords = _make_keywords(tmp_dir, ["secret"])

        original_get_text = fitz.Page.get_text

        def fake_get_text(self, *args, **kwargs):
            if kwargs.get("textpage") is not None:
                raise RuntimeError("synthetic get_text failure")
            return original_get_text(self, *args, **kwargs)

        monkeypatch.setattr(fitz.Page, "get_textpage_ocr", lambda *_a, **_k: object())
        monkeypatch.setattr(fitz.Page, "get_text", fake_get_text)

        result = redact_pdf(input_path, output_path, keywords)

        assert result.status == "ok"
        assert result.redaction_count == 0
        assert output_path.exists()

    def test_ocr_returns_none_skips_page(self, tmp_dir, monkeypatch):
        """When get_textpage_ocr returns None, the page should be skipped."""
        input_path = _create_pdf(tmp_dir / "input.pdf", [""])
        output_path = tmp_dir / "output.pdf"
        keywords = _make_keywords(tmp_dir, ["secret"])

        monkeypatch.setattr(fitz.Page, "get_textpage_ocr", lambda *_a, **_k: None)

        result = redact_pdf(input_path, output_path, keywords)

        assert result.status == "ok"
        assert result.redaction_count == 0
        assert result.ocr_used is False
        assert output_path.exists()

    def test_ocr_initialization_exception_skips_page(self, tmp_dir, monkeypatch):
        """When get_textpage_ocr raises, the page should be skipped."""
        input_path = _create_pdf(tmp_dir / "input.pdf", [""])
        output_path = tmp_dir / "output.pdf"
        keywords = _make_keywords(tmp_dir, ["secret"])

        def raise_on_ocr(*_a, **_k):
            raise RuntimeError("Tesseract not found")

        monkeypatch.setattr(fitz.Page, "get_textpage_ocr", raise_on_ocr)

        result = redact_pdf(input_path, output_path, keywords)

        assert result.status == "ok"
        assert result.redaction_count == 0
        assert output_path.exists()


class TestOcrRedactPass:
    @pytest.mark.skipif(
        not shutil.which("tesseract"), reason="Tesseract not installed"
    )
    def test_ocr_redact_pass_catches_image_text(self, tmp_dir):
        src_doc = fitz.open()
        src_page = src_doc.new_page()
        src_page.insert_text((72, 72), "CONFIDENTIAL DOCUMENT", fontsize=24)
        pix = src_page.get_pixmap(dpi=150)
        src_doc.close()

        doc = fitz.open()
        page = doc.new_page()
        page.insert_image(page.rect, pixmap=pix)

        assert not page.get_text().strip()

        keywords = _make_keywords(tmp_dir, ["confidential"])
        count, misses = _ocr_redact_pass(page, keywords, "eng")
        doc.close()

        assert count > 0

    @pytest.mark.skipif(
        not shutil.which("tesseract"), reason="Tesseract not installed"
    )
    def test_ocr_redact_pass_no_double_count(self, tmp_dir):
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "CONFIDENTIAL data here", fontsize=12)

        keywords = _make_keywords(tmp_dir, ["confidential"])

        hits, _ = _search_keywords_on_page(page, keywords)
        for _, rect in hits:
            page.add_redact_annot(rect, fill=(0, 0, 0))
        page.apply_redactions()

        ocr_count, _ = _ocr_redact_pass(page, keywords, "eng")
        doc.close()

        assert ocr_count == 0

    def test_ocr_redact_pass_rasterization_failure(self, tmp_dir, monkeypatch):
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "CONFIDENTIAL", fontsize=12)

        def raise_error(*args, **kwargs):
            raise RuntimeError("rasterization failed")

        monkeypatch.setattr(fitz.Page, "get_pixmap", raise_error)

        keywords = _make_keywords(tmp_dir, ["confidential"])
        count, misses = _ocr_redact_pass(page, keywords, "eng")
        doc.close()

        assert count == 0
        assert misses == []

    def test_ocr_redact_pass_ocr_init_failure(self, tmp_dir, monkeypatch):
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "CONFIDENTIAL", fontsize=12)

        def raise_on_ocr(*args, **kwargs):
            raise RuntimeError("Tesseract not found")

        monkeypatch.setattr(fitz.Page, "get_textpage_ocr", raise_on_ocr)

        keywords = _make_keywords(tmp_dir, ["confidential"])
        count, misses = _ocr_redact_pass(page, keywords, "eng")
        doc.close()

        assert count == 0
        assert misses == []

    def test_redact_pdf_includes_ocr_count(self, tmp_dir):
        input_path = _create_pdf(tmp_dir / "input.pdf", ["Some text here."])
        output_path = tmp_dir / "output.pdf"
        keywords = _make_keywords(tmp_dir, ["nonexistent"])

        result = redact_pdf(input_path, output_path, keywords)

        assert hasattr(result, "ocr_redaction_count")
        assert result.ocr_redaction_count >= 0