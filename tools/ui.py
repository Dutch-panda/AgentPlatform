"""Terminal UI and Rich styling helpers for BuildRelay."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterable

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
    detail_str = str(detail).strip()
    lines = detail_str.splitlines()

    if len(lines) > 1:
        # Check if the command is writing files (e.g. cat > file <<EOF or tee file)
        import re
        from pathlib import Path
        written_files = re.findall(
            r"(?:cat\s*>\s*|cat\s*<<['\"]?\w+['\"]?\s*>\s*|tee\s+)([^\s<>&|;'\"]+)",
            detail_str,
        )
        if written_files:
            file_names = [Path(f).name for f in written_files if Path(f).name]
            files_str = ", ".join(file_names[:3])
            if len(file_names) > 3:
                files_str += f" (+{len(file_names) - 3} more)"
            first_cmd = lines[0].strip()
            if first_cmd.startswith("mkdir"):
                summary = f"Scaffolding & writing {files_str} ({len(lines)} lines)"
            else:
                summary = f"Writing {files_str} ({len(lines)} lines)"
        else:
            first_line = lines[0].strip()
            summary = f"{first_line[:70]}... (+{len(lines) - 1} lines)"
    else:
        summary = detail_str[:100] + ("..." if len(detail_str) > 100 else "")

    console.print(f"   [dim]↳ \\[{escape(theme['name'])}\\] {escape(action)}: {escape(summary)}[/dim]")


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


def print_brief_summary(
    target_lead: str,
    questions: list[str],
    token_usage: dict[str, Any] | None = None,
    model: str | None = None,
) -> None:
    """Display Natasha's routing decision in a compact box."""
    lead_theme = _get_theme(target_lead)
    content = f"[bold]Assigned Lead:[/bold] [{lead_theme['color']}]{lead_theme['icon']} {lead_theme['name']} ({lead_theme['role']})[/]\n"
    if token_usage:
        from tools.token_analytics import format_token_badge

        content += f"[bold]Tokens Used:[/bold]   [yellow]{format_token_badge(token_usage, model)}[/yellow]\n"
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


def print_spec_summary(
    base_image: str | None,
    phases: list[Any],
    token_usage: dict[str, Any] | None = None,
    model: str | None = None,
) -> None:
    """Display Taghi's execution roadmap in a styled summary."""
    image = base_image or "node:18-bullseye-slim (default)"
    header = f"[bold]Runtime Image:[/bold] [cyan]{image}[/cyan]\n"
    if token_usage:
        from tools.token_analytics import format_token_badge

        header += f"[bold]Tokens Used:[/bold]   [yellow]{format_token_badge(token_usage, model)}[/yellow]\n"
    header += f"[bold]Execution Roadmap ({len(phases)} phases):[/bold]\n"
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


