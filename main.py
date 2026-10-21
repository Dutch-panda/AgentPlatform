import sys
import argparse
import uuid
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from tools.chatgpt_auth import get_chatgpt_model
from tools.project_notes import validate_project_id

# Load environment variables (API keys, etc.) from .env
load_dotenv()

from agents.natasha import NatashaRouter
from agents.odin import OdinResearcher
from agents.taghi import ExecutionPhase, TaghiArchitect
from agents.meti import MetiImplementer

async def main() -> None:
    parser = argparse.ArgumentParser(description="Run the multi-agent engineering workflow")
    parser.add_argument("prompt", help="Task description or prompt")
    parser.add_argument("--project", type=validate_project_id, help="Parent project ID, for example my-awesome-app")
    args = parser.parse_args()
    user_prompt = args.prompt.strip()
    project_id = args.project
    if not user_prompt:
        print("Task description cannot be empty.")
        sys.exit(1)

    model_name = await get_chatgpt_model()

    # 1. Generate a unique, immutable task ID
    timestamp = datetime.now().strftime("%Y%m%d")
    short_hash = uuid.uuid4().hex[:6]
    task_id = f"task-{timestamp}-{short_hash}"

    print(f"[Orchestrator] Starting V2 Workflow for {task_id}")

    natasha = NatashaRouter(model_name=model_name)

    # 3. Natasha Coordinator & Dynamic Router
    task_brief = await natasha.coordinate_request(user_prompt, task_id, project_id=project_id)
    target = task_brief.target_lead.lower()

    print(f"\n[Orchestrator] Natasha routed task to: {target.upper()}\n")

    objective = task_brief.objective
    if task_brief.research_questions:
        objective += "\n\nScope and questions:\n" + "\n".join(
            f"- {question}" for question in task_brief.research_questions
        )

    if target == "odin":
        # Full Research -> Architecture -> Implementation Pipeline
        research = await OdinResearcher(model_name=model_name).conduct_research(task_id, objective, project_id=project_id)
        research_context = (
            f"Objective: {objective}\n\nSummary: {research.summary}\n\n"
            "Key findings:\n" + "\n".join(f"- {item}" for item in research.key_findings)
            + "\n\nRecommended stack:\n"
            + "\n".join(f"- {item}" for item in research.recommended_stack)
        )
        spec = await TaghiArchitect(model_name=model_name).create_specification(task_id, research_context, project_id=project_id)

    elif target == "taghi":
        # Skip research, go straight to Architecture Design -> Implementation
        spec = await TaghiArchitect(model_name=model_name).create_specification(task_id, objective, project_id=project_id)

    elif target == "meti":
        validation_script = f"validate-{task_id}.sh"
        default_phases = [
            ExecutionPhase(
                phase_name="1-fast-track",
                instructions=(
                    f"{objective}\n\n"
                    f"Create your project directory at workspace/{task_id}/ and place all modules there. "
                    f"Create {validation_script} in /app/workspace/{task_id}/ with task-specific tests or checks. "
                    "The script must exercise the implemented behavior and exit nonzero on failure. "
                    "A completion message alone is not validation."
                ),
                validation_command=f"sh /app/workspace/{task_id}/{validation_script}",
            )
        ]
        result = await MetiImplementer(model_name=model_name).execute_specification(task_id, objective, default_phases, project_id=project_id)

    else:
        raise ValueError(f"Unknown target lead: {target}")

    if target in ("odin", "taghi"):
        result = await MetiImplementer(model_name=model_name).execute_specification(
            task_id, spec.architecture_overview, spec.phases,
            required_dependencies=spec.required_dependencies,
            project_id=project_id,
        )

    print(f"[Orchestrator] {result.summary}")
    if result.status != "success":
        print(f"[Orchestrator] Workflow {task_id} failed. Check ./vault/code-reviews.")
        sys.exit(1)

    print(f"[Orchestrator] Workflow {task_id} Completed Successfully!")
    print("[Orchestrator] Check your ./vault folder and Obsidian app.")

if __name__ == "__main__":
    asyncio.run(main())
