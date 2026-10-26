import asyncio
import re
import uuid
from typing import Literal
from pathlib import Path
from datetime import datetime
from pydantic_ai import Agent
from pydantic_ai.models import Model
from contracts import TaskBrief
from tools.graphify_tool import GraphifyVaultManager
from tools.project_notes import prepare_project
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
        self.tasks_dir = Path(tasks_dir) if tasks_dir is not None else self.vault_path / "tasks"
        self.graph_manager = graph_manager or GraphifyVaultManager(vault_path=str(self.vault_path))

        self.agent = Agent(
            model_name,
            output_type=TaskBrief,
            system_prompt=(
                "You are Natasha, the master coordinator and router of an elite multi-agent engineering team. "
                "Analyze the user's request, break it down into a structured task brief, "
                "and formulate core research questions. Decide "
                "which lead ('odin', 'taghi', or 'meti') the task is designated for."
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

    async def coordinate_request(self, user_prompt: str, task_id: str, project_id: str | None = None) -> TaskBrief:
        print_agent("natasha", f"Analyzing and routing task: '{user_prompt}'")
        
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", task_id):
            raise ValueError("Task ID must contain only letters, digits, underscores, or hyphens")
        project = prepare_project(self.vault_path, project_id)
        result = await self.agent.run(f"Task ID: {task_id}\n{project.prompt}User request: {user_prompt}")
        task_brief = result.output
        task_brief.task_id = task_id
        task_brief.project_id = project_id

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

        note_filename.write_text(markdown_content, encoding="utf-8")
        print_agent("natasha", f"Created master task note at: {note_filename}")

        await update_vault_graph(self.graph_manager, note_filename)
        return task_brief
