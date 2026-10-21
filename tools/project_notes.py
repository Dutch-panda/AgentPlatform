import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


def validate_project_id(project_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", project_id):
        raise ValueError("Project ID must contain only letters, digits, underscores, or hyphens")
    return project_id


@dataclass(frozen=True)
class ProjectContext:
    project_id: str | None

    @property
    def link(self) -> str:
        return f"[[projects/{self.project_id}]]" if self.project_id else ""

    @property
    def frontmatter(self) -> str:
        return f'project: "{self.link}"\n' if self.project_id else ""

    @property
    def body(self) -> str:
        return f"Project: {self.link}\n\n" if self.project_id else ""

    @property
    def prompt(self) -> str:
        return (
            f"Project ID: {self.project_id}\nParent project: {self.link}\n"
            "Keep this project ID unchanged.\n"
            if self.project_id else "Project ID: none. This task has no parent project.\n"
        )


def prepare_project(vault_path: Path, project_id: str | None) -> ProjectContext:
    if project_id is None:
        return ProjectContext(None)
    validate_project_id(project_id)
    vault_root = vault_path.resolve()
    projects_dir = (vault_root / "projects").resolve()
    note_path = projects_dir / f"{project_id}.md"
    if not projects_dir.is_relative_to(vault_root) or projects_dir == vault_root:
        raise ValueError("Project notes must be within the vault")
    if note_path.is_symlink():
        raise ValueError("Project notes must not be symbolic links")
    projects_dir.mkdir(parents=True, exist_ok=True)
    try:
        with note_path.open("x", encoding="utf-8") as note:
            note.write(
                f'---\nid: "{project_id}"\ntype: "project"\n'
                f'created_at: "{datetime.now():%Y-%m-%d}"\n---\n'
                f"# {project_id}\n"
            )
    except FileExistsError:
        if not note_path.is_file():
            raise ValueError("Project note path must be a Markdown file") from None
    return ProjectContext(project_id)
