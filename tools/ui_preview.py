"""Local Web Preview server for generated user input surfaces and forms."""

from __future__ import annotations

import functools
import http.server
import socket
import threading
import webbrowser
from pathlib import Path
from typing import Any

from rich.panel import Panel
from rich.markup import escape

from tools.ui import console
from tools.project_notes import validate_project_id


def find_previewable_surfaces(workspace_path: Path) -> list[str]:
    """Discover available user entry HTML files in the project workspace."""
    surfaces: list[str] = []
    preferred = ["form.html", "web-entry.html", "index.html"]

    for name in preferred:
        if (workspace_path / name).is_file():
            surfaces.append(name)

    # Search root and public/ for any additional HTML files
    for p in workspace_path.glob("*.html"):
        if p.name not in surfaces:
            surfaces.append(p.name)

    public_dir = workspace_path / "public"
    if public_dir.is_dir():
        for p in public_dir.glob("*.html"):
            surfaces.append(f"public/{p.name}")

    return surfaces


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a local port is already bound."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0


def find_available_port(start_port: int = 8080, max_attempts: int = 20) -> int:
    """Find the first available port starting from start_port."""
    for p in range(start_port, start_port + max_attempts):
        if not is_port_in_use(p):
            return p
    # Fallback to ephemeral port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def start_preview_server(
    project_id: str,
    workspace_root: Path | str = "workspace",
    port: int = 8080,
    open_browser: bool = False,
    run_until_interrupted: bool = True,
) -> tuple[Any, int, str]:
    """
    Launch a local HTTP preview server rooted in the project's workspace directory.

    Args:
        project_id: Project identifier.
        workspace_root: Workspace root directory.
        port: Preferred port (finds next free port if occupied).
        open_browser: Automatically open the browser to the primary entry surface.
        run_until_interrupted: Run blocking server loop until Ctrl+C / Enter.

    Returns:
        tuple (server_instance, port_used, primary_url)
    """
    validate_project_id(project_id)
    ws_dir = (Path(workspace_root).resolve() / project_id)

    if not ws_dir.is_dir():
        console.print(f"[bold red]Error:[/bold red] Project workspace not found at {escape(str(ws_dir))}")
        raise FileNotFoundError(f"Workspace directory not found: {ws_dir}")

    surfaces = find_previewable_surfaces(ws_dir)
    target_port = find_available_port(port)

    # Use standard library SimpleHTTPRequestHandler serving ws_dir
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler,
        directory=str(ws_dir),
    )

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", target_port), handler)
    base_url = f"http://localhost:{target_port}/"

    # Identify primary URL
    primary_surface = surfaces[0] if surfaces else None
    primary_url = f"{base_url}{primary_surface}" if primary_surface else base_url

    surface_lines = []
    if surfaces:
        for s in surfaces:
            surface_lines.append(f"  • [cyan]{base_url}{s}[/cyan]")
    else:
        surface_lines.append(f"  • [dim]No HTML form detected yet; serving directory listing at {base_url}[/dim]")

    panel_content = (
        f"[bold white]Project:[/bold white]          [green]{escape(project_id)}[/green]\n"
        f"[bold white]Workspace:[/bold white]        [dim]{escape(str(ws_dir))}[/dim]\n"
        f"[bold white]Base URL:[/bold white]         [bold cyan]{base_url}[/bold cyan]\n\n"
        f"[bold white]Available Input Surfaces & Pages:[/bold white]\n"
        + "\n".join(surface_lines) + "\n\n"
        "[dim]Press [yellow]Ctrl+C[/yellow] or [yellow]Enter[/yellow] in terminal to stop preview server.[/dim]"
    )

    console.print()
    console.print(
        Panel(
            panel_content,
            title="[bold #38bdf8]🌐 BuildRelay — Local UI & Input Preview[/bold #38bdf8]",
            title_align="left",
            border_style="#38bdf8",
            padding=(1, 2),
        )
    )

    if open_browser:
        try:
            webbrowser.open(primary_url)
        except Exception:
            pass

    if not run_until_interrupted:
        # Non-blocking: caller manages server
        return httpd, target_port, primary_url

    # Blocking interactive loop
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()

    try:
        input("\n[BuildRelay] > Press Enter to stop the preview server... ")
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        httpd.shutdown()
        httpd.server_close()
        console.print("[yellow]Preview server stopped.[/yellow]\n")

    return httpd, target_port, primary_url
