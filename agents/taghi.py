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
                "- If a project requires user-provided configuration (e.g. spreadsheet URLs, API tokens, column mappings, or database paths), DO NOT leave passive markdown questionnaires or expect raw JSON editing: mandate an interactive CLI setup script (e.g. 'scripts/setup.js' or 'setup.py') that guides the user interactively in plain English.\n\n"
                "MANDATORY USER INPUT SURFACE & ENTRY POINT PHASE:\n"
                "- NEVER architect a 'headless receiver' or 'ghost pipeline' that assumes user data arrives from nowhere. "
                "  If the task involves workflows, form submissions, surveys, transaction inputs, or interactive tools, "
                "  you MUST dedicate an explicit execution phase to creating the concrete User Input Surface / Entry Point "
                "  (e.g. an automated form creator script, a lightweight HTML web form, or an interactive CLI input prompt). "
                "  The phases must build both the data receiver AND the actual input mechanism that a human or client uses to enter data.\n\n"
                "ARCHITECTURAL GRILL-ME & USER INTERFACE APPROVAL:\n"
                "- Always populate 'input_interface_spec' with the concrete layout/schema of the user entry interface "
                "  (e.g., list of form fields, data types, validation rules, dropdown options, or CLI prompt questions).\n"
                "- Formulate up to 10 targeted 'clarification_questions' (strictly <= 10) for the user to approve before coding. "
                "  Cover key architectural trade-offs: (1) field schema & column names, (2) UI/form structure and UX options, "
                "  (3) core libraries/frameworks, (4) failure modes & error handling, and (5) offline mock verification strategy. "
                "  Every question MUST provide 2 to 4 concrete numbered options with exactly one marked is_default=True representing your recommended architecture.\n\n"
                "TWO-TIER VERIFICATION ARCHITECTURE & SPECIFICATION MANDATE:\n"
                "1. Tier 1 (Automated Docker Validation):\n"
                "   - Phase 1 MUST define and build the concrete User Input Interface / Surface (e.g., Form generator, HTML web form, or CLI input script).\n"
                "   - All execution phases executed by Meti inside Docker MUST use deterministic unit tests, fixtures, and mock service adapters (e.g. mock SpreadsheetApp, mock REST API responses).\n"
                "   - Docker tests validate 100% offline with zero external network or secrets required.\n"
                "2. Tier 2 (Guided Live Environment Verification):\n"
                "   - Always populate 'live_verification_guide' with a clear, step-by-step checklist explaining how the user verifies against their real environment (e.g. Google Sheets, live webhooks, real database).\n"
                "   - Mandate in the final delivery phase that Meti builds a dedicated live smoke-test script (e.g. 'scripts/verify_live.py' or Apps Script 'testDirectSync()') and includes the Live Verification Checklist in the project README.md."
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
"""
        if getattr(spec, "input_interface_spec", None):
            markdown_content += f"\n## User Input Surface & Form Specification\n{spec.input_interface_spec}\n"

        if getattr(spec, "live_verification_guide", None):
            markdown_content += f"\n## Tier 2: Live Verification Guide\n{spec.live_verification_guide}\n"

        markdown_content += "\n## Required Dependencies\n"
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

    async def conduct_architectural_review(
        self,
        spec: TechnicalSpec,
        task_id: str,
        design_context: str,
        auto: bool = False,
        input_func: Any = None,
        project_id: str | None = None,
    ) -> tuple[TechnicalSpec, bool]:
        """
        Run Taghi's architectural grill interview and review approval gate before Meti implements.
        Returns: (approved_or_revised_spec, quit_requested)
        """
        from tools.grill import has_non_default_answers, run_grill_session, format_grill_answers_for_prompt
        from tools.ui import prompt_spec_approval_gate

        current_spec = spec
        while True:
            # Step 1: Run architectural grill questions if present
            if getattr(current_spec, "clarification_questions", None):
                answers, quit_requested = run_grill_session(
                    current_spec.clarification_questions,
                    agent_name="taghi",
                    title="🏛 Taghi Architecture & Schema Grill",
                    auto=auto,
                    input_func=input_func,
                    max_questions=10,
                )
                if quit_requested:
                    return current_spec, True

                if not auto and has_non_default_answers(current_spec.clarification_questions, answers):
                    formatted_decisions = format_grill_answers_for_prompt(answers, current_spec.clarification_questions)
                    updated_context = f"{design_context}\n\n{formatted_decisions}"
                    current_spec = await self.create_specification(task_id, updated_context, project_id=project_id)

            # Step 2: Present architectural review card and prompt for user approval
            action, feedback = prompt_spec_approval_gate(current_spec, auto=auto, input_func=input_func)
            if action == "quit":
                return current_spec, True
            elif action == "revise" and feedback:
                updated_context = f"{design_context}\n\nUser Architectural Revisions / Feedback:\n{feedback}"
                current_spec = await self.create_specification(task_id, updated_context, project_id=project_id)
            else:
                return current_spec, False