def print_token_summary_table(
    token_usage_dict: dict[str, dict[str, Any]],
    default_model: str | None = None,
) -> None:
    """Render a structured token usage and cost table broken down per lead."""
    from tools.token_analytics import calculate_token_cost

    table = Table(
        title="[bold #818cf8]Token Usage & Cost Summary[/bold #818cf8]",
        title_justify="left",
        border_style="dim",
        padding=(0, 1),
    )
    table.add_column("Lead", style="bold", min_width=18)
    table.add_column("Prompt Tokens", justify="right", min_width=16)
    table.add_column("Completion Tokens", justify="right", min_width=18)
    table.add_column("Total Tokens", justify="right", min_width=14)
    table.add_column("Est. Cost", justify="right", min_width=14)

    total_prompt = 0
    total_completion = 0
    total_tokens = 0
    total_cost: float = 0.0
    all_numeric_cost = True

    lead_order = ["natasha", "odin", "taghi", "meti"]
    for k in token_usage_dict:
        if k not in lead_order:
            lead_order.append(k)

    for lead_key in lead_order:
        usage = token_usage_dict.get(lead_key)
        if not usage:
            continue
        theme = _get_theme(lead_key)
        lead_label = f"[{theme['color']}]{theme['icon']} {theme['name']}[/]"

        inp = usage.get("input_tokens", 0)
        out = usage.get("output_tokens", 0)
        tot = usage.get("total_tokens", inp + out)
        model = usage.get("model") or default_model

        cost_val, cost_display = calculate_token_cost(inp, out, model)
        if cost_val is not None:
            total_cost += cost_val
        else:
            all_numeric_cost = False

        total_prompt += inp
        total_completion += out
        total_tokens += tot

        table.add_row(
            lead_label,
            f"{inp:,}",
            f"{out:,}",
            f"{tot:,}",
            f"[green]{cost_display}[/green]" if "$" in cost_display else f"[dim]{cost_display}[/dim]",
        )

    if total_tokens > 0:
        table.add_section()
        if all_numeric_cost:
            total_cost_str = f"${total_cost:.4f}" if total_cost < 0.001 else f"${total_cost:.3f}"
        else:
            total_cost_str = "--"
        table.add_row(
            "[bold white]Total[/bold white]",
            f"[bold]{total_prompt:,}[/bold]",
            f"[bold]{total_completion:,}[/bold]",
            f"[bold yellow]{total_tokens:,}[/bold yellow]",
            f"[bold green]{total_cost_str}[/bold green]"
            if "$" in total_cost_str
            else f"[bold dim]{total_cost_str}[/bold dim]",
        )

    console.print()
    console.print(table)
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


def print_alignment_brief(brief: Any) -> None:
    """Render the 5-sentence structured Task Alignment Brief panel."""
    ab = getattr(brief, "alignment_brief", None)
    if not ab:
        return

    lines = ab.to_lines() if hasattr(ab, "to_lines") else []
    if not lines and isinstance(ab, dict):
        lines = [
            ("1. Goal:", ab.get("goal", "")),
            ("2. Features:", ab.get("core_features", "")),
            ("3. Stack:", ab.get("tech_stack", "")),
            ("4. Exclusions:", ab.get("exclusions", "")),
            ("5. Next Steps:", ab.get("next_actions", "")),
        ]

    content_lines = []
    for label, val in lines:
        content_lines.append(f"[bold #38bdf8]{label:<15}[/bold #38bdf8] {escape(val)}")

    panel = Panel(
        "\n".join(content_lines),
        title="[bold #d946ef]🎯 Task Alignment Brief[/bold #d946ef]",
        title_align="left",
        border_style="#d946ef",
        padding=(1, 2),
    )
    console.print()
    console.print(panel)


