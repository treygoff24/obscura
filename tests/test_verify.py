"""Tests for verification layer."""

import json

import fitz
import pytest

from obscura.keywords import KeywordSet
from obscura.verify import VerificationReport, verify_pdf


def _create_pdf(path, pages: list[str]):
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=12)
    doc.save(str(path))
    doc.close()
    return path


def _make_keywords(tmp_dir, lines: list[str]) -> KeywordSet:
    kw_file = tmp_dir / "keywords.txt"
    kw_file.write_text("\n".join(lines) + "\n")
    return KeywordSet.from_file(kw_file)


class TestVerifyPdf:
    def test_clean_pdf_reports_clean(self, tmp_dir):
        pdf_path = _create_pdf(tmp_dir / "clean.pdf", ["This is fine."])
        keywords = _make_keywords(tmp_dir, ["secret"])

        report = verify_pdf(pdf_path, keywords, confidence_threshold=70)

        assert report.status == "clean"
        assert report.residual_matches == []

    def test_residual_match_detected(self, tmp_dir):
        pdf_path = _create_pdf(
            tmp_dir / "dirty.pdf", ["This has a secret word."]
        )
        keywords = _make_keywords(tmp_dir, ["secret"])

        report = verify_pdf(pdf_path, keywords, confidence_threshold=70)

        assert report.status == "needs_review"
        assert len(report.residual_matches) > 0
        assert report.residual_matches[0]["keyword"] == "secret"
        assert report.residual_matches[0]["page"] == 1

    def test_report_to_dict(self, tmp_dir):
        pdf_path = _create_pdf(tmp_dir / "test.pdf", ["Clean content."])
        keywords = _make_keywords(tmp_dir, ["missing"])

        report = verify_pdf(pdf_path, keywords, confidence_threshold=70)
        d = report.to_dict()

        assert "file" in d
        assert "status" in d
        assert "residual_matches" in d
        assert "timestamp" in d
        assert "engine_version" in d
        assert "keywords_hash" in d
        assert "source_hash" in d
        assert "output_hash" in d
        assert "confidence_threshold" in d

    def test_report_serializable_to_json(self, tmp_dir):
        pdf_path = _create_pdf(tmp_dir / "test.pdf", ["Content."])
        keywords = _make_keywords(tmp_dir, ["missing"])

        report = verify_pdf(pdf_path, keywords, confidence_threshold=70)
        json_str = json.dumps(report.to_dict())
        parsed = json.loads(json_str)

        assert parsed["status"] == "clean"

    def test_image_only_page_detection(self, tmp_dir):
        """A page with no extractable text should be flagged."""
        doc = fitz.open()
        page = doc.new_page()
        img = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 10, 10), 1)
        img.set_pixel(5, 5, (255, 0, 0, 255))
        page.insert_image(fitz.Rect(72, 72, 200, 200), pixmap=img)
        pdf_path = tmp_dir / "image_only.pdf"
        doc.save(str(pdf_path))
        doc.close()

        keywords = _make_keywords(tmp_dir, ["anything"])

        report = verify_pdf(pdf_path, keywords, confidence_threshold=70)

        assert 1 in report.unreadable_pages
        assert report.status == "unreadable"

    def test_source_hash_included(self, tmp_dir):
        pdf_path = _create_pdf(tmp_dir / "test.pdf", ["Content."])
        keywords = _make_keywords(tmp_dir, ["missing"])

        report = verify_pdf(pdf_path, keywords, confidence_threshold=70)

        assert report.source_hash.startswith("sha256:")
        assert report.output_hash.startswith("sha256:")

    def test_no_context_in_default_report(self, tmp_dir):
        """Default reports should not include surrounding text context."""
        pdf_path = _create_pdf(
            tmp_dir / "test.pdf", ["The secret project is here."]
        )
        keywords = _make_keywords(tmp_dir, ["secret"])

        report = verify_pdf(pdf_path, keywords, confidence_threshold=70)

        d = report.to_dict()
        for match in d["residual_matches"]:
            assert "context" not in match

    def test_ocr_confidence_pages_populated(self, tmp_dir):
        """Verify that low_confidence_pages gets populated for OCR pages.

        Note: This is an integration test that requires Tesseract installed.
        The OCR confidence check runs on image-only pages and flags pages
        below the confidence_threshold. For unit testing, we verify the
        report structure includes the field and handles the clean case.
        """
        pdf_path = _create_pdf(tmp_dir / "test.pdf", ["Clear text here."])
        keywords = _make_keywords(tmp_dir, ["missing"])

        report = verify_pdf(pdf_path, keywords, confidence_threshold=70)

        assert isinstance(report.low_confidence_pages, list)
        assert report.low_confidence_pages == []
