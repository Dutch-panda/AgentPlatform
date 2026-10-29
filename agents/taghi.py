import asyncio
import re
from pathlib import Path
from datetime import datetime
from pydantic_ai import Agent
from pydantic_ai.models import Model
from contracts import ExecutionPhase, TechnicalSpec
from tools.graphify_tool import GraphifyVaultManager
from tools.project_notes import prepare_project
from tools.vault_infra import (
    register_graph_tools,
    register_note_writer_tool,
    update_vault_graph,
)
from tools.ui import print_agent

class TaghiArchitect:
    def __init__(
        self,
        vault_path: str | Path = "./vault",
        model_name: str | Model = "openai-chat:gpt-4o",
        graph_manager: GraphifyVaultManager | None = None,
        specs_dir: str | Path | None = None,
        research_dir: str | Path | None = None,
    ):
        self.vault_path = Path(vault_path)
        self.model_name = model_name
        self.specs_dir = Path(specs_dir) if specs_dir is not None else self.vault_path / "specs"
        self.research_dir = Path(research_dir) if research_dir is not None else self.vault_path / "research"
        self.graph_manager = graph_manager or GraphifyVaultManager(vault_path=str(self.vault_path))

        self.agent = Agent(
            model_name,
            output_type=TechnicalSpec,
            model_settings={"cache": True},
            system_prompt=(
                "You are Taghi, Technical Design Lead. Verify that the task is designated for design/architecture. "
                "Translate research reports into precise technical specifications and sequential execution phases for Meti. "
                "Select a suitable Docker base_image for the required runtime (e.g. 'python:3.11-slim' for Python tasks, "
                "'node:18-bullseye-slim' for Node/JS/TS, or an appropriate slim image).\n\n"
                "CRITICAL EXECUTION CONSTRAINTS FOR METI SANDBOX:\n"
                "- Meti executes and validates all phases autonomously inside an isolated Docker container without host credentials or live external API keys.\n"
                "- Every phase in 'phases' MUST be fully executable and verifiable inside the container environment using offline test suites, fixtures, or mock adapters.\n"
                "- If the task involves third-party services or private APIs where no credentials or endpoints are provided in the brief, specify modular mock implementations and offline test suites.\n"
                "- NEVER emit speculative, conditional, or blocked phases (e.g., 'Phase 5: authorized-source-integration-gate') that require unprovided credentials, live network access, or manual approvals. "
                "Document production prerequisites and future live integration gates exclusively in 'architecture_overview', NEVER as an ExecutionPhase.\n\n"
                "USER-FIRST DELIVERY & DOCUMENTATION MANDATE:\n"
                "- The final documentation/delivery phase MUST instruct creation of a project README.md designed for end-users with zero cognitive friction.\n"
                "- The README.md MUST include: (1) an intuitive visual architecture or data flow diagram (ASCII or Mermaid), (2) a zero-jargon, step-by-step Quickstart guide explaining exactly how to run or deploy the result in simple numbered steps, and (3) concrete examples.\n"
                "- If a project requires user-provided configuration (e.g. spreadsheet URLs, API tokens, column mappings, or database paths), DO NOT leave passive markdown questionnaires or expect raw JSON editing: mandate an interactive CLI setup script (e.g. 'scripts/setup.js' or 'setup.py') that guides the user interactively in plain English."
            ),
        )
        # --- BINDING TOOLS TO Taghi ---
        register_graph_tools(self.agent, self.graph_manager, "Taghi")
        register_note_writer_tool(
            self.agent,
            self.specs_dir,
            tool_name="write_specs_note",
            category="Specs",
            directory_name="Specs",
            agent_name="Taghi",
        )

    async def create_specification(self, task_id: str, research_summary: str, project_id: str | None = None) -> TechnicalSpec:
        print_agent("taghi", f"Designing technical architecture and roadmap for task: {task_id}")

        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", task_id):
            raise ValueError("Task ID must contain only letters, digits, underscores, or hyphens")
        project = prepare_project(self.vault_path, project_id)
        workspace_dir = project_id or task_id
        directory_instruction = f"Create your project directory at workspace/{workspace_dir}/ and place all modules there."
        prompt = (
            f"Task ID: {task_id}\n{project.prompt}Research Summary/Findings: {research_summary}\n\n"
            f"Include this instruction in the specification: {directory_instruction}\n"
            f"All sandbox commands start in /app/workspace/{workspace_dir}/. "
            "Keep source files, tests, documentation, validation scripts, and dependencies in this project directory. "
            "Write validation commands relative to this directory or using its absolute container path.\n"
            "Execution Rule: All phases in 'phases' must be actionable and fully verifiable offline within the container. "
            "Do NOT include conditional or blocked phases that depend on unprovided credentials or external authorization; "
            "place any unverified external prerequisites or live deployment notes in architecture_overview."
        )
        result = await self.agent.run(prompt)
        spec = result.output
        spec.task_id = task_id
        spec.project_id = project_id
        from tools.token_analytics import extract_usage

        spec.token_usage = extract_usage(result, model_name=str(self.model_name))
        spec.sanitize_executable_phases()
        spec.architecture_overview = f"{directory_instruction}\n\n{spec.architecture_overview}"

        timestamp = datetime.now().strftime("%Y-%m-%d")
        note_filename = self.specs_dir / f"spec-{task_id}.md"
        note_filename.parent.mkdir(parents=True, exist_ok=True)

        markdown_content = f"""---
id: "spec-{task_id}"
type: "technical-spec"
agent: "taghi"
task_id: "{task_id}"
{project.frontmatter}created_at: "{timestamp}"
links: ["[[research-{task_id}]]", "[[{task_id}-brief]]"]
---
# Technical Specification: {task_id}

{project.body}## Architecture Overview
{spec.architecture_overview}

## Required Dependencies
"""
        for dep in spec.required_dependencies:
            markdown_content += f"- {dep}\n"

        markdown_content += "\n## Phased Execution Roadmap\n"
        for phase in spec.phases:
            markdown_content += f"### Phase: {phase.phase_name}\n"
            markdown_content += f"- **Instructions:** {phase.instructions}\n"
            markdown_content += f"- **Validation Command:** `{phase.validation_command}`\n\n"

        note_filename.write_text(markdown_content, encoding="utf-8")
        print_agent("taghi", f"Saved technical specification to: {note_filename}")

        await update_vault_graph(self.graph_manager, note_filename)
        return spec
