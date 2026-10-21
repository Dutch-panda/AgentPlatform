import asyncio
import re
from pathlib import Path
from datetime import datetime
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from tools.graphify_tool import GraphifyVaultManager

class ExecutionPhase(BaseModel):
    phase_name: str = Field(description="Name of phase, e.g., '1-database', '2-backend', '3-frontend', '4-qa'")
    instructions: str = Field(description="Detailed instructions and implementation requirements")
    validation_command: str = Field(description="Terminal command to validate this phase inside the container")

class TechnicalSpec(BaseModel):
    task_id: str
    architecture_overview: str
    required_dependencies: list[str]
    phases: list[ExecutionPhase] = Field(description="Ordered sequential phases for Meti to execute")

class TaghiArchitect:
    def __init__(self, vault_path: str = "./vault", model_name: str = "openai-chat:gpt-4o"):
        self.vault_path = Path(vault_path)
        self.specs_dir = self.vault_path / "specs"
        self.specs_dir.mkdir(parents=True, exist_ok=True)
        self.research_dir = self.vault_path / "research"
        self.research_dir.mkdir(parents=True, exist_ok=True)
        self.graph_manager = GraphifyVaultManager(vault_path=str(self.vault_path))

        self.agent = Agent(
            model_name,
            output_type=TechnicalSpec,
            system_prompt=(
                "You are Taghi, Technical Design Lead. Verify that the task is designated for design/architecture. "
                "Translate research reports into precise technical specifications and sequential execution phases for Meti."
            )
        )
        # --- BINDING TOOLS TO Taghi ---
        @self.agent.tool_plain
        def query_vault_knowledge(search_term: str) -> list[dict]:
            """
            Search the Obsidian vault graph for existing nodes, tasks, or past specs matching a term.
            """
            print(f"[Taghi Tool Called] Searching graph for: {search_term}")
            return self.graph_manager.query_nodes(search_term)

        @self.agent.tool_plain
        def get_related_notes(node_id: str) -> list[dict]:
            """
            Get direct neighbor connections for a specific note ID in the vault graph.
            """
            print(f"[Taghi Tool Called] Finding neighbors for node: {node_id}")
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
            print(f"[Taghi Tool] Wrote note directly to vault: {file_path}")
            return f"Successfully saved note to {file_path}"

    async def create_specification(self, task_id: str, research_summary: str) -> TechnicalSpec:
        print(f"[Taghi] Designing architecture and execution phases for task: {task_id}")

        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", task_id):
            raise ValueError("Task ID must contain only letters, digits, underscores, or hyphens")
        prompt = f"Task ID: {task_id}\nResearch Summary/Findings: {research_summary}"
        result = await self.agent.run(prompt)
        spec = result.output
        spec.task_id = task_id

        timestamp = datetime.now().strftime("%Y-%m-%d")
        note_filename = self.specs_dir / f"spec-{task_id}.md"

        markdown_content = f"""---
id: "spec-{task_id}"
type: "technical-spec"
agent: "taghi"
task_id: "{task_id}"
created_at: "{timestamp}"
links: ["[[research-{task_id}]]", "[[{task_id}-brief]]"]
---
# Technical Specification: {task_id}

## Architecture Overview
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
        print(f"[Taghi] Saved technical specification to: {note_filename}")

        if not await asyncio.to_thread(self.graph_manager.build_graph, incremental=True):
            raise RuntimeError(f"Note saved to {note_filename}, but graph update failed")
        return spec
