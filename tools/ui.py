"""Terminal UI and Rich styling helpers for BuildRelay."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

console = Console(highlight=False)

AGENT_THEMES: dict[str, dict[str, str]] = {
    "natasha": {"name": "Natasha", "color": "bold #d946ef", "icon": "🟣", "role": "Coordinator"},
    "odin": {"name": "Odin", "color": "bold #06b6d4", "icon": "🔵", "role": "Researcher"},
    "taghi": {"name": "Taghi", "color": "bold #22c55e", "icon": "🟢", "role": "Architect"},
    "meti": {"name": "Meti", "color": "bold #ffa76c", "icon": "🟠", "role": "Implementer"},
    "docker": {"name": "Docker", "color": "bold #38bdf8", "icon": "🐳", "role": "Sandbox"},
    "orchestrator": {"name": "BuildRelay", "color": "bold #818cf8", "icon": "⚡", "role": "System"},
    "resume": {"name": "Resume", "color": "bold #eab308", "icon": "🔄", "role": "Recovery"},
}


def _get_theme(agent_key: str) -> dict[str, str]:
    normalized = agent_key.lower().strip()
    return AGENT_THEMES.get(
        normalized,
        {"name": agent_key, "color": "bold white", "icon": "•", "role": "Agent"},
    )


def print_agent(agent: str, message: str, detail: str | None = None) -> None:
    """Print a role-badged message with agent icon and color."""
    theme = _get_theme(agent)
    console.print(f"[{theme['color']}]{theme['icon']} \\[{escape(theme['name'])}\\][/] {escape(message)}")
    if detail:
        console.print(f"   [dim]{escape(detail)}[/dim]")


def print_tool_call(agent: str, action: str, detail: str) -> None:
    """Print a subtle, dimmed tool invocation line to prevent clutter."""
    theme = _get_theme(agent)
    console.print(f"   [dim]↳ \\[{escape(theme['name'])}\\] {escape(action)}: {escape(detail)}[/dim]")


@contextmanager
def agent_status(agent: str, message: str):
    """Display an animated spinner with the agent's role icon and theme."""
    theme = _get_theme(agent)
    status_text = f"[{theme['color']}]{theme['icon']} [{escape(theme['name'])}][/] {escape(message)}"
    status = console.status(status_text, spinner="dots")
    status.start()
    try:
        yield status
    finally:
        status.stop()


def print_task_header(
    task_id: str, prompt: str, project_id: str | None = None, is_resume: bool = False
) -> None:
    """Render a clean launch or resume header panel."""
    title = "🔄 BuildRelay — Task Resume" if is_resume else "⚡ BuildRelay — Task Launch"
    border_style = "#eab308" if is_resume else "#ffa76c"

    lines = [f"[bold]Task ID:[/bold]  [cyan]{task_id}[/cyan]"]
    if project_id:
        lines.append(f"[bold]Project:[/bold]  [green]{project_id}[/green]")
    lines.append(f"[bold]Prompt:[/bold]   {prompt}")

    panel = Panel(
        "\n".join(lines),
        title=f"[bold]{title}[/bold]",
        title_align="left",
        border_style=border_style,
        padding=(1, 2),
    )
    console.print()
    console.print(panel)


def print_brief_summary(target_lead: str, questions: list[str]) -> None:
    """Display Natasha's routing decision in a compact box."""
    lead_theme = _get_theme(target_lead)
    content = f"[bold]Assigned Lead:[/bold] [{lead_theme['color']}]{lead_theme['icon']} {lead_theme['name']} ({lead_theme['role']})[/]\n"
    if questions:
        content += "[bold]Key Questions:[/bold]\n" + "\n".join(f"  • [dim]{q}[/dim]" for q in questions)
    console.print(
        Panel(
            content.strip(),
            title="[bold magenta]🟣 Task Brief & Routing[/bold magenta]",
            title_align="left",
            border_style="#d946ef",
            padding=(0, 2),
        )
    )


def print_spec_summary(base_image: str | None, phases: list[Any]) -> None:
    """Display Taghi's execution roadmap in a styled summary."""
    image = base_image or "node:18-bullseye-slim (default)"
    header = f"[bold]Runtime Image:[/bold] [cyan]{image}[/cyan]\n[bold]Execution Roadmap ({len(phases)} phases):[/bold]\n"
    phase_lines = []
    for idx, phase in enumerate(phases, start=1):
        name = getattr(phase, "phase_name", str(phase))
        cmd = getattr(phase, "validation_command", "")
        phase_lines.append(f"  [green]{idx}.[/green] [bold]{name}[/bold] [dim]→ `{cmd}`[/dim]")
    content = header + "\n".join(phase_lines)
    console.print(
        Panel(
            content.strip(),
            title="[bold green]🟢 Technical Architecture & Roadmap[/bold green]",
            title_align="left",
            border_style="#22c55e",
            padding=(0, 2),
        )
    )