def prompt_alignment_gate(
    brief: Any,
    auto: bool = False,
    input_func: Callable[[str], str] | None = None,
) -> tuple[str, str | None, dict[str, str]]:
    """
    Present the 5-sentence brief and any clarification questions.
    Returns: (action, feedback_text, selected_answers)
      action: 'confirm' | 'edit' | 'quit'
    """
    import sys

    # Always render the alignment brief panel
    print_alignment_brief(brief)

    # Collect default answers
    questions = getattr(brief, "clarification_questions", []) or []
    answers: dict[str, str] = {}
    for q in questions:
        for opt in getattr(q, "options", []):
            if getattr(opt, "is_default", False):
                answers[getattr(q, "id", str(q))] = getattr(opt, "label", getattr(opt, "key", ""))
                break

    # If headless / automated / non-interactive: automatically proceed with defaults
    ask = input_func or input
    if auto or (input_func is None and not sys.stdin.isatty()):
        return "confirm", None, answers

    # Render clarification questions if present
    if questions:
        console.print(
            "[bold yellow]⚡ Clarification Questions[/bold yellow] [dim](Press Enter to accept defaults):[/dim]"
        )
        for idx, q in enumerate(questions, start=1):
            q_text = getattr(q, "question", str(q))
            console.print(f"  [bold cyan]{idx}. {escape(q_text)}[/bold cyan]")
            for opt in getattr(q, "options", []):
                key = getattr(opt, "key", "")
                lbl = getattr(opt, "label", "")
                is_def = getattr(opt, "is_default", False)
                def_tag = " [bold green](Default)[/bold green]" if is_def else ""
                console.print(f"     [bold cyan]\\[{escape(str(key))}][/bold cyan] {escape(lbl)}{def_tag}")
        console.print()

    console.print(
        "[bold]👉 Action:[/bold] "
        "[green]\\[Y/enter][/green] Confirm Defaults  |  "
        "[cyan]\\[1, 2...][/cyan] Pick Option  |  "
        "[yellow]\\[e][/yellow] Edit / Custom  |  "
        "[red]\\[q][/red] Quit"
    )
    try:
        user_choice = ask("> ").strip()
    except (EOFError, KeyboardInterrupt):
        return "quit", None, {}

    low = user_choice.lower()
    if low in ("", "y", "yes"):
        return "confirm", None, answers
    if low in ("q", "quit", "exit"):
        return "quit", None, {}
    if low in ("e", "edit"):
        try:
            feedback = ask("📝 Describe intent changes / clarifications: ").strip()
            return "edit", feedback or "User requested intent review.", answers
        except (EOFError, KeyboardInterrupt):
            return "quit", None, {}

    # Check if user typed a specific option number / key (e.g. "2" or "b")
    matched_opt = None
    matched_q = None
    for q in questions:
        for opt in getattr(q, "options", []):
            if str(getattr(opt, "key", "")).strip().lower() == low:
                matched_opt = opt
                matched_q = q
                break
        if matched_opt:
            break

    if matched_opt and matched_q:
        opt_key = getattr(matched_opt, "key", user_choice)
        opt_label = getattr(matched_opt, "label", "")
        q_id = getattr(matched_q, "id", str(matched_q))
        q_text = getattr(matched_q, "question", "requirement")
        answers[q_id] = opt_label
        console.print(f"   [bold green]✔ Selected option \\[{opt_key}]: {escape(opt_label)}[/bold green]")
        feedback = f"Selected option [{opt_key}] {opt_label} for '{q_text}'."
        return "edit", feedback, answers

    # Freeform user input treated as modification/clarification
    console.print(f"   [dim]↳ Applying modification: {escape(user_choice)}[/dim]")
    return "edit", user_choice, answers


def prompt_step_gate(
    stage_name: str,
    summary_text: str,
    auto: bool = False,
    input_func: Callable[[str], str] | None = None,
) -> tuple[str, str | None]:
    """
    Step gate confirmation for --step mode before executing a lead.
    Returns: ('confirm' | 'pivot' | 'quit', feedback_text)
    """
    import sys

    theme = _get_theme(stage_name)
    panel = Panel(
        summary_text.strip(),
        title=f"[{theme['color']}]{theme['icon']} Step Gate: {theme['name']} ({theme['role']})[/{theme['color']}]",
        title_align="left",
        border_style=theme["color"].split()[-1] if " " in theme["color"] else theme["color"],
        padding=(1, 2),
    )
    console.print()
    console.print(panel)

    ask = input_func or input
    if auto or (input_func is None and not sys.stdin.isatty()):
        return "confirm", None

    console.print(
        f"[bold]Proceed to {theme['name']}?[/bold] [green]\\[Y/enter][/green] Proceed  |  "
        f"[yellow]\\[e][/yellow] Pivot / Re-route  |  [red]\\[q][/red] Abort"
    )
    try:
        choice = ask("> ").strip()
    except (EOFError, KeyboardInterrupt):
        return "quit", None

    low = choice.lower()
    if low in ("", "y", "yes"):
        return "confirm", None
    if low in ("q", "quit", "exit"):
        return "quit", None
    if low in ("e", "edit", "pivot"):
        try:
            feedback = ask("📝 Describe intent pivot: ").strip()
            return "pivot", feedback
        except (EOFError, KeyboardInterrupt):
            return "quit", None

    return "pivot", choice


