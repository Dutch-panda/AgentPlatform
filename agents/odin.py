import asyncio
import re
from pathlib import Path
from datetime import datetime
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models import Model
from tools.graphify_tool import GraphifyVaultManager
from tools.project_notes import prepare_project

class ResearchReport(BaseModel):
    task_id: str
    project_id: str | None = Field(default=None, description="Parent project ID supplied by the caller; null for standalone tasks")
    summary: str = Field(description="Executive summary of research findings")
    key_findings: list[str] = Field(description="Bullet points of technical insights or architectural approaches")
    recommended_stack: list[str] = Field(description="Recommended technologies or packages to use")
    

class OdinResearcher:
    def __init__(self, vault_path: str = "./vault", model_name: str | Model = "openai-chat:gpt-4o"):
        self.vault_path = Path(vault_path)
        self.research_dir = self.vault_path / "research"
        self.research_dir.mkdir(parents=True, exist_ok=True)
        self.graph_manager = GraphifyVaultManager(vault_path=str(self.vault_path))

        # Initialize Pydantic AI Agent
        self.agent = Agent(
            model_name,
            output_type=ResearchReport,
            system_prompt=(
                "You are Odin, the Research Lead. You have access to vault graph tools. "
                "Use them to query related concepts before writing your final research report."
            )
        )

        # --- BINDING TOOLS TO Odin ---
        @self.agent.tool_plain
        def query_vault_knowledge(search_term: str) -> list[dict]:
            """
            Search the Obsidian vault graph for existing nodes, tasks, or past specs matching a term.
            """
            print(f"[Odin Tool Called] Searching graph for: {search_term}")
            return self.graph_manager.query_nodes(search_term)

        @self.agent.tool_plain
        def get_related_notes(node_id: str) -> list[dict]:
            """
            Get direct neighbor connections for a specific note ID in the vault graph.
            """
            print(f"[Odin Tool Called] Finding neighbors for node: {node_id}")
            return self.graph_manager.get_neighbors(node_id)
        
        @self.agent.tool_plain
        def write_research_note(filename: str, content: str) -> str:
            """
            Safely write a markdown research report into the vault/research directory.
            """
            root = self.research_dir.resolve()
            file_path = (root / filename).resolve()
            if not file_path.is_relative_to(root) or file_path == root or file_path.suffix.lower() != ".md":
                raise ValueError("Research notes must be Markdown files within the research directory")
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            print(f"[Odin Tool] Wrote note directly to vault: {file_path}")
            return f"Successfully saved note to {file_path}"

    async def conduct_research(self, task_id: str, objective: str, project_id: str | None = None) -> ResearchReport:
        print(f"[Odin] Checking task brief and conducting research for: {task_id}")
        
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", task_id):
            raise ValueError("Task ID must contain only letters, digits, underscores, or hyphens")
        project = prepare_project(self.vault_path, project_id)
        # Double-check task assignment from vault brief if needed
        graph_context = await asyncio.to_thread(self.graph_manager.query_nodes, task_id)
        prompt = f"Task ID: {task_id}\n{project.prompt}Objective: {objective}\nVault Context: {graph_context}"
        
        result = await self.agent.run(prompt)
        report = result.output
        report.task_id = task_id
        report.project_id = project_id

        timestamp = datetime.now().strftime("%Y-%m-%d")
        note_filename = self.research_dir / f"research-{task_id}.md"

        markdown_content = f"""---
id: "research-{task_id}"
type: "research-report"
agent: "odin"
task_id: "{task_id}"
{project.frontmatter}created_at: "{timestamp}"
links: ["[[{task_id}-brief]]"]
---
# Research Report: {task_id}

{project.body}## Executive Summary
{report.summary}

## Key Findings
"""
        for finding in report.key_findings:
            markdown_content += f"- {finding}\n"

        markdown_content += "\n## Recommended Stack\n"
        for item in report.recommended_stack:
            markdown_content += f"- {item}\n"

        note_filename.write_text(markdown_content, encoding="utf-8")
        print(f"[Odin] Saved research report to: {note_filename}")

        if not await asyncio.to_thread(self.graph_manager.build_graph, incremental=True):
            print(f"[Graphify Warning] Note saved to {note_filename}, but graph update failed; continuing without updated graph context")
        return report