def print_phase_table(
    phases: list[Any],
    completed_phases: Iterable[str] = (),
    current_phase: str | None = None,
    failed_phase: str | None = None,
) -> None:
    """Render a structured status table for all execution phases."""
    table = Table(
        title="[bold #ffa76c]Execution & Validation Phases[/bold #ffa76c]",
        title_justify="left",
        border_style="dim",
        padding=(0, 1),
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Phase", style="bold", min_width=20)
    table.add_column("Validation Command", style="cyan", min_width=30)
    table.add_column("Status", justify="center", width=14)

    completed_set = set(completed_phases)
    for idx, phase in enumerate(phases, start=1):
        name = getattr(phase, "phase_name", str(phase))
        cmd = getattr(phase, "validation_command", "")

        if name in completed_set:
            status = "[bold green]✓ PASSED[/bold green]"
        elif name == failed_phase:
            status = "[bold red]✗ FAILED[/bold red]"
        elif name == current_phase:
            status = "[bold yellow]RUNNING[/bold yellow]"
        else:
            status = "[dim]PENDING[/dim]"

        table.add_row(str(idx), name, cmd, status)

    console.print()
    console.print(table)
    console.print()


def print_completion(task_id: str, success: bool, summary: str) -> None:
    """Render the final outcome panel with resume hints if failed."""
    if success:
        panel = Panel(
            f"[bold green]✓ All phases validated successfully![/bold green]\n\n{summary}",
            title=f"[bold green]⚡ Workflow Completed — {task_id}[/bold green]",
            title_align="left",
            border_style="green",
            padding=(1, 2),
        )
    else:
        panel = Panel(
            f"[bold red]✗ Workflow did not complete successfully.[/bold red]\n\n"
            f"{summary}\n\n"
            f"[bold yellow]To resume from saved checkpoints:[/bold yellow]\n"
            f"  [cyan]python main.py --resume {task_id}[/cyan]",
            title=f"[bold red]⚡ Workflow Incomplete — {task_id}[/bold red]",
            title_align="left",
            border_style="red",
            padding=(1, 2),
        )
    console.print()
    console.print(panel)
    console.print()


def print_workspace_tree(workspace_path: str | Path, max_depth: int = 3) -> None:
    """Print a formatted rich.tree.Tree of all generated project files."""
    path = Path(workspace_path)
    if not path.exists():
        return

    tree = Tree(f"[bold blue]📁 {path.name}/[/bold blue]")
    ignore_dirs = {
        ".git",
        "__pycache__",
        ".pytest_cache",
        ".venv",
        ".mypy_cache",
        ".ruff_cache",
        "node_modules",
        ".DS_Store",
    }

    def _build_tree(current_dir: Path, current_node: Tree, depth: int) -> None:
        if depth > max_depth:
            current_node.add("[dim]... (truncated)[/dim]")
            return

        try:
            entries = sorted(current_dir.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except Exception:
            return

        for entry in entries:
            if entry.name in ignore_dirs or entry.name.startswith("."):
                continue
            if entry.is_dir():
                sub_node = current_node.add(f"[bold #38bdf8]📁 {entry.name}/[/bold #38bdf8]")
                _build_tree(entry, sub_node, depth + 1)
            else:
                current_node.add(f"[white]📄 {entry.name}[/white]")

    _build_tree(path, tree, depth=1)
    console.print(tree)
    console.print()


def print_how_to_run(
    workspace_path: str | Path,
    run_cmd: str | None = None,
    test_cmd: str | None = None,
    entry_point: str | None = None,
) -> None:
    """Render a prominent Rich banner showing how to run and test the project."""
    path = Path(workspace_path)

    # Auto-detect test command if not provided
    if test_cmd is None:
        if (path / "package.json").exists():
            test_cmd = "npm test"
        elif (path / "Cargo.toml").exists():
            test_cmd = "cargo test"
        elif (path / "go.mod").exists():
            test_cmd = "go test ./..."
        else:
            test_cmd = "pytest"

    # Auto-detect run command and entry point if not provided
    if run_cmd is None:
        if (path / "package.json").exists():
            run_cmd = "npm start"
            entry_point = entry_point or "index.js"
        elif (path / "Cargo.toml").exists():
            run_cmd = "cargo run"
            entry_point = entry_point or "src/main.rs"
        elif (path / "go.mod").exists():
            run_cmd = "go run ."
            entry_point = entry_point or "main.go"
        elif (path / "src" / "main.py").exists():
            run_cmd = "python -m src.main"
            entry_point = entry_point or "src/main.py"
        elif (path / "main.py").exists():
            run_cmd = "python main.py"
            entry_point = entry_point or "main.py"
        elif (path / "app.py").exists():
            run_cmd = "python app.py"
            entry_point = entry_point or "app.py"
        else:
            run_cmd = f"python main.py"
            entry_point = entry_point or "main.py"

    content_lines = [
        f"[bold]Workspace:[/bold]  [cyan]{path}[/cyan]",
        f"[bold]Run:[/bold]        [green]{run_cmd}[/green]",
        f"[bold]Test:[/bold]       [yellow]{test_cmd}[/yellow]",
    ]
    if entry_point:
        content_lines.append(f"[bold]Entry:[/bold]      [magenta]{entry_point}[/magenta]")

    panel = Panel(
        "\n".join(content_lines),
        title="[bold green]🚀 How to Run & Test[/bold green]",
        title_align="left",
        border_style="#22c55e",
        padding=(1, 2),
    )
    console.print(panel)
    console.print()
