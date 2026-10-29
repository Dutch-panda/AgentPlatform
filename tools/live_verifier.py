"""Tier 2 Live Verification runner for real-environment testing."""

from __future__ import annotations

import os
import sys
import time
import subprocess
from pathlib import Path
from typing import Any

from rich.panel import Panel
from rich.markup import escape

from tools.ui import console
from tools.project_notes import get_project_env, validate_project_id


def find_live_verification_script(workspace_path: Path) -> tuple[str, list[str]] | None:
    """Detect available Tier 2 live verification scripts in the workspace."""
    scripts_dir = workspace_path / "scripts"

    if (scripts_dir / "verify_live.py").is_file():
        return "python", [sys.executable, str(scripts_dir / "verify_live.py")]
    if (scripts_dir / "verify.py").is_file():
        return "python", [sys.executable, str(scripts_dir / "verify.py")]
    if (workspace_path / "verify_live.py").is_file():
        return "python", [sys.executable, str(workspace_path / "verify_live.py")]
    if (scripts_dir / "verify.js").is_file():
        return "node", ["node", str(scripts_dir / "verify.js")]
    if (scripts_dir / "verify_live.sh").is_file():
        return "bash", ["bash", str(scripts_dir / "verify_live.sh")]
    if (workspace_path / "dist" / "Code.gs").is_file():
        return "apps_script", [str(workspace_path / "dist" / "Code.gs")]

    return None


def run_live_verification(
    project_id: str,
    workspace_root: Path | str = "workspace",
    env_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Execute the Tier 2 live verification smoke test for a project with real credentials.

    Args:
        project_id: Project identifier.
        workspace_root: Workspace directory root.
        env_overrides: Optional environment variable overrides.

    Returns:
        dict containing result status, output, command, and diagnostics.
    """
    validate_project_id(project_id)
    ws_dir = (Path(workspace_root).resolve() / project_id)

    if not ws_dir.is_dir():
        console.print(f"[bold red]Error:[/bold red] Project workspace not found at {escape(str(ws_dir))}")
        return {"success": False, "error": "Workspace directory not found"}

    # Load local project secrets
    project_env = get_project_env(project_id, workspace_root=workspace_root)
    if env_overrides:
        project_env.update(env_overrides)

    exec_env = os.environ.copy()
    exec_env.update(project_env)

    script_info = find_live_verification_script(ws_dir)
    if not script_info:
        console.print(f"[yellow]No live smoke test script found in {escape(str(ws_dir))}.[/yellow]")
        console.print("[dim]Expected one of: scripts/verify_live.py, scripts/verify.js, scripts/verify_live.sh, dist/Code.gs[/dim]")
        return {"success": False, "error": "No verification script found"}

    script_type, cmd = script_info

    # Google Apps Script handled with guided live steps
    if script_type == "apps_script":
        code_gs_content = Path(cmd[0]).read_text(encoding="utf-8", errors="ignore")
        has_direct_sync = "testDirectSync" in code_gs_content
        has_form_creator = "createGoogleForm" in code_gs_content

        instructions = [
            f"[bold white]Google Apps Script Engine:[/bold white] [cyan]{escape(cmd[0])}[/cyan]",
            "",
            "[bold white]Guided Live Verification Steps:[/bold white]",
        ]
        if has_direct_sync:
            instructions.append("  1. Open your Google Sheet script editor ([dim]Extensions > Apps Script[/dim]).")
            instructions.append("  2. Select [bold cyan]'testDirectSync'[/bold cyan] from the toolbar function dropdown and click [green]Run[/green].")
            instructions.append("  3. Check the Execution Log and verify that a test row was appended to your spreadsheet.")
        if has_form_creator:
            instructions.append("  4. To generate an input form, select [bold cyan]'createGoogleForm'[/bold cyan] and click [green]Run[/green].")
            instructions.append("  5. Copy the generated public Google Form link from the log to begin live submissions.")

        panel = Panel(
            "\n".join(instructions),
            title="[bold green]🧪 Tier 2: Google Apps Script Live Verification Guide[/bold green]",
            title_align="left",
            border_style="green",
            padding=(1, 2),
        )
        console.print()
        console.print(panel)
        return {
            "success": True,
            "type": "apps_script",
            "has_direct_sync": has_direct_sync,
            "has_form_creator": has_form_creator,
        }

    # Running local executable smoke test on host with loaded credentials
    console.print(f"\n[bold]🧪 Running Tier 2 Live Verification:[/bold] [cyan]{escape(' '.join(cmd))}[/cyan]")
    console.print(f"[dim]Working directory: {escape(str(ws_dir))}[/dim]\n")

    start_time = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ws_dir),
            env=exec_env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        elapsed = time.time() - start_time
        success = proc.returncode == 0

        border_style = "green" if success else "red"
        status_label = "[bold green]PASS[/bold green]" if success else f"[bold red]FAIL (exit {proc.returncode})[/bold red]"

        output_text = proc.stdout.strip() or proc.stderr.strip() or "(No console output)"
        panel_content = (
            f"[bold white]Status:[/bold white]        {status_label}\n"
            f"[bold white]Duration:[/bold white]      {elapsed:.2f}s\n"
            f"[bold white]Command:[/bold white]       [cyan]{escape(' '.join(cmd))}[/cyan]\n\n"
            f"[bold white]Output Log:[/bold white]\n{escape(output_text)}"
        )

        console.print(
            Panel(
                panel_content,
                title="[bold]🧪 Tier 2: Live Smoke Verification Result[/bold]",
                title_align="left",
                border_style=border_style,
                padding=(1, 2),
            )
        )

        return {
            "success": success,
            "type": script_type,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "duration": elapsed,
        }

    except subprocess.TimeoutExpired:
        console.print("[bold red]Live verification timed out after 60 seconds.[/bold red]")
        return {"success": False, "error": "Verification timed out"}
    except Exception as err:
        console.print(f"[bold red]Verification execution failed:[/bold red] {escape(str(err))}")
        return {"success": False, "error": str(err)}
