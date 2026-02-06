"""Tests for shared naming utilities."""

import pytest

from obscura.naming import disambiguate_output_filenames, output_filename_for_input


class TestOutputFilenameForInput:
    def test_normal_pdf(self):
        assert output_filename_for_input("doc.pdf") == "doc_redacted.pdf"

    def test_already_redacted_lowercase(self):
        assert output_filename_for_input("doc_redacted.pdf") == "doc_redacted.pdf"

    def test_already_redacted_mixed_case(self):
        assert output_filename_for_input("Doc_Redacted.PDF") == "Doc_Redacted.PDF"

    def test_no_extension(self):
        assert output_filename_for_input("doc") == "doc_redacted"

    def test_multiple_dots(self):
        assert output_filename_for_input("my.file.pdf") == "my.file_redacted.pdf"

    def test_empty_string(self):
        result = output_filename_for_input("")
        assert isinstance(result, str)


class TestDisambiguateOutputFilenames:
    def test_collision_gets_suffix(self):
        mapping = disambiguate_output_filenames(["doc.pdf", "doc_redacted.pdf"])
        assert mapping["doc.pdf"] == "doc_redacted.pdf"
        assert mapping["doc_redacted.pdf"] == "doc_redacted_1.pdf"

    def test_case_insensitive_collision(self):
        mapping = disambiguate_output_filenames(["Doc.pdf", "doc.pdf"])
        assert mapping["Doc.pdf"] == "Doc_redacted.pdf"
        assert mapping["doc.pdf"] == "doc_redacted_1.pdf"
