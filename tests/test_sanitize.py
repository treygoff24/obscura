"""Tests for PDF sanitization step."""

import fitz
import pytest

from obscura.sanitize import sanitize_pdf


def _create_pdf_with_metadata(path, metadata: dict, text: str = "Sample text."):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=12)
    doc.set_metadata(metadata)
    doc.save(str(path))
    doc.close()
    return path


def _create_pdf_with_annotation(path, text="Annotated doc."):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=12)
    annot = page.add_text_annot((100, 100), "This is a sticky note")
    doc.save(str(path))
    doc.close()
    return path


def _create_pdf_with_embedded_file(path, text="Doc with attachment."):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=12)
    doc.embfile_add("secret.txt", b"secret content", filename="secret.txt")
    doc.save(str(path))
    doc.close()
    return path


class TestSanitizePdf:
    def test_scrubs_metadata(self, tmp_dir):
        input_path = _create_pdf_with_metadata(
            tmp_dir / "input.pdf",
            {"author": "John Doe", "title": "Secret Report", "subject": "Classified"},
        )
        output_path = tmp_dir / "output.pdf"

        sanitize_pdf(input_path, output_path)

        doc = fitz.open(str(output_path))
        meta = doc.metadata
        doc.close()
        assert meta.get("author", "") == ""
        assert meta.get("title", "") == ""
        assert meta.get("subject", "") == ""

    def test_removes_annotations(self, tmp_dir):
        input_path = _create_pdf_with_annotation(tmp_dir / "input.pdf")
        output_path = tmp_dir / "output.pdf"

        sanitize_pdf(input_path, output_path)

        doc = fitz.open(str(output_path))
        annots = list(doc[0].annots() or [])
        doc.close()
        assert len(annots) == 0

    def test_removes_embedded_files(self, tmp_dir):
        input_path = _create_pdf_with_embedded_file(tmp_dir / "input.pdf")
        output_path = tmp_dir / "output.pdf"

        sanitize_pdf(input_path, output_path)

        doc = fitz.open(str(output_path))
        assert doc.embfile_count() == 0
        doc.close()

    def test_collapses_incremental_updates(self, tmp_dir):
        input_path = tmp_dir / "input.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Version 1")
        doc.save(str(input_path))
        doc.close()

        doc = fitz.open(str(input_path))
        doc[0].insert_text((72, 120), "Version 2")
        doc.save(str(input_path), incremental=True, encryption=0)
        doc.close()

        output_path = tmp_dir / "output.pdf"
        sanitize_pdf(input_path, output_path)

        output_size = output_path.stat().st_size
        input_size = input_path.stat().st_size
        assert output_size <= input_size

    def test_sanitize_in_place(self, tmp_dir):
        """Sanitize can write to the same path (via atomic temp file)."""
        path = _create_pdf_with_metadata(
            tmp_dir / "doc.pdf",
            {"author": "John Doe"},
        )

        sanitize_pdf(path, path)

        doc = fitz.open(str(path))
        assert doc.metadata.get("author", "") == ""
        doc.close()

    def test_removes_xmp_metadata(self, tmp_dir):
        """XMP metadata (XML-based) should be cleared separately from standard metadata."""
        input_path = tmp_dir / "input.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Sample text.")
        doc.set_metadata({"author": "John Doe"})
        xmp = '<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?><x:xmpmeta><rdf:RDF><rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:creator>Secret Author</dc:creator></rdf:Description></rdf:RDF></x:xmpmeta>'
        doc.set_xml_metadata(xmp)
        doc.save(str(input_path))
        doc.close()

        output_path = tmp_dir / "output.pdf"
        sanitize_pdf(input_path, output_path)

        doc = fitz.open(str(output_path))
        xml_meta = doc.get_xml_metadata()
        doc.close()
        assert "Secret Author" not in xml_meta

    def test_removes_form_fields(self, tmp_dir):
        """Form fields / widgets should be removed."""
        input_path = tmp_dir / "input.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Form document.")
        widget = fitz.Widget()
        widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        widget.field_name = "secret_field"
        widget.field_value = "secret value"
        widget.rect = fitz.Rect(72, 100, 300, 130)
        page.add_widget(widget)
        doc.save(str(input_path))
        doc.close()

        output_path = tmp_dir / "output.pdf"
        sanitize_pdf(input_path, output_path)

        doc = fitz.open(str(output_path))
        widgets = list(doc[0].widgets() or [])
        doc.close()
        assert len(widgets) == 0

    def test_preserves_page_content(self, tmp_dir):
        input_path = _create_pdf_with_metadata(
            tmp_dir / "input.pdf",
            {"author": "John Doe"},
            text="Important content here.",
        )
        output_path = tmp_dir / "output.pdf"

        sanitize_pdf(input_path, output_path)

        doc = fitz.open(str(output_path))
        text = doc[0].get_text()
        doc.close()
        assert "Important content here" in text