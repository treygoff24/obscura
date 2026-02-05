"""Project model — folder structure, project.json, discovery."""

from __future__ import annotations

import dataclasses
import json
import pathlib
from datetime import datetime, timezone

SCHEMA_VERSION = 1


@dataclasses.dataclass
class Project:
    """Represents an Obscura project folder on disk."""

    path: pathlib.Path
    name: str
    created: str
    last_run: str | None
    language: str
    confidence_threshold: int

    @classmethod
    def load(cls, project_dir: pathlib.Path) -> Project:
        """Load a project from its directory.

        Raises:
            ValueError: If project.json is missing or has wrong schema_version.
        """
        config_path = project_dir / "project.json"
        if not config_path.exists():
            raise ValueError(
                f"Not a valid project (missing project.json): {project_dir}. "
                "Expected schema_version 1."
            )

        data = json.loads(config_path.read_text(encoding="utf-8"))
        if data.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported schema_version {data.get('schema_version')} "
                f"in {config_path}. Expected {SCHEMA_VERSION}."
            )

        return cls(
            path=project_dir,
            name=data["name"],
            created=data.get("created", ""),
            last_run=data.get("last_run"),
            language=data.get("language", "eng"),
            confidence_threshold=data.get("confidence_threshold", 70),
        )

    def save(self) -> None:
        """Write project.json to disk."""
        data = {
            "schema_version": SCHEMA_VERSION,
            "name": self.name,
            "created": self.created,
            "last_run": self.last_run,
            "language": self.language,
            "confidence_threshold": self.confidence_threshold,
        }
        config_path = self.path / "project.json"
        config_path.write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8"
        )

    @property
    def input_dir(self) -> pathlib.Path:
        return self.path / "input"

    @property
    def output_dir(self) -> pathlib.Path:
        return self.path / "output"

    @property
    def reports_dir(self) -> pathlib.Path:
        return self.path / "reports"

    @property
    def keywords_path(self) -> pathlib.Path:
        return self.path / "keywords.txt"


_INVALID_NAME_CHARS = set('/\\:*?"<>|')
_MAX_NAME_LENGTH = 255


def _validate_project_name(name: str) -> None:
    """Validate project name for filesystem safety.

    Raises:
        ValueError: If the name is invalid.
    """
    if not name or not name.strip():
        raise ValueError("Invalid project name: name cannot be empty")
    if len(name) > _MAX_NAME_LENGTH:
        raise ValueError(
            f"Invalid project name: exceeds {_MAX_NAME_LENGTH} characters"
        )
    if any(c in name for c in _INVALID_NAME_CHARS):
        raise ValueError(
            f"Invalid project name: contains reserved characters"
        )
    if name.startswith(".") or ".." in name:
        raise ValueError("Invalid project name: path traversal not allowed")


def create_project(
    root: pathlib.Path,
    name: str,
    language: str = "eng",
    confidence_threshold: int = 70,
) -> Project:
    """Create a new project folder with all required structure.

    Args:
        root: The project root directory (e.g. ~/Obscura/).
        name: Project name (becomes the folder name).
        language: Tesseract language code.
        confidence_threshold: OCR confidence cutoff (0-100).

    Returns:
        The newly created Project.

    Raises:
        FileExistsError: If a project with that name already exists.
        ValueError: If the project name is invalid.
    """
    _validate_project_name(name)
    project_dir = root / name
    if project_dir.exists():
        raise FileExistsError(f"Project already exists: {project_dir}")

    project_dir.mkdir(parents=True)
    (project_dir / "input").mkdir()
    (project_dir / "output").mkdir()
    (project_dir / "reports").mkdir()
    (project_dir / "keywords.txt").write_text("", encoding="utf-8")

    project = Project(
        path=project_dir,
        name=name,
        created=datetime.now(timezone.utc).isoformat(),
        last_run=None,
        language=language,
        confidence_threshold=confidence_threshold,
    )
    project.save()
    return project


def discover_projects(root: pathlib.Path) -> list[Project]:
    """Scan a root directory and return all valid projects.

    Skips hidden folders and folders without a valid project.json.
    """
    projects: list[Project] = []
    if not root.exists():
        return projects

    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        try:
            projects.append(Project.load(child))
        except (ValueError, json.JSONDecodeError):
            continue

    return projects