"""Tests for project model — folder structure, project.json, discovery."""

import json

import pytest

from obscura.project import Project, discover_projects, create_project


class TestCreateProject:
    def test_creates_project_folder_structure(self, tmp_dir):
        project = create_project(tmp_dir, "Test Matter")

        assert (tmp_dir / "Test Matter" / "project.json").exists()
        assert (tmp_dir / "Test Matter" / "keywords.txt").exists()
        assert (tmp_dir / "Test Matter" / "input").is_dir()
        assert (tmp_dir / "Test Matter" / "output").is_dir()
        assert (tmp_dir / "Test Matter" / "reports").is_dir()

    def test_project_json_has_schema_version(self, tmp_dir):
        project = create_project(tmp_dir, "Test Matter")
        data = json.loads((tmp_dir / "Test Matter" / "project.json").read_text())
        assert data["schema_version"] == 1

    def test_project_json_has_required_fields(self, tmp_dir):
        project = create_project(tmp_dir, "Test Matter")
        data = json.loads((tmp_dir / "Test Matter" / "project.json").read_text())
        assert "name" in data
        assert "created" in data
        assert "language" in data
        assert "confidence_threshold" in data
        assert data["name"] == "Test Matter"
        assert data["language"] == "eng"
        assert data["confidence_threshold"] == 70

    def test_custom_language_and_threshold(self, tmp_dir):
        project = create_project(
            tmp_dir, "Spanish Matter", language="spa", confidence_threshold=80
        )
        data = json.loads((tmp_dir / "Spanish Matter" / "project.json").read_text())
        assert data["language"] == "spa"
        assert data["confidence_threshold"] == 80

    def test_duplicate_name_raises(self, tmp_dir):
        create_project(tmp_dir, "Test Matter")
        with pytest.raises(FileExistsError):
            create_project(tmp_dir, "Test Matter")

    def test_rejects_path_separator_in_name(self, tmp_dir):
        with pytest.raises(ValueError, match="Invalid project name"):
            create_project(tmp_dir, "bad/name")

    def test_rejects_path_traversal(self, tmp_dir):
        with pytest.raises(ValueError, match="Invalid project name"):
            create_project(tmp_dir, "../escape")

    def test_rejects_too_long_name(self, tmp_dir):
        with pytest.raises(ValueError, match="Invalid project name"):
            create_project(tmp_dir, "a" * 256)


class TestProjectLoad:
    def test_load_valid_project(self, tmp_dir):
        create_project(tmp_dir, "Test Matter")
        project = Project.load(tmp_dir / "Test Matter")
        assert project.name == "Test Matter"
        assert project.language == "eng"
        assert project.confidence_threshold == 70

    def test_load_invalid_folder_raises(self, tmp_dir):
        (tmp_dir / "not_a_project").mkdir()
        with pytest.raises(ValueError, match="schema_version"):
            Project.load(tmp_dir / "not_a_project")

    def test_load_wrong_schema_version(self, tmp_dir):
        project_dir = tmp_dir / "BadVersion"
        project_dir.mkdir()
        (project_dir / "project.json").write_text(
            json.dumps({"schema_version": 999, "name": "Bad"})
        )
        with pytest.raises(ValueError, match="schema_version"):
            Project.load(project_dir)


class TestDiscoverProjects:
    def test_discovers_valid_projects(self, tmp_dir):
        create_project(tmp_dir, "Matter A")
        create_project(tmp_dir, "Matter B")
        (tmp_dir / "random_folder").mkdir()

        projects = discover_projects(tmp_dir)
        names = [p.name for p in projects]
        assert "Matter A" in names
        assert "Matter B" in names
        assert len(projects) == 2

    def test_empty_root(self, tmp_dir):
        projects = discover_projects(tmp_dir)
        assert projects == []

    def test_ignores_hidden_folders(self, tmp_dir):
        create_project(tmp_dir, "Matter A")
        (tmp_dir / ".hidden").mkdir()
        (tmp_dir / ".hidden" / "project.json").write_text(
            json.dumps({"schema_version": 1, "name": ".hidden"})
        )
        projects = discover_projects(tmp_dir)
        names = [p.name for p in projects]
        assert ".hidden" not in names


class TestProjectPaths:
    def test_input_dir(self, tmp_dir):
        project = create_project(tmp_dir, "Test Matter")
        assert project.input_dir == tmp_dir / "Test Matter" / "input"

    def test_output_dir(self, tmp_dir):
        project = create_project(tmp_dir, "Test Matter")
        assert project.output_dir == tmp_dir / "Test Matter" / "output"

    def test_reports_dir(self, tmp_dir):
        project = create_project(tmp_dir, "Test Matter")
        assert project.reports_dir == tmp_dir / "Test Matter" / "reports"

    def test_keywords_path(self, tmp_dir):
        project = create_project(tmp_dir, "Test Matter")
        assert project.keywords_path == tmp_dir / "Test Matter" / "keywords.txt"