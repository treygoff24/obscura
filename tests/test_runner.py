"""Tests for run orchestrator — full pipeline per project."""

import json

import fitz
import pytest

from obscura.project import create_project
from obscura.runner import run_project, RunSummary


def _add_pdf_to_project(project, filename: str, pages: list[str]):
    path = project.input_dir / filename
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=12)
    doc.save(str(path))
    doc.close()
    return path


class TestRunProject:
    def test_processes_all_input_pdfs(self, tmp_dir):
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\n")
        _add_pdf_to_project(project, "doc1.pdf", ["Secret info here."])
        _add_pdf_to_project(project, "doc2.pdf", ["More secret data."])

        summary = run_project(project)

        assert summary.files_processed == 2
        assert (project.output_dir / "doc1_redacted.pdf").exists()
        assert (project.output_dir / "doc2_redacted.pdf").exists()

    def test_generates_verification_report(self, tmp_dir):
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\n")
        _add_pdf_to_project(project, "doc1.pdf", ["Secret content."])

        summary = run_project(project)

        report_files = list(project.reports_dir.glob("*.json"))
        assert len(report_files) == 1

        report_data = json.loads(report_files[0].read_text())
        assert report_data["schema_version"] == 1
        assert "run_id" in report_data
        assert "engine_version" in report_data
        assert "settings" in report_data
        assert "files" in report_data
        assert len(report_data["files"]) == 1
        assert report_data["files"][0]["file"] == "doc1.pdf"
        assert "redactions_applied" in report_data["files"][0]

    def test_redacted_text_not_in_output(self, tmp_dir):
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\n")
        _add_pdf_to_project(project, "doc.pdf", ["The secret password."])

        run_project(project)

        doc = fitz.open(str(project.output_dir / "doc_redacted.pdf"))
        text = doc[0].get_text()
        doc.close()
        assert "secret" not in text.lower()

    def test_metadata_scrubbed_in_output(self, tmp_dir):
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("anything\n")

        path = project.input_dir / "doc.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Clean text.")
        doc.set_metadata({"author": "John Doe"})
        doc.save(str(path))
        doc.close()

        run_project(project)

        doc = fitz.open(str(project.output_dir / "doc_redacted.pdf"))
        assert doc.metadata.get("author", "") == ""
        doc.close()

    def test_updates_last_run(self, tmp_dir):
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\n")
        _add_pdf_to_project(project, "doc.pdf", ["Secret."])

        assert project.last_run is None

        run_project(project)

        from obscura.project import Project
        reloaded = Project.load(project.path)
        assert reloaded.last_run is not None

    def test_empty_project_no_crash(self, tmp_dir):
        project = create_project(tmp_dir, "Empty")
        project.keywords_path.write_text("secret\n")

        summary = run_project(project)

        assert summary.files_processed == 0

    def test_summary_structure(self, tmp_dir):
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\n")
        _add_pdf_to_project(project, "doc.pdf", ["Secret."])

        summary = run_project(project)

        assert isinstance(summary, RunSummary)
        assert summary.files_processed == 1
        assert isinstance(summary.total_redactions, int)
        assert isinstance(summary.files_needing_review, int)
        assert isinstance(summary.files_errored, int)

    def test_per_file_error_isolation(self, tmp_dir):
        """If one file fails during processing, others should still complete."""
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\n")
        _add_pdf_to_project(project, "good.pdf", ["Secret info."])
        (project.input_dir / "bad.pdf").write_bytes(b"not a pdf")

        summary = run_project(project)

        assert summary.files_processed == 2
        assert (project.output_dir / "good_redacted.pdf").exists()
        assert summary.files_errored >= 0

    def test_empty_keywords_raises(self, tmp_dir):
        """Running with an empty keywords file should raise ValueError."""
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("")
        _add_pdf_to_project(project, "doc.pdf", ["Content."])

        with pytest.raises(ValueError, match="Keywords file is empty"):
            run_project(project)

    def test_report_schema_has_metadata(self, tmp_dir):
        """Report should use versioned envelope with run metadata."""
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\n")
        _add_pdf_to_project(project, "doc.pdf", ["Secret."])

        run_project(project)

        report_files = list(project.reports_dir.glob("*.json"))
        report_data = json.loads(report_files[0].read_text())
        assert report_data["schema_version"] == 1
        assert "run_id" in report_data
        assert "engine_version" in report_data
        assert "project_name" in report_data
        assert report_data["settings"]["language"] == "eng"
        assert "keywords_hash" in report_data["settings"]
        assert "redactions_applied" in report_data["files"][0]

    def test_error_during_sanitize_is_recorded(self, tmp_dir, monkeypatch):
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\n")
        _add_pdf_to_project(project, "doc.pdf", ["Secret."])

        def boom(*_args, **_kwargs):
            raise RuntimeError("sanitize failed")

        monkeypatch.setattr("obscura.runner.sanitize_pdf", boom)

        summary = run_project(project)

        assert summary.files_processed == 1
        assert summary.files_errored == 1

        report_files = list(project.reports_dir.glob("*.json"))
        report_data = json.loads(report_files[0].read_text())
        assert report_data["files"][0]["status"] == "error"

    def test_report_paths_are_unique_for_back_to_back_runs(self, tmp_dir):
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\n")
        _add_pdf_to_project(project, "doc.pdf", ["Secret."])

        summary1 = run_project(project)
        summary2 = run_project(project)

        assert summary1.report_path != summary2.report_path
        report_files = sorted(project.reports_dir.glob("*.json"))
        assert len(report_files) == 2

    def test_prunes_stale_output_files_when_inputs_removed(self, tmp_dir):
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\n")
        _add_pdf_to_project(project, "a.pdf", ["Secret one."])
        _add_pdf_to_project(project, "b.pdf", ["Secret two."])

        run_project(project)
        assert (project.output_dir / "a_redacted.pdf").exists()
        assert (project.output_dir / "b_redacted.pdf").exists()

        (project.input_dir / "b.pdf").unlink()
        run_project(project)

        assert (project.output_dir / "a_redacted.pdf").exists()
        assert not (project.output_dir / "b_redacted.pdf").exists()

    def test_report_includes_output_file_mapping(self, tmp_dir):
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\n")
        _add_pdf_to_project(project, "doc.pdf", ["Secret."])

        run_project(project)

        report_files = sorted(project.reports_dir.glob("*.json"))
        report_data = json.loads(report_files[-1].read_text())
        assert report_data["files"][0]["file"] == "doc.pdf"
        assert report_data["files"][0]["output_file"] == "doc_redacted.pdf"

    def test_symlink_pdfs_survive_pruning(self, tmp_dir):
        """Symlink PDFs in output dir should not be pruned."""
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\n")
        _add_pdf_to_project(project, "a.pdf", ["Secret one."])

        run_project(project)
        assert (project.output_dir / "a_redacted.pdf").exists()

        # Create a symlink PDF in output that doesn't match any input
        real_pdf = project.output_dir / "a_redacted.pdf"
        symlink_pdf = project.output_dir / "linked.pdf"
        symlink_pdf.symlink_to(real_pdf)

        # Re-run — symlink should survive pruning
        run_project(project)
        assert symlink_pdf.is_symlink()
        assert symlink_pdf.exists()

    def test_non_pdf_files_survive_pruning(self, tmp_dir):
        """Non-PDF files in output dir should not be pruned."""
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\n")
        _add_pdf_to_project(project, "a.pdf", ["Secret one."])

        run_project(project)

        # Add a non-PDF file to output dir
        txt_file = project.output_dir / "notes.txt"
        txt_file.write_text("some notes")

        # Re-run — .txt should survive since pruning only globs *.pdf
        run_project(project)
        assert txt_file.exists()

    def test_already_redacted_filename_not_double_suffixed(self, tmp_dir):
        """Input named 'doc_redacted.pdf' should output as 'doc_redacted.pdf', not 'doc_redacted_redacted.pdf'."""
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\n")
        _add_pdf_to_project(project, "doc_redacted.pdf", ["Secret info."])

        run_project(project)

        assert (project.output_dir / "doc_redacted.pdf").exists()
        assert not (project.output_dir / "doc_redacted_redacted.pdf").exists()

    def test_colliding_input_names_get_distinct_output_files(self, tmp_dir):
        """doc.pdf and doc_redacted.pdf must not overwrite each other's output."""
        project = create_project(tmp_dir, "Test")
        project.keywords_path.write_text("secret\n")
        _add_pdf_to_project(project, "doc.pdf", ["Secret A."])
        _add_pdf_to_project(project, "doc_redacted.pdf", ["Secret B."])

        run_project(project)

        outputs = sorted(p.name for p in project.output_dir.glob("*.pdf"))
        assert len(outputs) == 2
        assert "doc_redacted.pdf" in outputs
        assert any(name.startswith("doc_redacted_") and name.endswith(".pdf") for name in outputs)

        report_files = sorted(project.reports_dir.glob("*.json"))
        report_data = json.loads(report_files[-1].read_text())
        mapping = {entry["file"]: entry["output_file"] for entry in report_data["files"]}
        assert mapping["doc.pdf"] != mapping["doc_redacted.pdf"]
