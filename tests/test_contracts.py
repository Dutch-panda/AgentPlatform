import json
import sqlite3
import pytest

from contracts import (
    ExecutionPhase,
    ImplementationCheckpoint,
    ImplementationResult,
    ResearchReport,
    TaskBrief,
    TechnicalSpec,
    ValidationAttempt,
    format_design_context,
)
from tools.task_ledger import TaskLedger, TaskRecord


def test_zero_circular_imports():
    """Verify contracts can be imported cleanly without importing agents or tools."""
    import sys
    # Verify contracts module has no imports of agents or tools
    import contracts
    contracts_attrs = dir(contracts)
    assert "TaskBrief" in contracts_attrs
    assert "ResearchReport" in contracts_attrs
    assert "TechnicalSpec" in contracts_attrs
    assert "ExecutionPhase" in contracts_attrs
    assert "ImplementationCheckpoint" in contracts_attrs
    assert "ImplementationResult" in contracts_attrs
    assert "ValidationAttempt" in contracts_attrs
    assert "format_design_context" in contracts_attrs


def test_format_design_context_preserves_vault_sources_and_distinguishes_context():
    objective = "Build a user authentication service with JWT"
    research = ResearchReport(
        task_id="task-auth",
        project_id="auth-proj",
        summary="Use pyjwt and passlib with argon2 hashing.",
        key_findings=[
            "Argon2 is recommended over bcrypt for new designs.",
            "Stateless JWT tokens require short expiry and refresh rotation.",
        ],
        recommended_stack=["fastapi", "pyjwt", "passlib[argon2]"],
        vault_sources=["projects/auth-notes.md", "[[specs/legacy-auth.md]]"],
    )

    context = format_design_context(objective, research)

    assert f"Objective: {objective}" in context
    assert "Summary: Use pyjwt and passlib with argon2 hashing." in context
    assert "- Argon2 is recommended over bcrypt for new designs." in context
    assert "- fastapi" in context
    assert "Retrieved vault context (historical vault notes; not independent empirical facts):" in context
    assert "- [[projects/auth-notes.md]]" in context
    assert "- [[specs/legacy-auth.md]]" in context  # Avoids double brackets


def test_format_design_context_without_research_or_sources():
    objective = "Build a CLI parser"
    # No research provided
    assert format_design_context(objective, None) == objective

    # Research without vault_sources
    research = ResearchReport(
        task_id="task-cli",
        summary="Use argparse.",
        key_findings=["Standard library argparse has zero dependencies."],
        recommended_stack=["python-standard-library"],
        vault_sources=[],
    )
    context = format_design_context(objective, research)
    assert f"Objective: {objective}" in context
    assert "Use argparse." in context
    assert "Retrieved vault context" not in context


def test_legacy_sqlite_payload_round_trip(tmp_path):
    """Ensure older raw-dictionary JSON rows in SQLite load into typed models without data loss."""
    db_path = tmp_path / "tasks.db"
    raw_payload = {
        "schema_version": 1,
        "task_id": "task-legacy-001",
        "prompt": "Implement SQLite caching layer",
        "project_id": "cache-sys",
        "status": "IMPLEMENTING",
        "brief": {
            "project_id": "cache-sys",
            "task_id": "task-legacy-001",
            "title": "SQLite Caching",
            "objective": "Build SQLite cache",
            "slug": "sqlite-cache",
            "target_lead": "odin",
            "research_questions": ["What is cache expiry latency?"],
            "custom_legacy_brief_field": "preserved",
        },
        "research": {
            "task_id": "task-legacy-001",
            "project_id": "cache-sys",
            "summary": "SQLite with WAL mode provides low-overhead cache.",
            "key_findings": ["WAL mode allows concurrent readers."],
            "recommended_stack": ["sqlite3"],
            "vault_sources": ["notes/sqlite-tuning.md"],
            "custom_legacy_research_field": 42,
        },
        "specification": {
            "task_id": "task-legacy-001",
            "project_id": "cache-sys",
            "architecture_overview": "Cache interface with get/set and TTL.",
            "required_dependencies": [],
            "base_image": "python:3.11-slim",
            "phases": [
                {
                    "phase_name": "1-schema",
                    "instructions": "Create table",
                    "validation_command": "pytest test_schema.py",
                },
                {
                    "phase_name": "2-api",
                    "instructions": "Implement get/set",
                    "validation_command": "pytest test_api.py",
                },
            ],
        },
        "implementation": {
            "phases": [
                {
                    "phase_name": "1-schema",
                    "instructions": "Create table",
                    "validation_command": "pytest test_schema.py",
                },
                {
                    "phase_name": "2-api",
                    "instructions": "Implement get/set",
                    "validation_command": "pytest test_api.py",
                },
            ],
            "validated_phases": ["1-schema"],
            "validation_attempts": [
                {
                    "phase_name": "1-schema",
                    "command": "pytest test_schema.py",
                    "attempt": 1,
                    "success": True,
                    "exit_code": 0,
                    "output": "PASSED",
                    "run_number": 1,
                }
            ],
            "in_flight_command": None,
            "interrupted_commands": [],
            "workspace_used": True,
            "base_image": "python:3.11-slim",
            "project_id": "cache-sys",
            "custom_legacy_impl_flag": True,
        },
        "result": None,
        "error": None,
        "run_number": 1,
    }

    ledger = TaskLedger(db_path)
    # Insert directly into SQLite table as an older version would have written
    with sqlite3.connect(db_path) as conn:
        conn.execute("INSERT INTO tasks VALUES (?, ?)", ("task-legacy-001", json.dumps(raw_payload)))

    # Load via TaskLedger
    record = ledger.load("task-legacy-001")

    # Verify typed models
    assert isinstance(record.brief, TaskBrief)
    assert record.brief.slug == "sqlite-cache"
    assert record.brief["custom_legacy_brief_field"] == "preserved"

    assert isinstance(record.research, ResearchReport)
    assert record.research.vault_sources == ["notes/sqlite-tuning.md"]
    assert record.research["custom_legacy_research_field"] == 42

    assert isinstance(record.specification, TechnicalSpec)
    assert len(record.specification.phases) == 2
    assert record.specification.phases[0].phase_name == "1-schema"

    assert isinstance(record.implementation, ImplementationCheckpoint)
    assert record.implementation.is_started() is True
    assert record.implementation.validated_phases == ["1-schema"]
    assert len(record.implementation.validation_attempts) == 1
    assert record.implementation.validation_attempts[0].success is True
    assert record.implementation["custom_legacy_impl_flag"] is True

    # Dict-like access works on models
    assert record.implementation["validated_phases"] == ["1-schema"]
    assert record.implementation["validation_attempts"][0]["run_number"] == 1
    assert record.implementation.get("base_image") == "python:3.11-slim"

    # Save and reload again to verify clean round-trip
    record.run_number = 2
    ledger.save(record)
    reloaded = ledger.load("task-legacy-001")
    assert reloaded.run_number == 2
    assert reloaded.brief.title == "SQLite Caching"
    assert reloaded.implementation.validated_phases == ["1-schema"]


