"""Tests for pywebview API bridge."""

import json
import sys
import types

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


def _create_pdf(path, text="Sample text."):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=12)
    doc.save(str(path))
    doc.close()
    return path


class TestObscuraAPI:
    def test_list_projects_requires_root(self, tmp_dir):
        api = ObscuraAPI(project_root=None, config_dir=tmp_dir)
        result = json.loads(api.list_projects())

        assert result["needs_root"] is True
        assert result["projects"] == []

    def test_list_projects(self, tmp_dir):
        create_project(tmp_dir, "Matter A")
        api = ObscuraAPI(project_root=tmp_dir, config_dir=tmp_dir)

        result = api.list_projects()
        parsed = json.loads(result)["projects"]

        assert len(parsed) == 1
        assert parsed[0]["name"] == "Matter A"

    def test_create_project(self, tmp_dir):
        api = ObscuraAPI(project_root=tmp_dir, config_dir=tmp_dir)

        result = api.create_project("New Matter")
        parsed = json.loads(result)

        assert parsed["name"] == "New Matter"
        assert (tmp_dir / "New Matter" / "project.json").exists()

    def test_create_project_requires_root(self, tmp_dir):
        api = ObscuraAPI(project_root=None, config_dir=tmp_dir)
        with pytest.raises(ValueError, match="Project root not set"):
            api.create_project("No Root")

    def test_run_project(self, tmp_dir):
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\n")
        _add_pdf(project, "doc.pdf", ["Secret text."])

        api = ObscuraAPI(project_root=tmp_dir, config_dir=tmp_dir)
        result = api.run_project("Test")
        parsed = json.loads(result)

        assert parsed["files_processed"] == 1
        assert "total_redactions" in parsed

    def test_get_report(self, tmp_dir):
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\n")
        _add_pdf(project, "doc.pdf", ["Secret."])

        api = ObscuraAPI(project_root=tmp_dir, config_dir=tmp_dir)
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

        api = ObscuraAPI(project_root=tmp_dir, config_dir=tmp_dir)
        result = api.get_keywords("Test")

        assert result == "secret\nconfidential\n"

    def test_save_keywords(self, tmp_dir):
        project = create_project(tmp_dir, "Test")

        api = ObscuraAPI(project_root=tmp_dir, config_dir=tmp_dir)
        api.save_keywords("Test", "new_keyword\nanother\n")

        assert project.keywords_path.read_text() == "new_keyword\nanother\n"

    def test_validate_keywords_reports_errors(self, tmp_dir):
        api = ObscuraAPI(project_root=tmp_dir, config_dir=tmp_dir)
        result = json.loads(api.validate_keywords("regex:[invalid\nok\n"))

        assert result["valid"] is False
        assert len(result["errors"]) == 1
        assert result["errors"][0]["line"] == 1

    def test_list_files_with_report_status(self, tmp_dir):
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\n")
        _add_pdf(project, "doc.pdf", ["Secret."])
        _add_pdf(project, "clean.pdf", ["Clean."])

        report = {
            "schema_version": 1,
            "files": [
                {
                    "file": "doc.pdf",
                    "status": "needs_review",
                    "redactions_applied": 2,
                    "ocr_redactions_applied": 1,
                },
            ],
        }
        (project.reports_dir / "report.json").write_text(
            json.dumps(report), encoding="utf-8"
        )

        api = ObscuraAPI(project_root=tmp_dir, config_dir=tmp_dir)
        result = json.loads(api.list_files("Test"))
        files = {item["file"]: item for item in result["files"]}

        assert files["doc.pdf"]["status"] == "needs_review"
        assert files["doc.pdf"]["redactions_applied"] == 3
        assert files["doc.pdf"]["ocr_redactions_applied"] == 1
        assert files["clean.pdf"]["status"] == "not_run"

    def test_list_files_with_invalid_report(self, tmp_dir):
        project = create_project(tmp_dir, "Test")
        _add_pdf(project, "doc.pdf", ["Secret."])
        (project.reports_dir / "bad.json").write_text("{not-json", encoding="utf-8")

        api = ObscuraAPI(project_root=tmp_dir, config_dir=tmp_dir)
        result = json.loads(api.list_files("Test"))
        assert result["files"][0]["status"] == "not_run"

    def test_add_files_handles_duplicates_and_skips(self, tmp_dir):
        project = create_project(tmp_dir, "Test")
        api = ObscuraAPI(project_root=tmp_dir, config_dir=tmp_dir)

        src1 = tmp_dir / "src1"
        src2 = tmp_dir / "src2"
        src1.mkdir()
        src2.mkdir()

        pdf1 = _create_pdf(src1 / "doc.pdf")
        pdf2 = _create_pdf(src2 / "doc.pdf")
        txt = src1 / "notes.txt"
        txt.write_text("not a pdf")
        link = src1 / "link.pdf"
        link.symlink_to(pdf1)

        result = json.loads(
            api.add_files("Test", paths=[str(pdf1), str(pdf2), str(txt), str(link)])
        )

        assert "doc.pdf" in result["added"]
        assert "doc-1.pdf" in result["added"]
        assert str(txt) in result["skipped"]
        assert str(link) in result["skipped"]

    def test_remove_file_deletes_input_pdf(self, tmp_dir):
        project = create_project(tmp_dir, "Test")
        _add_pdf(project, "doc.pdf", ["Secret."])
        api = ObscuraAPI(project_root=tmp_dir, config_dir=tmp_dir)

        result = json.loads(api.remove_file("Test", "doc.pdf"))

        assert result["status"] == "ok"
        assert result["removed"] == "doc.pdf"
        assert not (project.input_dir / "doc.pdf").exists()

    def test_remove_file_rejects_bad_names_and_missing_files(self, tmp_dir):
        create_project(tmp_dir, "Test")
        api = ObscuraAPI(project_root=tmp_dir, config_dir=tmp_dir)

        for bad_name in ["", "../escape.pdf", "nested/doc.pdf", "/etc/passwd"]:
            result = json.loads(api.remove_file("Test", bad_name))
            assert "error" in result

        missing = json.loads(api.remove_file("Test", "missing.pdf"))
        assert "error" in missing

    def test_remove_file_rejects_non_pdf(self, tmp_dir):
        """remove_file should reject non-PDF files even if they exist in input dir."""
        project = create_project(tmp_dir, "Test")
        txt_file = project.input_dir / "notes.txt"
        txt_file.write_text("some notes")
        api = ObscuraAPI(project_root=tmp_dir, config_dir=tmp_dir)

        result = json.loads(api.remove_file("Test", "notes.txt"))
        assert "error" in result
        assert txt_file.exists()  # File should not have been deleted

    def test_update_project_settings(self, tmp_dir):
        create_project(tmp_dir, "Test")
        api = ObscuraAPI(project_root=tmp_dir, config_dir=tmp_dir)

        result = json.loads(api.update_project_settings("Test", language="spa", confidence_threshold="85"))
        assert result["language"] == "spa"
        assert result["confidence_threshold"] == 85

    def test_get_project_settings(self, tmp_dir):
        create_project(tmp_dir, "Test")
        api = ObscuraAPI(project_root=tmp_dir, config_dir=tmp_dir)

        result = json.loads(api.get_project_settings("Test"))
        assert result["language"] == "eng"
        assert result["confidence_threshold"] == 70

    def test_select_project_root_with_window(self, tmp_dir, monkeypatch):
        root_dir = tmp_dir / "Root"

        class DummyWindow:
            def create_file_dialog(self, *_args, **_kwargs):
                return [str(root_dir)]

        dummy_webview = types.SimpleNamespace(FOLDER_DIALOG=object())
        monkeypatch.setitem(sys.modules, "webview", dummy_webview)

        api = ObscuraAPI(project_root=None, config_dir=tmp_dir)
        api.attach_window(DummyWindow())
        result = json.loads(api.select_project_root())

        assert result["status"] == "ok"
        assert result["root"] == str(root_dir)
        config_data = json.loads((tmp_dir / ".config.json").read_text())
        assert config_data["project_root"] == str(root_dir)

    def test_select_project_root_without_window(self, tmp_dir):
        api = ObscuraAPI(project_root=None, config_dir=tmp_dir)
        result = json.loads(api.select_project_root())
        assert result["error"] == "Window not ready"

    def test_open_and_reveal_missing_file(self, tmp_dir):
        project = create_project(tmp_dir, "Test")
        api = ObscuraAPI(project_root=tmp_dir, config_dir=tmp_dir)

        result = json.loads(api.open_in_preview("Test", "missing.pdf"))
        assert "error" in result
        result = json.loads(api.open_in_preview("Test", "../escape.pdf"))
        assert "error" in result
        result = json.loads(api.reveal_in_finder("Test", "missing.pdf"))
        assert "error" in result

    def test_open_and_reveal_valid_file(self, tmp_dir, monkeypatch):
        project = create_project(tmp_dir, "Test")
        output_path = project.output_dir / "doc_redacted.pdf"
        _create_pdf(output_path)

        calls = []

        def fake_popen(args):
            calls.append(args)
            class DummyProc:
                pass
            return DummyProc()

        monkeypatch.setattr("obscura.api.subprocess.Popen", fake_popen)

        api = ObscuraAPI(project_root=tmp_dir, config_dir=tmp_dir)
        api.open_in_preview("Test", "doc.pdf")
        api.reveal_in_finder("Test", "doc.pdf")

        assert calls[0][:2] == ["open", "--"]
        assert calls[0][2].endswith("doc_redacted.pdf")
        assert calls[1][:3] == ["open", "-R", "--"]
        assert calls[1][3].endswith("doc_redacted.pdf")

    def test_resolve_project_rejects_traversal(self, tmp_dir):
        api = ObscuraAPI(project_root=tmp_dir, config_dir=tmp_dir)
        with pytest.raises(ValueError, match="outside root"):
            api.get_keywords("../escape")

    def test_resolve_output_file_rejects_absolute_and_empty(self, tmp_dir):
        project = create_project(tmp_dir, "Test")
        api = ObscuraAPI(project_root=tmp_dir, config_dir=tmp_dir)

        for bad_name in ["", "/etc/passwd", "sub/dir.pdf"]:
            result = json.loads(api.open_in_preview("Test", bad_name))
            assert "error" in result, f"Expected rejection for {bad_name!r}"