def prompt_delivery_gate(
    task_id: str,
    workspace_path: Path,
    summary_text: str,
    auto: bool = False,
    input_func: Callable[[str], str] | None = None,
) -> tuple[str, str | None]:
    """
    Delivery review gate after Meti validates all phases, before final completion.
    Returns: ('confirm' | 'refine' | 'quit', feedback_text)
    """
    import sys

    theme = _get_theme("meti")
    rel_ws = str(workspace_path)
    try:
        rel_ws = str(workspace_path.relative_to(Path.cwd()))
    except ValueError:
        pass

    content = (
        f"[bold white]📦 Deliverables Ready in:[/bold white] [cyan]{escape(rel_ws)}[/cyan]\n"
        f"[bold white]🎯 Implementation Summary:[/bold white] {escape(summary_text)}\n\n"
        "[dim]Review the generated files and instructions. If you would like simpler guides, "
        "visual charts, or code refinements, request them now before final delivery.[/dim]"
    )

    panel = Panel(
        content.strip(),
        title=f"[{theme['color']}]{theme['icon']} Meti Delivery Review: {escape(task_id)}[/{theme['color']}]",
        title_align="left",
        border_style="green",
        padding=(1, 2),
    )
    console.print()
    console.print(panel)

    ask = input_func or input
    if auto or (input_func is None and not sys.stdin.isatty()):
        return "confirm", None

    console.print(
        "[bold]👉 Delivery Action:[/bold] "
        "[green]\\[Y/enter][/green] Accept & Complete  |  "
        "[yellow]\\[r][/yellow] Request Refinement (Docs/Code)  |  "
        "[red]\\[q][/red] Quit"
    )
    try:
        choice = ask("> ").strip()
    except (EOFError, KeyboardInterrupt):
        return "quit", None

    low = choice.lower()
    if low in ("", "y", "yes"):
        return "confirm", None
    if low in ("q", "quit", "exit"):
        return "quit", None
    if low in ("r", "refine", "edit", "e"):
        try:
            feedback = ask("📝 Describe refinements needed (e.g. clearer README, beginner guide, specific fixes):\n> ").strip()
            return "refine", feedback or "User requested documentation and usability refinement."
        except (EOFError, KeyboardInterrupt):
            return "quit", None

    # Freeform text typed directly at prompt
    console.print(f"   [dim]↳ Requesting refinement: {escape(choice)}[/dim]")
    return "refine", choice


def print_model_lineup_card(
    models: dict[str, Any],
    tier: str = "balanced",
    prompt_caching: bool = True,
    budget_estimate: str | None = None,
) -> None:
    """Render a clean card displaying the pipeline model lineup across all leads."""
    from tools.model_tiers import get_tier_label

    content_lines = []
    leads = [
        ("natasha", "Natasha"),
        ("taghi", "Taghi"),
        ("odin", "Odin"),
        ("meti", "Meti"),
    ]

    for left_lead, right_lead in [(leads[0], leads[1]), (leads[2], leads[3])]:
        t_left = _get_theme(left_lead[0])
        t_right = _get_theme(right_lead[0])
        mdl_left = models.get(left_lead[0], "gpt-4o")
        mdl_right = models.get(right_lead[0], "gpt-4o")
        lbl_left = get_tier_label(mdl_left)
        lbl_right = get_tier_label(mdl_right)

        str_left = f"[{t_left['color']}]{t_left['icon']} {t_left['name']}:[/{t_left['color']}] [white]{escape(str(mdl_left))}[/white] [dim]({lbl_left})[/dim]"
        str_right = f"[{t_right['color']}]{t_right['icon']} {t_right['name']}:[/{t_right['color']}] [white]{escape(str(mdl_right))}[/white] [dim]({lbl_right})[/dim]"
        content_lines.append(f"{str_left:<42}  {str_right}")

    footer = f"\n[bold cyan]Tier:[/bold cyan] {tier.title()}  |  [bold yellow]Prompt Caching:[/bold yellow] {'Enabled (prefix match)' if prompt_caching else 'Disabled'}"
    if budget_estimate:
        footer += f"  |  [bold green]Est. Budget:[/bold green] {budget_estimate}"
    content_lines.append(footer)

    panel = Panel(
        "\n".join(content_lines),
        title="[bold #818cf8]⚙ Pipeline Model Configuration[/bold #818cf8]",
        title_align="left",
        border_style="#818cf8",
        padding=(1, 2),
    )
    console.print()
    console.print(panel)


