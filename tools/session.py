"""Interactive Project REPL & Workspace Memory Session for BuildRelay."""

from __future__ import annotations

import os
import sys
import asyncio
from pathlib import Path
from typing import Any, Callable

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.markup import escape

from tools.ui import _get_theme, console, print_agent
from tools.project_notes import (
    get_project_env,
    init_project_workspace,
    load_project_profile,
    prepare_project,
    set_project_env,
    validate_project_id,
)


def print_session_banner(project_id: str, workspace_path: Path) -> None:
    """Render the interactive project session launch banner."""
    rel_path = workspace_path
    try:
        rel_path = workspace_path.relative_to(Path.cwd())
    except ValueError:
        pass

    content = (
        f"[bold white]Project ID:[/bold white]   [green]{escape(project_id)}[/green]\n"
        f"[bold white]Workspace:[/bold white]    [cyan]{escape(str(rel_path))}[/cyan]\n"
        f"[bold white]Memory Note:[/bold white]  [yellow]{escape(str(rel_path / 'PROJECT_PROFILE.md'))}[/yellow]\n"
        f"[bold white]Local Env:[/bold white]    [dim]{escape(str(rel_path / '.env'))} (gitignored secrets)[/dim]\n\n"
        "[bold white]Session Commands:[/bold white]\n"
        "  [cyan]/profile[/cyan]      View active data schema, input interface, and task history\n"
        "  [cyan]/env[/cyan]          View or configure project-specific credentials & IDs\n"
        "  [cyan]/test[/cyan]         Execute local tests or Tier 2 verification in this workspace\n"
        "  [cyan]/help[/cyan]         Show available commands\n"
        "  [cyan]/exit[/cyan]         Exit session [dim](or Ctrl+D / quit)[/dim]\n\n"
        "[dim]Enter any prompt or revision instruction to plan, architect, and execute within this project.[/dim]"
    )
    panel = Panel(
        content.strip(),
        title="[bold #38bdf8]🔄 BuildRelay — Interactive Project Session[/bold #38bdf8]",
        title_align="left",
        border_style="#38bdf8",
        padding=(1, 2),
    )
    console.print()
    console.print(panel)


def mask_secret(value: str) -> str:
    """Mask sensitive string values, revealing only first 4 and last 2 characters."""
    if len(value) <= 6:
        return "******"
    return value[:4] + "*" * (len(value) - 6) + value[-2:]