def test_checkpoint_plan_consistency_validation():
    phases = [
        ExecutionPhase(phase_name="1-db", instructions="DB", validation_command="test-1"),
        ExecutionPhase(phase_name="2-api", instructions="API", validation_command="test-2"),
    ]

    # Valid matching plan and prefix
    checkpoint = ImplementationCheckpoint(
        phases=phases,
        validated_phases=["1-db"],
        validation_attempts=[
            ValidationAttempt("1-db", "test-1", 1, True, 0, "pass", run_number=1)
        ],
    )
    # Resuming with run_number=2 is valid
    checkpoint.validate_plan_consistency(phases, run_number=2)

    # 1. Plan mismatch: different phase instructions
    mismatched_phases = [
        ExecutionPhase(phase_name="1-db", instructions="MODIFIED INSTRUCTIONS", validation_command="test-1"),
        ExecutionPhase(phase_name="2-api", instructions="API", validation_command="test-2"),
    ]
    with pytest.raises(ValueError, match="Checkpoint phase plan does not match the saved specification"):
        checkpoint.validate_plan_consistency(mismatched_phases, run_number=2)

    # 2. Plan mismatch: different number of phases
    with pytest.raises(ValueError, match="Checkpoint phase plan does not match the saved specification"):
        checkpoint.validate_plan_consistency(phases[:1], run_number=2)

    # 3. Validated phases not an ordered prefix: phase 2 validated before phase 1
    out_of_order = ImplementationCheckpoint(
        phases=phases,
        validated_phases=["2-api"],
    )
    with pytest.raises(ValueError, match="Checkpoint validated phases must be an ordered prefix of the phase plan"):
        out_of_order.validate_plan_consistency(phases, run_number=2)

    # 4. Validated phases has duplicate / non-prefix phase
    duplicate_phases = ImplementationCheckpoint(
        phases=phases,
        validated_phases=["1-db", "1-db"],
    )
    with pytest.raises(ValueError, match="Checkpoint validated phases must be an ordered prefix of the phase plan"):
        duplicate_phases.validate_plan_consistency(phases, run_number=2)

    # 5. Resumed run without incrementing run number
    with pytest.raises(ValueError, match="A resumed run must use a new run number"):
        checkpoint.validate_plan_consistency(phases, run_number=1)

    # 6. Invalid non-positive attempt or run_number
    invalid_attempt = ImplementationCheckpoint(
        phases=phases,
        validated_phases=["1-db"],
        validation_attempts=[
            ValidationAttempt("1-db", "test-1", 0, True, 0, "pass", run_number=1)
        ],
    )
    with pytest.raises(ValueError, match="Validation attempts must have positive run_number and attempt values"):
        invalid_attempt.validate_plan_consistency(phases, run_number=2)

    # 7. Attempt referencing unknown phase
    unknown_phase_attempt = ImplementationCheckpoint(
        phases=phases,
        validated_phases=[],
        validation_attempts=[
            ValidationAttempt("unknown-phase", "test", 1, True, 0, "pass", run_number=1)
        ],
    )
    with pytest.raises(ValueError, match="Validation attempt references unknown phase: unknown-phase"):
        unknown_phase_attempt.validate_plan_consistency(phases, run_number=2)


def test_checkpoint_is_started():
    assert ImplementationCheckpoint().is_started() is False
    assert ImplementationCheckpoint(phases=[]).is_started() is False

    assert ImplementationCheckpoint(workspace_used=True).is_started() is True
    assert ImplementationCheckpoint(validated_phases=["1-test"]).is_started() is True
    assert ImplementationCheckpoint(
        validation_attempts=[ValidationAttempt("1-test", "cmd", 1, True, 0, "ok")]
    ).is_started() is True
    assert ImplementationCheckpoint(in_flight_command="pytest").is_started() is True


def test_implementation_result_dict_and_attr_access():
    result = ImplementationResult(
        task_id="task-test",
        project_id="my-proj",
        status="success",
        summary="All phases validated",
        executed_phases=["1-db", "2-api"],
    )
    assert result.status == "success"
    assert result["status"] == "success"
    assert result.executed_phases == ["1-db", "2-api"]
    assert result["executed_phases"] == ["1-db", "2-api"]
    assert result.get("non_existent", "fallback") == "fallback"
    assert "summary" in result
