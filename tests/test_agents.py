import asyncio
from unittest.mock import Mock

import pytest
from pydantic import ValidationError
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from agents.natasha import NatashaRouter, TaskBrief
from agents.odin import OdinResearcher
from agents.taghi import ExecutionPhase, TaghiArchitect


@pytest.mark.parametrize("lead", ["odin", "taghi", "meti"])
def test_natasha_preserves_routing_and_caller_identity(tmp_path, lead):
    output = dict(task_id="model-id", project_id="model-project", title="CSV tool",
                  objective="Validate CSV files", slug="csv-tool", target_lead=lead,
                  research_questions=["Which columns are required?"])
    router = NatashaRouter(vault_path=str(tmp_path / "vault"),
                           model_name=TestModel(call_tools=[], custom_output_args=output))
    brief = asyncio.run(router.coordinate_request("Build a CSV tool", "task-csv", project_id="csv"))
    assert (brief.target_lead, brief.task_id, brief.project_id) == (lead, "task-csv", "csv")
    note = (tmp_path / "vault/tasks/task-csv-brief.md").read_text()
    assert f'target_lead: "{lead}"' in note
    assert 'project: "[[projects/csv]]"' in note
    assert "Which columns are required?" in note
    assert (tmp_path / "vault/projects/csv.md").is_file()


def test_task_brief_rejects_unknown_route():
    with pytest.raises(ValidationError):
        TaskBrief(task_id="task-csv", title="CSV", objective="Validate", slug="csv",
                  target_lead="unknown", research_questions=[])


def test_odin_handles_empty_graph_and_failed_extraction(tmp_path, monkeypatch, capsys):
    output = dict(task_id="model-id", summary="No prior context", key_findings=["Use CSV"],
                  recommended_stack=["Python"])
    odin = OdinResearcher(vault_path=str(tmp_path / "vault"),
                         model_name=TestModel(call_tools=[], custom_output_args=output))
    lookup = Mock(return_value=[])
    monkeypatch.setattr(odin.graph_manager, "query_nodes", lookup)
    monkeypatch.setattr(odin.graph_manager, "build_graph", Mock(return_value=False))
    report = asyncio.run(odin.conduct_research("task-csv", "Research CSV"))
    lookup.assert_called_once_with("task-csv")
    assert report.task_id == "task-csv"
    note = (tmp_path / "vault/research/research-task-csv.md").read_text()
    assert "No prior context" in note and "Use CSV" in note and "Python" in note
    assert "graph update failed" in capsys.readouterr().out


def test_odin_can_query_related_graph_nodes(tmp_path, monkeypatch):
    step = 0
    returned = []

    def respond(messages, info):
        nonlocal step
        returned.extend(part.content for part in messages[-1].parts if isinstance(part, ToolReturnPart))
        step += 1
        if step == 1:
            return ModelResponse(parts=[ToolCallPart("get_related_notes", {"node_id": "past-task"})])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, dict(
            task_id="task-csv", summary="Related CSV work", key_findings=[], recommended_stack=[]))])

    odin = OdinResearcher(vault_path=str(tmp_path / "vault"), model_name=FunctionModel(respond))
    monkeypatch.setattr(odin.graph_manager, "query_nodes", Mock(return_value=[]))
    neighbors = Mock(return_value=[{"id": "past-spec"}])
    monkeypatch.setattr(odin.graph_manager, "get_neighbors", neighbors)
    asyncio.run(odin.conduct_research("task-csv", "Research CSV"))
    neighbors.assert_called_once_with("past-task")
    assert [{"id": "past-spec"}] in returned


def test_taghi_saves_dependencies_and_exact_validation(tmp_path):
    phase = ExecutionPhase(phase_name="1-test", instructions="Add CSV tests", validation_command="python -m pytest")
    model = TestModel(call_tools=[], custom_output_args=dict(
        task_id="model-id", architecture_overview="CSV module", required_dependencies=["pytest"],
        phases=[phase.model_dump()]))
    taghi = TaghiArchitect(vault_path=str(tmp_path / "vault"), model_name=model)
    spec = asyncio.run(taghi.create_specification("task-csv", "Use Python", project_id="csv"))
    assert spec.task_id == "task-csv" and spec.project_id == "csv"
    assert "workspace/csv/" in spec.architecture_overview
    assert spec.phases == [phase]
    note = (tmp_path / "vault/specs/spec-task-csv.md").read_text()
    assert "- pytest" in note and "`python -m pytest`" in note
    assert "[[projects/csv]]" in note

    standalone = asyncio.run(taghi.create_specification("task-standalone", "Use Python", project_id=None))
    assert "workspace/task-standalone/" in standalone.architecture_overview


def test_taghi_filters_unexecutable_blocked_phases(tmp_path):
    p1 = ExecutionPhase(phase_name="1-cli", instructions="Build CLI", validation_command="python -m pytest")
    p2 = ExecutionPhase(
        phase_name="2-authorized-gate",
        instructions="BLOCKED AND CONDITIONAL: do not run without live API token",
        validation_command="RUN_LIVE=1 python live_check.py",
    )
    model = TestModel(
        call_tools=[],
        custom_output_args=dict(
            task_id="model-id",
            architecture_overview="Hybrid CLI with offline core.",
            required_dependencies=["pytest"],
            phases=[p1.model_dump(), p2.model_dump()],
        ),
    )
    taghi = TaghiArchitect(vault_path=str(tmp_path / "vault"), model_name=model)
    spec = asyncio.run(taghi.create_specification("task-filter", "Build tool", project_id=None))

    # Automated phases must ONLY contain actionable offline phase
    assert spec.phases == [p1]

    # Markdown note must preserve the deferred gate in architecture overview and keep roadmap clean
    note = (tmp_path / "vault/specs/spec-task-filter.md").read_text()
    assert "### Phase: 1-cli" in note
    assert "### Phase: 2-authorized-gate" not in note
    assert "Deferred / Prerequisite Production Gates" in note
    assert "2-authorized-gate" in note
    assert "RUN_LIVE=1 python live_check.py" in note

