"""Unit tests for Phase 3: Project REPL & Workspace Memory System."""

from pathlib import Path
import pytest
from contracts import ImplementationResult, TaskBrief, TechnicalSpec
from tools.project_notes import (
    get_project_env,
    init_project_workspace,
    load_project_profile,
    prepare_project,
    set_project_env,
    update_project_profile,
    validate_project_id,
)
from tools.session import mask_secret, run_project_session


def test_validate_project_id():
    assert validate_project_id("my-project") == "my-project"
    assert validate_project_id("crm_integration_2026") == "crm_integration_2026"
    with pytest.raises(ValueError):
        validate_project_id("../path-traversal")
    with pytest.raises(ValueError):
        validate_project_id("bad project name with spaces")


def test_init_project_workspace(tmp_path):
    ws_dir, profile_path = init_project_workspace("test-proj", workspace_root=tmp_path)
    assert ws_dir.exists()
    assert profile_path.exists()

    # Verify .gitignore protects .env
    gitignore = (ws_dir / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore

    # Verify initial PROJECT_PROFILE.md structure
    profile_content = profile_path.read_text(encoding="utf-8")
    assert "# Project Profile: test-proj" in profile_content
    assert "## Active Data Schemas & Entities" in profile_content
    assert "## User Input Surfaces & Entry Points" in profile_content
    assert "## Task History" in profile_content

    # Verify .env created
    env_path = ws_dir / ".env"
    assert env_path.exists()


def test_project_env_get_and_set(tmp_path):
    init_project_workspace("env-proj", workspace_root=tmp_path)
    set_project_env("env-proj", "SPREADSHEET_ID", "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms", workspace_root=tmp_path)
    set_project_env("env-proj", "WEBHOOK_TOKEN", "secret-token-xyz", workspace_root=tmp_path)

    env_vars = get_project_env("env-proj", workspace_root=tmp_path)
    assert env_vars.get("SPREADSHEET_ID") == "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
    assert env_vars.get("WEBHOOK_TOKEN") == "secret-token-xyz"

    # Update variable
    set_project_env("env-proj", "WEBHOOK_TOKEN", "new-token-123", workspace_root=tmp_path)
    env_vars2 = get_project_env("env-proj", workspace_root=tmp_path)
    assert env_vars2.get("WEBHOOK_TOKEN") == "new-token-123"


def test_update_project_profile(tmp_path):
    brief = TaskBrief(
        task_id="task-profile-1",
        title="Google Form Data Ingestion",
        objective="Collect transactions from form into sheet",
        slug="form-sync",
        target_lead="meti",
        research_questions=[],
    )
    spec = TechnicalSpec(
        task_id="task-profile-1",
        architecture_overview="Apps script mapper",
        required_dependencies=[],
        base_image="node:18-bullseye-slim",
        phases=[],
        input_interface_spec="Google Form with fields: Date, Amount, Category",
    )
    result = ImplementationResult(
        task_id="task-profile-1",
        status="success",
        summary="Automated Google Form created and verified with direct sync",
        executed_phases=["1-form", "2-sync"],
    )

    profile_path = update_project_profile(
        "profile-proj",
        task_id="task-profile-1",
        brief=brief,
        spec=spec,
        result=result,
        workspace_root=tmp_path,
    )
    content = profile_path.read_text(encoding="utf-8")
    assert "Google Form with fields: Date, Amount, Category" in content
    assert "task-profile-1" in content
    assert "Automated Google Form created" in content


def test_prepare_project_loads_profile_memory_in_prompt(tmp_path):
    vault = tmp_path / "vault"
    ws = tmp_path / "workspace"

    # Initialize project and add custom memory
    _, profile_path = init_project_workspace("mem-proj", workspace_root=ws)
    profile_path.write_text(
        "# Project Profile: mem-proj\n\n## Active Data Schemas & Entities\nColumns: ID, Date, Amount, Notes\n",
        encoding="utf-8",
    )

    context = prepare_project(vault, "mem-proj", workspace_root=ws)
    assert "Project ID: mem-proj" in context.prompt
    assert "--- EXISTING PROJECT PROFILE & MEMORY ---" in context.prompt
    assert "Columns: ID, Date, Amount, Notes" in context.prompt
    assert "Respect existing data schemas and project decisions" in context.prompt


def test_mask_secret():
    assert mask_secret("short") == "******"
    masked = mask_secret("tvly-dev-secret-key-12345")
    assert masked.startswith("tvly")
    assert masked.endswith("45")
    assert len(masked) == len("tvly-dev-secret-key-12345")


@pytest.mark.anyio
async def test_run_project_session_commands(tmp_path, capsys):
    vault = tmp_path / "vault"
    ws = tmp_path / "workspace"

    dispatched_tasks = []

    def mock_task_runner(project_id: str, prompt: str):
        dispatched_tasks.append((project_id, prompt))
        return "Task finished"

    # Simulate user entering:
    # 1. /profile
    # 2. /env
    # 3. Enter (skip env update)
    # 4. A regular task prompt: "Add export to CSV"
    # 5. /exit
    inputs = ["/profile", "/env", "", "Add export to CSV", "/exit"]

    await run_project_session(
        project_id="session-proj",
        vault_path=vault,
        workspace_root=ws,
        input_func=lambda _: inputs.pop(0),
        task_runner=mock_task_runner,
    )

    out = capsys.readouterr().out
    assert "BuildRelay — Interactive Project Session" in out
    assert "Project Profile: session-proj" in out
    assert "Project Secrets & Configurations" in out
    assert "Session ended. Project memory preserved." in out

    assert len(dispatched_tasks) == 1
    assert dispatched_tasks[0] == ("session-proj", "Add export to CSV")
