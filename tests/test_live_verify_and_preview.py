from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from tools.live_verifier import (
    find_live_verification_script,
    run_live_verification,
)
from tools.ui_preview import (
    find_previewable_surfaces,
    is_port_in_use,
    find_available_port,
    start_preview_server,
)


def test_find_live_verification_script_python(tmp_path: Path) -> None:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir(parents=True)
    script_file = scripts_dir / "verify_live.py"
    script_file.write_text("print('ok')", encoding="utf-8")

    result = find_live_verification_script(tmp_path)
    assert result is not None
    script_type, cmd = result
    assert script_type == "python"
    assert cmd == [sys.executable, str(script_file)]


def test_find_live_verification_script_node(tmp_path: Path) -> None:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir(parents=True)
    script_file = scripts_dir / "verify.js"
    script_file.write_text("console.log('ok')", encoding="utf-8")

    result = find_live_verification_script(tmp_path)
    assert result is not None
    script_type, cmd = result
    assert script_type == "node"
    assert cmd == ["node", str(script_file)]


def test_find_live_verification_script_apps_script(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir(parents=True)
    gs_file = dist_dir / "Code.gs"
    gs_file.write_text("function testDirectSync() {}", encoding="utf-8")

    result = find_live_verification_script(tmp_path)
    assert result is not None
    script_type, cmd = result
    assert script_type == "apps_script"
    assert cmd == [str(gs_file)]


def test_find_live_verification_script_none(tmp_path: Path) -> None:
    assert find_live_verification_script(tmp_path) is None


def test_run_live_verification_missing_workspace(tmp_path: Path) -> None:
    res = run_live_verification("nonexistent-proj", workspace_root=tmp_path)
    assert res["success"] is False
    assert "Workspace directory not found" in res["error"]


def test_run_live_verification_missing_script(tmp_path: Path) -> None:
    proj_dir = tmp_path / "my-project"
    proj_dir.mkdir(parents=True)

    res = run_live_verification("my-project", workspace_root=tmp_path)
    assert res["success"] is False
    assert "No verification script found" in res["error"]


def test_run_live_verification_apps_script(tmp_path: Path) -> None:
    proj_dir = tmp_path / "apps-proj"
    dist_dir = proj_dir / "dist"
    dist_dir.mkdir(parents=True)
    (dist_dir / "Code.gs").write_text(
        "function testDirectSync() {}\nfunction createGoogleForm() {}",
        encoding="utf-8",
    )

    res = run_live_verification("apps-proj", workspace_root=tmp_path)
    assert res["success"] is True
    assert res["type"] == "apps_script"
    assert res["has_direct_sync"] is True
    assert res["has_form_creator"] is True


def test_run_live_verification_python_execution(tmp_path: Path) -> None:
    proj_dir = tmp_path / "live-proj"
    scripts_dir = proj_dir / "scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "verify_live.py").write_text(
        "import os\nprint('LIVE_PASS:' + os.environ.get('API_KEY', ''))\n",
        encoding="utf-8",
    )
    (proj_dir / ".env").write_text("API_KEY=secret_live_key\n", encoding="utf-8")

    res = run_live_verification("live-proj", workspace_root=tmp_path)
    assert res["success"] is True
    assert res["type"] == "python"
    assert res["returncode"] == 0
    assert "LIVE_PASS:secret_live_key" in res["stdout"]


def test_find_previewable_surfaces(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<h1>Index</h1>", encoding="utf-8")
    (tmp_path / "web-entry.html").write_text("<h1>Entry</h1>", encoding="utf-8")
    public_dir = tmp_path / "public"
    public_dir.mkdir()
    (public_dir / "portal.html").write_text("<h1>Portal</h1>", encoding="utf-8")

    surfaces = find_previewable_surfaces(tmp_path)
    assert "web-entry.html" in surfaces
    assert "index.html" in surfaces
    assert "public/portal.html" in surfaces


def test_start_preview_server_lifecycle(tmp_path: Path) -> None:
    proj_dir = tmp_path / "preview-proj"
    proj_dir.mkdir(parents=True)
    (proj_dir / "form.html").write_text("<h1>Form</h1>", encoding="utf-8")

    server, port, url = start_preview_server(
        "preview-proj",
        workspace_root=tmp_path,
        port=8900,
        open_browser=False,
        run_until_interrupted=False,
    )
    try:
        assert port >= 8900
        assert url.startswith(f"http://localhost:{port}/")
        assert "form.html" in url
    finally:
        server.server_close()


def test_main_cli_verify_dispatch() -> None:
    from main import main
    with patch("sys.argv", ["main.py", "--verify", "demo-proj"]):
        with patch("tools.live_verifier.run_live_verification") as mock_verify:
            mock_verify.return_value = {"success": True}
            asyncio.run(main())
            mock_verify.assert_called_once_with("demo-proj")


def test_main_cli_preview_dispatch() -> None:
    from main import main
    with patch("sys.argv", ["main.py", "--preview", "demo-proj", "--port", "9090"]):
        with patch("tools.ui_preview.start_preview_server") as mock_preview:
            asyncio.run(main())
            mock_preview.assert_called_once_with(
                project_id="demo-proj",
                port=9090,
                open_browser=False,
                run_until_interrupted=True,
            )

