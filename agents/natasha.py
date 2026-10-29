import asyncio
import re
import uuid
from typing import Literal
from pathlib import Path
from datetime import datetime
from pydantic_ai import Agent
from pydantic_ai.models import Model
from contracts import AlignmentBrief, ClarificationOption, ClarificationQuestion, TaskBrief
from tools.graphify_tool import GraphifyVaultManager
from tools.project_notes import ProjectContext, prepare_project
from tools.vault_infra import (
    register_graph_tools,
    register_note_writer_tool,
    update_vault_graph,
)
from tools.ui import print_agent

class NatashaRouter:
    def __init__(
        self,
        vault_path: str | Path = "./vault",
        model_name: str | Model = "openai-chat:gpt-4o",
        graph_manager: GraphifyVaultManager | None = None,
        tasks_dir: str | Path | None = None,
    ):
        self.vault_path = Path(vault_path)
        self.model_name = model_name
        self.tasks_dir = Path(tasks_dir) if tasks_dir is not None else self.vault_path / "tasks"
        self.graph_manager = graph_manager or GraphifyVaultManager(vault_path=str(self.vault_path))

        self.agent = Agent(
            model_name,
            output_type=TaskBrief,
            model_settings={"cache": True},
            system_prompt=(
                "You are Natasha, the master coordinator and router of an elite multi-agent engineering team. "
                "Analyze the user's request, break it down into a structured task brief, "
                "and formulate core research questions. Decide "
                "which lead ('odin', 'taghi', or 'meti') the task is designated for. "
                "Always generate a concise, semantic kebab-case slug (2-4 core words, omitting stop words like 'build', 'create', 'a', 'the').\n\n"
                "INTENT ALIGNMENT & GRILL-ME INTERVIEW RULES:\n"
                "1. Always populate 'alignment_brief' with exactly 5 structured sentences:\n"
                "   - goal: Exactly what is being built.\n"
                "   - core_features: Key functionality included in scope.\n"
                "   - tech_stack: Frameworks, databases, and container runtime image.\n"
                "   - exclusions: Explicitly state what is deferred or intentionally omitted.\n"
                "   - next_actions: State the designated next lead and their first deliverable.\n"
                "2. Conduct an active 'Grill-Me' alignment interview by generating targeted 'clarification_questions' (up to 10 questions, strictly <= 10). "
                "   Focus on establishing shared vocabulary, clarifying business objectives, data schemas/fields, operational triggers, "
                "   failure modes, and user entry points. Categorize each question (e.g. category='User Input', 'Schema', 'Operational Scope', or 'Edge Cases'). "
                "   Every question MUST provide 2 to 4 concrete numbered options with exactly one marked is_default=True representing your recommended choice.\n\n"
                "USER INPUT SURFACE & ENTRY POINT MANDATE:\n"
                "- When the user's request involves data ingestion, workflows, forms, surveys, CLI utilities, or interactive apps, "
                "  you MUST explicitly define the Entry Point / Input Surface in 'alignment_brief' (under goal or core_features). "
                "  Declare whether the project will generate an input form/UI (e.g. automated Google Form builder script, web form, or interactive CLI), "
                "  or connect to an external source. Never frame an app as a headless receiver without specifying how a human or client enters data.\n"
                "- If the input mechanism is ambiguous (e.g. user mentions 'form responses' but not where the form comes from), "
                "  include a clarification question asking whether to generate a new entry form/UI or connect an existing form."
            )
        )
        # --- BINDING TOOLS TO Natasha ---
        register_graph_tools(self.agent, self.graph_manager, "Natasha")
        register_note_writer_tool(
            self.agent,
            self.tasks_dir,
            tool_name="write_task_note",
            category="Task",
            directory_name="Task",
            agent_name="Natasha",
        )

        @self.agent.tool_plain
        def lookup_technology(query: str) -> str:
            """Look up official library names or technology options when clarifying task briefs."""
            from tools.ui import print_tool_call
            print_tool_call("Natasha", "lookup_technology", f"query='{query}'")
            from tools.web_search import search_web
            results = search_web(query, max_results=2)
            if not results:
                return f"No documentation found for '{query}'."
            return "\n".join(f"- {r.title}: {r.snippet}" for r in results)

    async def coordinate_request(self, user_prompt: str, task_id: str, project_id: str | None = None) -> TaskBrief:
        print_agent("natasha", f"Analyzing and routing task: '{user_prompt}'")
        
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", task_id):
            raise ValueError("Task ID must contain only letters, digits, underscores, or hyphens")
        project = prepare_project(self.vault_path, project_id)
        result = await self.agent.run(f"Task ID: {task_id}\n{project.prompt}User request: {user_prompt}")
        task_brief = result.output
        task_brief.task_id = task_id
        task_brief.project_id = project_id
        from tools.token_analytics import extract_usage

        task_brief.token_usage = extract_usage(result, model_name=str(self.model_name))
        self._ensure_alignment_brief(task_brief, user_prompt)

        await self._write_brief_note(task_brief, project)
        return task_brief

    def _ensure_alignment_brief(self, brief: TaskBrief, prompt: str) -> None:
        """Ensure alignment_brief is populated with 5 structured sentences."""
        if not brief.alignment_brief:
            target = brief.target_lead.capitalize()
            brief.alignment_brief = AlignmentBrief(
                goal=brief.title or prompt[:60],
                core_features=brief.objective[:120] if brief.objective else prompt,
                tech_stack="Python 3.11 / container environment",
                exclusions="Production cloud infrastructure and external credentials deferred to local mocks.",
                next_actions=f"{target} lead initiates {'deep investigation' if target == 'Odin' else 'architecture specification'}.",
            )
        elif isinstance(brief.alignment_brief, dict):
            brief.alignment_brief = AlignmentBrief.model_validate(brief.alignment_brief)

    async def realign_intent(
        self,
        previous_brief: TaskBrief,
        user_feedback: str,
        project_id: str | None = None,
    ) -> TaskBrief:
        """Re-align Natasha's task brief when the user clarifies or pivots their intent."""
        print_agent("natasha", f"Re-aligning intent based on user feedback: '{user_feedback}'")
        project = prepare_project(self.vault_path, project_id or previous_brief.project_id)
        pivot_prompt = (
            f"Original Task ID: {previous_brief.task_id}\n"
            f"Original Goal: {previous_brief.title}\n"
            f"Original Scope: {previous_brief.objective}\n"
            f"{project.prompt}"
            f"User Feedback / Intent Pivot: {user_feedback}\n"
            "Please revise the task brief, re-evaluate target lead, update the 5-sentence alignment brief, "
            "and update clarification questions."
        )
        result = await self.agent.run(pivot_prompt)
        new_brief = result.output
        new_brief.task_id = previous_brief.task_id
        new_brief.project_id = previous_brief.project_id
        from tools.token_analytics import extract_usage

        new_brief.token_usage = extract_usage(result, model_name=str(self.model_name))
        self._ensure_alignment_brief(new_brief, user_feedback)
        await self._write_brief_note(new_brief, project)
        return new_brief

    async def conduct_grill_session(
        self,
        brief: TaskBrief,
        auto: bool = False,
        input_func: Any = None,
        project_id: str | None = None,
    ) -> tuple[TaskBrief, bool]:
        """Run Natasha's interactive grill-me alignment interview and realign intent if selections change."""
        from tools.grill import has_non_default_answers, run_grill_session, format_grill_answers_for_prompt

        if not brief.clarification_questions:
            return brief, False

        answers, quit_requested = run_grill_session(
            brief.clarification_questions,
            agent_name="natasha",
            title="🎯 Natasha Intent & Operational Scope Grill",
            auto=auto,
            input_func=input_func,
            max_questions=10,
        )
        if quit_requested:
            return brief, True

        if not auto and has_non_default_answers(brief.clarification_questions, answers):
            formatted_decisions = format_grill_answers_for_prompt(answers, brief.clarification_questions)
            realigned_brief = await self.realign_intent(brief, formatted_decisions, project_id=project_id)
            return realigned_brief, False

        return brief, False

    async def _write_brief_note(self, task_brief: TaskBrief, project: ProjectContext) -> Path:
        timestamp = datetime.now().strftime("%Y-%m-%d")
        note_filename = self.tasks_dir / f"{task_brief.task_id}-brief.md"
        note_filename.parent.mkdir(parents=True, exist_ok=True)

        markdown_content = f"""---
id: "{task_brief.task_id}"
type: "task-brief"
agent: "natasha"
target_lead: "{task_brief.target_lead}"
{project.frontmatter}created_at: "{timestamp}"
links: []
---
# Task: {task_brief.title}

{project.body}## Assignment
- **Target Lead:** {task_brief.target_lead.upper()}

## Objective
{task_brief.objective}

## Scope & Questions
"""
        for q in task_brief.research_questions:
            markdown_content += f"- {q}\n"

        if task_brief.alignment_brief:
            ab = task_brief.alignment_brief
            lines = ab.to_lines() if hasattr(ab, "to_lines") else []
            if lines:
                markdown_content += "\n## Alignment Brief (5-Sentence Summary)\n"
                for label, val in lines:
                    markdown_content += f"- **{label}** {val}\n"

        note_filename.write_text(markdown_content, encoding="utf-8")
        print_agent("natasha", f"Created master task note at: {note_filename}")

        await update_vault_graph(self.graph_manager, note_filename)
        return note_filename
