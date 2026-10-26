import asyncio
import re
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
from urllib.parse import quote
from pydantic_ai import Agent, RunContext
from pydantic_ai.models import Model
from contracts import ResearchReport
from tools.graphify_tool import GraphifyVaultManager
from tools.project_notes import prepare_project
from tools.vault_infra import (
    register_note_writer_tool,
    register_provenance_graph_tools,
    update_vault_graph,
)


@dataclass
class ResearchContext:
    retrieved_nodes: list[dict] = field(default_factory=list)
    

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
            deps_type=ResearchContext,
            system_prompt=(
                "You are Odin, the Research Lead. You have access to vault graph tools. "
                "Use them to query related concepts and their relationships before writing your final research report. "
                "Graph results are historical context, not independently verified facts or full note contents. "
                "The application records resolved source notes automatically; do not invent source paths."
            )
        )

        # --- BINDING TOOLS TO Odin ---
        register_provenance_graph_tools(self.agent, self.graph_manager, "Odin")
        register_note_writer_tool(
            self.agent,
            self.research_dir,
            tool_name="write_research_note",
            category="Research",
            directory_name="research",
            agent_name="Odin",
        )

    async def conduct_research(self, task_id: str, objective: str, project_id: str | None = None) -> ResearchReport:
        print(f"[Odin] Checking task brief and conducting research for: {task_id}")
        
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", task_id):
            raise ValueError("Task ID must contain only letters, digits, underscores, or hyphens")
        project = prepare_project(self.vault_path, project_id)
        # Double-check task assignment from vault brief if needed
        graph_context = await asyncio.to_thread(self.graph_manager.query_nodes, task_id)
        context = ResearchContext(retrieved_nodes=list(graph_context))
        prompt = f"Task ID: {task_id}\n{project.prompt}Objective: {objective}\nVault Context: {graph_context}"
        
        result = await self.agent.run(prompt, deps=context)
        report = result.output
        report.task_id = task_id
        report.project_id = project_id
        report.vault_sources = self.graph_manager.resolve_note_sources(context.retrieved_nodes)

        timestamp = datetime.now().strftime("%Y-%m-%d")
        note_filename = self.research_dir / f"research-{task_id}.md"
        source_links = [f"[[{Path(source).with_suffix('').as_posix()}]]" for source in report.vault_sources]
        links = json.dumps([f"[[{task_id}-brief]]", *source_links], ensure_ascii=False)

        markdown_content = f"""---
id: "research-{task_id}"
type: "research-report"
agent: "odin"
task_id: "{task_id}"
{project.frontmatter}created_at: "{timestamp}"
links: {links}
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

        markdown_content += "\n## Related vault sources\n"
        if report.vault_sources:
            markdown_content += "\nSource notes resolved from retrieved graph context; these are not claim-level citations or evidence that full notes were read.\n\n"
            for source in report.vault_sources:
                path = self.vault_path / source
                relative = Path(os.path.relpath(path, note_filename.parent)).as_posix()
                label = source.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]").replace("\n", " ").replace("\r", " ")
                markdown_content += f"- [{label}]({quote(relative, safe='/')})\n"
        else:
            markdown_content += "\nNo source notes could be resolved from the retrieved graph context.\n"

        note_filename.write_text(markdown_content, encoding="utf-8")
        print(f"[Odin] Saved research report to: {note_filename}")

        await update_vault_graph(self.graph_manager, note_filename)
        return report
