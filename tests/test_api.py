"""Tests for pywebview API bridge."""

import json

import fitz
import pytest

from obscura.api import ObscuraAPI
from obscura.project import create_project


def _add_pdf(project, filename, pages):
    path = project.input_dir / filename
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=12)
    doc.save(str(path))
    doc.close()


class TestObscuraAPI:
    def test_list_projects(self, tmp_dir):
        create_project(tmp_dir, "Matter A")
        api = ObscuraAPI(project_root=tmp_dir)

        result = api.list_projects()
        parsed = json.loads(result)

        assert len(parsed) == 1
        assert parsed[0]["name"] == "Matter A"

    def test_create_project(self, tmp_dir):
        api = ObscuraAPI(project_root=tmp_dir)

        result = api.create_project("New Matter")
        parsed = json.loads(result)

        assert parsed["name"] == "New Matter"
        assert (tmp_dir / "New Matter" / "project.json").exists()

    def test_run_project(self, tmp_dir):
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\n")
        _add_pdf(project, "doc.pdf", ["Secret text."])

        api = ObscuraAPI(project_root=tmp_dir)
        result = api.run_project("Test")
        parsed = json.loads(result)

        assert parsed["files_processed"] == 1
        assert "total_redactions" in parsed

    def test_get_report(self, tmp_dir):
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\n")
        _add_pdf(project, "doc.pdf", ["Secret."])

        api = ObscuraAPI(project_root=tmp_dir)
        api.run_project("Test")

        result = api.get_latest_report("Test")
        parsed = json.loads(result)

        assert isinstance(parsed, dict)
        assert "schema_version" in parsed
        assert "files" in parsed
        assert len(parsed["files"]) == 1

    def test_get_keywords(self, tmp_dir):
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\nconfidential\n")

        api = ObscuraAPI(project_root=tmp_dir)
        result = api.get_keywords("Test")

        assert result == "secret\nconfidential\n"

    def test_save_keywords(self, tmp_dir):
        project = create_project(tmp_dir, "Test")

        api = ObscuraAPI(project_root=tmp_dir)
        api.save_keywords("Test", "new_keyword\nanother\n")

        assert project.keywords_path.read_text() == "new_keyword\nanother\n"