"""Unit tests for Phase 2: User Input Interface contract & Two-Tier Validation."""

from pathlib import Path
import pytest
from contracts import ClarificationQuestion, ExecutionPhase, TechnicalSpec
from agents.taghi import TaghiArchitect
from agents.meti import MetiImplementer
from tools.ui import (
    print_how_to_run,
    print_spec_proposal_card,
    prompt_delivery_gate,
)


def test_spec_two_tier_verification_contract():
    spec = TechnicalSpec(
        task_id="task-tier2-contract",
        architecture_overview="Hybrid Google Workspace automation",
        required_dependencies=["npm:@google/clasp"],
        base_image="node:18-bullseye-slim",
        phases=[
            ExecutionPhase(
                phase_name="1-user-form",
                instructions="Build Google Form auto-creation script",
                validation_command="node scripts/test_form.js",
            ),
            ExecutionPhase(
                phase_name="2-backend-sync",
                instructions="Build transaction mapper with local mocks",
                validation_command="node scripts/test_sync.js",
            ),
        ],
        input_interface_spec="Google Form with fields: Date (Date), Amount (Number), Category (Choice), Description (Text)",
        live_verification_guide="1. Open Apps Script editor\n2. Run testDirectSync() to sync test transaction\n3. Confirm row in Google Sheet",
    )

    assert spec.input_interface_spec is not None
    assert "Date (Date)" in spec.input_interface_spec
    assert spec.live_verification_guide is not None
    assert "testDirectSync()" in spec.live_verification_guide


def test_taghi_system_prompt_two_tier_mandate(tmp_path):
    taghi = TaghiArchitect(vault_path=tmp_path / "vault", model_name="test")
    prompt = taghi.agent._system_prompts[0] if hasattr(taghi.agent, "_system_prompts") else str(taghi.agent.system_prompt)
    assert "TWO-TIER VERIFICATION ARCHITECTURE & SPECIFICATION MANDATE" in prompt
    assert "Tier 1 (Automated Docker Validation)" in prompt
    assert "Tier 2 (Guided Live Environment Verification)" in prompt
    assert "live_verification_guide" in prompt


def test_meti_system_prompt_two_tier_mandate(tmp_path):
    meti = MetiImplementer(vault_path=tmp_path / "vault", model_name="test")
    prompt = meti.agent._system_prompts[0] if hasattr(meti.agent, "_system_prompts") else str(meti.agent.system_prompt)
    assert "TWO-TIER VERIFICATION DELIVERY MANDATE" in prompt
    assert "Tier 1 (Automated Docker Validation)" in prompt
    assert "Tier 2 (Live Smoke Verification Script & Guided Checklist)" in prompt
    assert "Live Verification Checklist" in prompt


def test_print_spec_proposal_card_with_live_guide(capsys):
    spec = TechnicalSpec(
        task_id="task-card-test",
        architecture_overview="Architecture details",
        required_dependencies=[],
        base_image="python:3.11-slim",
        phases=[],
        input_interface_spec="Form with Date and Amount",
        live_verification_guide="Run python scripts/verify_live.py on host",
    )
    print_spec_proposal_card(spec)
    out = capsys.readouterr().out
    assert "Tier 2: Live Verification Guide:" in out
    assert "Run python scripts/verify_live.py on host" in out
    assert "Form with Date and Amount" in out


def test_prompt_delivery_gate_detects_tier2_smoke_scripts(tmp_path, capsys):
    workspace = tmp_path / "workspace" / "task-smoke"
    scripts_dir = workspace / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    dist_dir = workspace / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)

    # Add mock live verification script and Apps Script file
    (scripts_dir / "verify_live.py").write_text("print('verify')", encoding="utf-8")
    (dist_dir / "Code.gs").write_text("function testDirectSync() {}\nfunction createGoogleForm() {}", encoding="utf-8")

    action, feedback = prompt_delivery_gate(
        task_id="task-smoke",
        workspace_path=workspace,
        summary_text="Implementation complete with Tier 2 smoke verification",
        auto=False,
        input_func=lambda _: "y",
    )
    assert action == "confirm"
    assert feedback is None

    out = capsys.readouterr().out
    assert "Tier 2: Guided Live Verification Commands:" in out
    assert "python scripts/verify_live.py" in out
    assert "testDirectSync" in out
    assert "createGoogleForm" in out


def test_print_how_to_run_detects_live_smoke_command(tmp_path, capsys):
    workspace = tmp_path / "workspace" / "task-how-to-run"
    scripts_dir = workspace / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "verify_live.py").write_text("print('ok')", encoding="utf-8")
    (workspace / "main.py").write_text("print('app')", encoding="utf-8")

    print_how_to_run(workspace)
    out = capsys.readouterr().out
    assert "Tier 2 Smoke:" in out
    assert "python scripts/verify_live.py" in out
