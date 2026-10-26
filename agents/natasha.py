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

class NatashaRouter:
    def __init__(self, vault_path: str = "./vault", model_name: str | Model = "openai-chat:gpt-4o"):
        self.vault_path = Path(vault_path)
        self.tasks_dir = self.vault_path / "tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.graph_manager = GraphifyVaultManager(vault_path=str(self.vault_path))

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
        @self.agent.tool_plain
        def query_vault_knowledge(search_term: str) -> list[dict]:
            """
            Search the Obsidian vault graph for existing nodes, tasks, or past specs matching a term.
            """
            print(f"[Natasha Tool Called] Searching graph for: {search_term}")
            return self.graph_manager.query_nodes(search_term)

        @self.agent.tool_plain
        def get_related_notes(node_id: str) -> list[dict]:
            """
            Get direct neighbor connections for a specific note ID in the vault graph.
            """
            print(f"[Natasha Tool Called] Finding neighbors for node: {node_id}")
            return self.graph_manager.get_neighbors(node_id)
        
        @self.agent.tool_plain
        def write_task_note(filename: str, content: str) -> str:
            """
            Safely write a markdown task report into the vault/task directory.
            """
            root = self.tasks_dir.resolve()
            file_path = (root / filename).resolve()
            if not file_path.is_relative_to(root) or file_path == root or file_path.suffix.lower() != ".md":
                raise ValueError("Task notes must be Markdown files within the Task directory")
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            print(f"[Natasha Tool] Wrote note directly to vault: {file_path}")
            return f"Successfully saved note to {file_path}"

    async def coordinate_request(self, user_prompt: str, task_id: str, project_id: str | None = None) -> TaskBrief:
        print(f"[Natasha] Routing prompt for task {task_id}: '{user_prompt}'")
        
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", task_id):
            raise ValueError("Task ID must contain only letters, digits, underscores, or hyphens")
        project = prepare_project(self.vault_path, project_id)
        result = await self.agent.run(f"Task ID: {task_id}\n{project.prompt}User request: {user_prompt}")
        task_brief = result.output
        task_brief.task_id = task_id
        task_brief.project_id = project_id

        timestamp = datetime.now().strftime("%Y-%m-%d")
        note_filename = self.tasks_dir / f"{task_brief.task_id}-brief.md"
        
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
        print(f"[Natasha] Created master task note at: {note_filename}")

        if not await asyncio.to_thread(self.graph_manager.build_graph, incremental=True):
            print(f"[Graphify Warning] Note saved to {note_filename}, but graph update failed; continuing without updated graph context")
        return task_brief
