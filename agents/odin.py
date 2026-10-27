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
from tools.ui import print_agent


@dataclass
class ResearchContext:
    retrieved_nodes: list[dict] = field(default_factory=list)
    web_sources: list[dict[str, str]] = field(default_factory=list)
    search_calls_count: int = 0
    

class OdinResearcher:
    def __init__(
        self,
        vault_path: str | Path = "./vault",
        model_name: str | Model = "openai-chat:gpt-4o",
        graph_manager: GraphifyVaultManager | None = None,
        research_dir: str | Path | None = None,
    ):
        self.vault_path = Path(vault_path)
        self.model_name = model_name
        self.research_dir = Path(research_dir) if research_dir is not None else self.vault_path / "research"
        self.graph_manager = graph_manager or GraphifyVaultManager(vault_path=str(self.vault_path))

        # Initialize Pydantic AI Agent
        self.agent = Agent(
            model_name,
            output_type=ResearchReport,
            deps_type=ResearchContext,
            model_settings={"cache": True},
            system_prompt=(
                "You are Odin, the Research Lead. You have access to vault graph tools and web documentation tools.\n"
                "1. Use vault graph tools to query related historical context from the project notes.\n"
                "2. If the user request involves third-party packages, new frameworks, or modern API signatures, "
                "   use 'search_technical_documentation' or 'verify_package_ecosystem' to research current libraries.\n"
                "3. Keep search queries specific and focused on technical requirements (e.g. 'fastapi pydantic v2 migration').\n"
                "4. Graph and web results are automatically cited by the platform; do not invent source links."
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

        @self.agent.tool
        def search_technical_documentation(ctx: RunContext[ResearchContext], query: str) -> str:
            """Search the web for technical documentation, library signatures, or framework guides."""
            from tools.ui import print_tool_call
            print_tool_call("Odin", "search_technical_documentation", f"query='{query}'")
            if ctx.deps.search_calls_count >= 3:
                return "Search budget reached (maximum 3 web searches per task). Synthesize findings from retrieved information."
            ctx.deps.search_calls_count += 1

            from tools.web_search import search_web
            results = search_web(query, max_results=3)
            if not results:
                return f"No external documentation found for '{query}' (offline or empty results)."

            lines = []
            for r in results:
                ctx.deps.web_sources.append({"title": r.title, "url": r.url, "snippet": r.snippet})
                lines.append(f"- **[{r.title}]({r.url})**: {r.snippet}")
            return "\n".join(lines)

        @self.agent.tool
        def verify_package_ecosystem(ctx: RunContext[ResearchContext], package_name: str, ecosystem: str = "pypi") -> str:
            """Verify whether a package exists in the official PyPI or npm registry to prevent hallucinated dependencies."""
            from tools.ui import print_tool_call
            print_tool_call("Odin", "verify_package_ecosystem", f"pkg='{package_name}' ({ecosystem})")
            from tools.web_search import verify_package
            info = verify_package(package_name, ecosystem=ecosystem)
            if info.get("exists"):
                return f"Package '{info.get('name')}' is verified on {ecosystem}. Latest version: {info.get('version')}. Summary: {info.get('summary')}"
            return f"Package '{package_name}' was NOT found on {ecosystem}: {info.get('error')}"

    async def conduct_research(self, task_id: str, objective: str, project_id: str | None = None) -> ResearchReport:
        print_agent("odin", f"Conducting vault research for task: {task_id}")
        
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", task_id):
            raise ValueError("Task ID must contain only letters, digits, underscores, or hyphens")
        project = prepare_project(self.vault_path, project_id)
        # Double-check task assignment from vault brief if needed
        graph_context = await asyncio.to_thread(self.graph_manager.query_nodes, task_id)
        context = ResearchContext(retrieved_nodes=list(graph_context))
        from tools.context_pruner import prune_graph_context
        pruned_graph = prune_graph_context(objective, graph_context, max_items=5)
        prompt = f"Task ID: {task_id}\n{project.prompt}Objective: {objective}\nVault Context:\n{pruned_graph}"
        
        result = await self.agent.run(prompt, deps=context)
        report = result.output
        report.task_id = task_id
        report.project_id = project_id
        from tools.token_analytics import extract_usage

        report.token_usage = extract_usage(result, model_name=str(self.model_name))
        report.vault_sources = self.graph_manager.resolve_note_sources(context.retrieved_nodes)
        report.web_sources = getattr(context, "web_sources", [])

        timestamp = datetime.now().strftime("%Y-%m-%d")
        note_filename = self.research_dir / f"research-{task_id}.md"
        note_filename.parent.mkdir(parents=True, exist_ok=True)
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

        markdown_content += "\n## External web documentation & sources\n"
        if report.web_sources:
            for src in report.web_sources:
                markdown_content += f"- [{src['title']}]({src['url']}): {src.get('snippet', '')}\n"
        else:
            markdown_content += "\nNo external web documentation was queried for this task.\n"

        note_filename.write_text(markdown_content, encoding="utf-8")
        print_agent("odin", f"Saved research report to: {note_filename}")

        await update_vault_graph(self.graph_manager, note_filename)
        return report
