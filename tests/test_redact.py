"""Tests for PDF redaction engine."""

import pathlib

import fitz
import pytest

from obscura.keywords import KeywordSet
from obscura.redact import RedactionResult, redact_pdf


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