async def run_project_session(
    project_id: str,
    vault_path: Path | str = "./vault",
    workspace_root: Path | str = "workspace",
    model: str | None = None,
    tier: str | None = None,
    auto: bool = False,
    step: bool = False,
    input_func: Callable[[str], str] | None = None,
    task_runner: Callable[..., Any] | None = None,
) -> None:
    """
    Launch a continuous interactive REPL session rooted in a project workspace.

    Args:
        project_id: Validated project identifier.
        vault_path: Path to the Obsidian vault directory.
        workspace_root: Root workspace folder containing project directories.
        model: Global model override.
        tier: Model tier preset ('fast', 'balanced', 'powerful').
        auto: Whether to run sub-tasks in headless mode.
        step: Whether to enforce step gates between agent handoffs.
        input_func: Optional input function for testability.
        task_runner: Optional callable to execute tasks (defaults to main.run_task).
    """
    validate_project_id(project_id)
    vault_path_obj = Path(vault_path)
    ws_dir, profile_path = init_project_workspace(project_id, workspace_root=workspace_root)
    prepare_project(vault_path_obj, project_id, workspace_root=workspace_root)

    ask = input_func or input
    print_session_banner(project_id, ws_dir)

    while True:
        try:
            prompt_str = f"[{project_id}] > "
            user_input = ask(prompt_str).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Exiting project session. Progress saved.[/yellow]")
            break

        if not user_input:
            continue

        cmd = user_input.lower()

        # Exit
        if cmd in ("/exit", "/quit", "exit", "quit", ":q"):
            console.print("[green]Session ended. Project memory preserved.[/green]")
            break

        # Help
        if cmd in ("/help", "help"):
            print_session_banner(project_id, ws_dir)
            continue

        # Profile / Schema inspection
        if cmd in ("/profile", "profile"):
            profile_text = load_project_profile(project_id, workspace_root=workspace_root)
            if profile_text:
                console.print()
                console.print(Panel(Markdown(profile_text), title=f"[bold green]PROJECT_PROFILE.md ({project_id})[/bold green]", border_style="green", padding=(1, 2)))
            else:
                console.print(f"[yellow]No profile found for {project_id}.[/yellow]")
            continue

        # Environment & Secrets inspection / management
        if cmd in ("/env", "env"):
            env_vars = get_project_env(project_id, workspace_root=workspace_root)
            console.print(f"\n[bold white]🔐 Project Secrets & Configurations ([cyan]{escape(str(ws_dir / '.env'))}[/cyan]):[/bold white]")
            if not env_vars:
                console.print("  [dim](No project-specific variables defined yet)[/dim]")
            else:
                for k, v in env_vars.items():
                    masked = mask_secret(v)
                    console.print(f"  • [cyan]{escape(k)}[/cyan] = [yellow]{escape(masked)}[/yellow]")

            console.print("\n[dim]To add or update a variable, type `NAME=value` (or press Enter to return):[/dim]")
            try:
                env_input = ask("  > ").strip()
                if "=" in env_input:
                    k, v = env_input.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k:
                        set_project_env(project_id, k, v, workspace_root=workspace_root)
                        console.print(f"  [bold green]✔ Saved {escape(k)} to project .env[/bold green]")
            except (EOFError, KeyboardInterrupt):
                pass
            continue

        # Test command
        if cmd in ("/test", "test"):
            console.print(f"\n[bold]Running verification tests for [cyan]{project_id}[/cyan]...[/bold]")
            test_cmd = None
            if (ws_dir / "package.json").exists():
                test_cmd = f"cd {ws_dir} && npm test"
            elif (ws_dir / "scripts" / "verify_live.py").exists():
                test_cmd = f"python {ws_dir / 'scripts' / 'verify_live.py'}"
            else:
                test_cmd = f".venv/bin/pytest {ws_dir} || pytest {ws_dir}"

            ret = os.system(test_cmd)
            status_text = "[bold green]PASS[/bold green]" if ret == 0 else "[bold red]FAIL[/bold red]"
            console.print(f"Test run completed: {status_text}\n")
            continue

        # Task Execution in Project Context
        console.print(f"\n[bold magenta]⚡ Executing task in project context: '{escape(user_input)}'[/bold magenta]")
        
        # Lazy load main components if task_runner not provided
        if task_runner is None:
            from main import run_task, task_id_for
            from tools.task_ledger import TaskLedger, TaskRecord

            ledger = TaskLedger()
            task_id = task_id_for(user_input, ledger=ledger)
            with ledger.claim(task_id):
                record = TaskRecord(task_id=task_id, prompt=user_input, project_id=project_id)
                ledger.create(record)
                try:
                    res = await run_task(
                        record=record,
                        ledger=ledger,
                        model_override=model,
                        tier=tier,
                        auto=auto,
                        step=step,
                    )
                    console.print(f"[bold green]✔ Task {task_id} completed: {escape(res.summary)}[/bold green]\n")
                except Exception as err:
                    console.print(f"[bold red]❌ Task failed: {escape(str(err))}[/bold red]\n")
        else:
            try:
                res = task_runner(project_id, user_input)
                if asyncio.iscoroutine(res):
                    await res
                console.print(f"[bold green]✔ Task completed successfully.[/bold green]\n")
            except Exception as err:
                console.print(f"[bold red]❌ Task failed: {escape(str(err))}[/bold red]\n")
