import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from agents.meti import ImplementationResult, MetiImplementer
from agents.natasha import NatashaRouter, TaskBrief
from agents.odin import OdinResearcher, ResearchReport
from agents.taghi import ExecutionPhase, TaghiArchitect, TechnicalSpec
from tools.project_notes import prepare_project
import main


class ProjectNotesTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.vault = Path(self.temporary.name) / "vault"

    def test_project_creation_preserves_existing_notes_and_rejects_unsafe_ids(self):
        context = prepare_project(self.vault, "my-app")
        note = self.vault / "projects/my-app.md"
        self.assertIn('type: "project"', note.read_text())
        self.assertEqual(context.link, "[[projects/my-app]]")
        note.write_text("My existing project content")
        prepare_project(self.vault, "my-app")
        self.assertEqual(note.read_text(), "My existing project content")
        prepare_project(self.vault, "another-app")
        self.assertTrue((self.vault / "projects/another-app.md").is_file())
        for project_id in ("../escape", "/tmp/escape", "", 'bad"id', "bad/name"):
            with self.subTest(project_id=project_id), self.assertRaises(ValueError):
                prepare_project(self.vault, project_id)

    def test_projects_directory_cannot_escape_the_vault(self):
        self.vault.mkdir()
        (self.vault / "projects").symlink_to(self.vault.parent, target_is_directory=True)
        with self.assertRaises(ValueError):
            prepare_project(self.vault, "my-app")

    async def test_all_artifacts_share_the_project_and_standalone_tasks_omit_it(self):
        phase = ExecutionPhase(phase_name="test", instructions="Implement", validation_command="pytest")
        with patch("agents.meti.DockerSandboxRunner"):
            agents = [
                NatashaRouter(vault_path=str(self.vault), model_name="test"),
                OdinResearcher(vault_path=str(self.vault), model_name="test"),
                TaghiArchitect(vault_path=str(self.vault), model_name="test"),
                MetiImplementer(vault_path=str(self.vault), model_name="test"),
            ]
        models = [
            TaskBrief(task_id="wrong", project_id="invented", title="Task", objective="Build", slug="task", target_lead="odin", research_questions=[]),
            ResearchReport(task_id="wrong", project_id="invented", summary="Research", key_findings=[], recommended_stack=[]),
            TechnicalSpec(task_id="wrong", project_id="invented", architecture_overview="Design", required_dependencies=[], phases=[phase]),
            ImplementationResult(task_id="wrong", project_id="invented", status="failed", summary="Not executed", executed_phases=[]),
        ]
        calls = [
            ("coordinate_request", lambda task: ("Build", task)),
            ("conduct_research", lambda task: (task, "Build")),
            ("create_specification", lambda task: (task, "Design")),
            ("execute_specification", lambda task: (task, "Design", [phase])),
        ]
        paths = ["tasks/{task}-brief.md", "research/research-{task}.md", "specs/spec-{task}.md", "code-reviews/review-{task}.md"]
        for task_id, project_id in (("task-one", "my-app"), ("task-two", "my-app"), ("task-three", "other-app"), ("task-four", None)):
            for agent, model, (method, arguments), path in zip(agents, models, calls, paths):
                agent.agent = SimpleNamespace(run=AsyncMock(return_value=SimpleNamespace(output=model.model_copy(deep=True))))
                agent.graph_manager = Mock()
                agent.graph_manager.query_nodes.return_value = []
                agent.graph_manager.resolve_note_sources.return_value = []
                result = await getattr(agent, method)(*arguments(task_id), project_id=project_id)
                self.assertEqual(result.task_id, task_id)
                self.assertEqual(result.project_id, project_id)
                content = (self.vault / path.format(task=task_id)).read_text()
                if project_id:
                    link = f"[[projects/{project_id}]]"
                    self.assertIn(f'project: "{link}"', content)
                    self.assertIn(f"Project: {link}", content)
                    self.assertIn(f"Project ID: {project_id}", agent.agent.run.call_args.args[0])
                else:
                    self.assertNotIn("\nproject:", content)
                    self.assertNotIn("[[projects/", content)

    async def test_cli_passes_project_through_every_route(self):
        phase = ExecutionPhase(phase_name="test", instructions="Implement", validation_command="pytest")
        for route in ("odin", "taghi", "meti"):
            with self.subTest(route=route), patch.object(main, "get_chatgpt_model", AsyncMock(return_value="test")), \
                 patch.object(main, "NatashaRouter") as natasha, patch.object(main, "OdinResearcher") as odin, \
                 patch.object(main, "TaghiArchitect") as taghi, patch.object(main, "MetiImplementer") as meti, \
                 patch.object(main.sys, "argv", ["main.py", "Build", "--project", "my-app"]):
                natasha.return_value.coordinate_request = AsyncMock(return_value=TaskBrief(task_id="task", title="Task", target_lead=route, objective="Build", slug="task", research_questions=[]))
                odin.return_value.conduct_research = AsyncMock(return_value=ResearchReport(task_id="task", summary="Research", key_findings=[], recommended_stack=[]))
                taghi.return_value.create_specification = AsyncMock(return_value=TechnicalSpec(task_id="task", architecture_overview="Design", phases=[phase], required_dependencies=[]))
                meti.return_value.execute_specification = AsyncMock(return_value=ImplementationResult(task_id="task", status="success", summary="Done", executed_phases=[]))
                await main.main()
                self.assertEqual(natasha.return_value.coordinate_request.call_args.kwargs["project_id"], "my-app")
                self.assertEqual(meti.return_value.execute_specification.call_args.kwargs["project_id"], "my-app")
                if route == "odin":
                    self.assertEqual(odin.return_value.conduct_research.call_args.kwargs["project_id"], "my-app")
                else:
                    odin.return_value.conduct_research.assert_not_called()
                if route in ("odin", "taghi"):
                    self.assertEqual(taghi.return_value.create_specification.call_args.kwargs["project_id"], "my-app")
                else:
                    taghi.return_value.create_specification.assert_not_called()


if __name__ == "__main__":
    unittest.main()