def prompt_model_approval_gate(
    models: dict[str, Any],
    tier: str = "balanced",
    auto: bool = False,
    input_func: Callable[[str], str] | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """
    Prompt user for confirmation of the model lineup and cost tier before execution.
    Returns: ('confirm' | 'change' | 'quit', resolved_models)
    """
    import sys
    from tools.model_tiers import estimate_pipeline_budget, resolve_pipeline_models

    _, budget_str = estimate_pipeline_budget(models)
    print_model_lineup_card(models, tier=tier, prompt_caching=True, budget_estimate=budget_str)

    ask = input_func or input
    if auto or (input_func is None and not sys.stdin.isatty()):
        return "confirm", models

    console.print(
        "[bold]Proceed with this model lineup?[/bold] [green][Y/enter][/green] Proceed  |  "
        "[yellow][c][/yellow] Change Lineup/Tier  |  [red][q][/red] Abort"
    )
    try:
        choice = ask("> ").strip()
    except (EOFError, KeyboardInterrupt):
        return "quit", None

    low = choice.lower()
    if low in ("", "y", "yes"):
        return "confirm", models
    if low in ("q", "quit", "exit"):
        return "quit", None
    if low in ("c", "change"):
        from tools.model_tiers import (
            get_available_models_for_active_provider,
            get_tier_label,
            resolve_pipeline_models,
        )

        provider_name, available_models = get_available_models_for_active_provider()
        console.print(f"\n[bold cyan]Dynamic Model Selection ({provider_name}):[/bold cyan]")
        for idx, m in enumerate(available_models, start=1):
            lbl = get_tier_label(m)
            is_active = any(str(v).endswith(m) or str(v) == m for v in models.values())
            active_tag = " [green](Active)[/green]" if is_active else ""
            console.print(f"  [{idx}] {m} [dim]({lbl})[/dim]{active_tag}")

        fast_example = available_models[3] if len(available_models) > 3 else available_models[-1]
        console.print(f"  [f] Fast Tier ({fast_example} across leads)")
        console.print(f"  [b] Balanced Tier (Fast Router/Search + Reasoning Architect/Implementer)")
        console.print(f"  [p] Powerful Tier (Frontier reasoning/coding across leads)")
        console.print(f"  [m] Custom model name")

        try:
            choice_input = ask(f"Select Model [1-{len(available_models)}] or Tier [f/b/p/m]: ").strip().lower()
            if choice_input.isdigit():
                idx = int(choice_input) - 1
                if 0 <= idx < len(available_models):
                    selected_model = available_models[idx]
                    return "change", resolve_pipeline_models(global_model=selected_model)
            elif choice_input in ("f", "fast"):
                return "change", resolve_pipeline_models(tier="fast")
            elif choice_input in ("b", "balanced"):
                return "change", resolve_pipeline_models(tier="balanced")
            elif choice_input in ("p", "powerful"):
                return "change", resolve_pipeline_models(tier="powerful")
            elif choice_input in ("m", "custom"):
                custom = ask("Enter model (e.g. gpt-5.5, gpt-6, claude-3-5-sonnet): ").strip()
                if custom:
                    return "change", resolve_pipeline_models(global_model=custom)
            return "confirm", models
        except (EOFError, KeyboardInterrupt):
            return "quit", None

    return "confirm", models

