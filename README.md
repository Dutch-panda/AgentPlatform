<div align="center">

# Agent Platform

### One prompt. Four agent roles. A connected knowledge trail.

Turn engineering requests into structured briefs, research, phased specifications, and validated implementations.

![Version](https://img.shields.io/badge/version-0.1.0-6366f1?style=flat-square)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![Pydantic AI](https://img.shields.io/badge/agents-Pydantic_AI-e92063?style=flat-square)
![Docker](https://img.shields.io/badge/execution-Docker-2496ED?style=flat-square&logo=docker&logoColor=white)
![Obsidian](https://img.shields.io/badge/notes-Obsidian-7C3AED?style=flat-square&logo=obsidian&logoColor=white)

[Website](https://dutch-panda.github.io/AgentPlatform/) · [Tests](#testing) · [CI results](https://github.com/Dutch-panda/AgentPlatform/actions/workflows/tests.yml) · [Quick start](#quick-start) · [Workflow](#how-the-workflow-runs) · [Resume a task](#resume-a-task) · [Project memory](#keep-related-tasks-connected) · [Repository](#repository-map) · [Troubleshooting](#troubleshooting)

</div>

---

Agent Platform is a Python CLI that coordinates an engineering team built with Pydantic AI. Natasha selects the entry point for each request; Odin researches, Taghi designs, and Meti implements through Docker commands. Each stage saves Markdown artifacts to a local vault, with Graphify providing graph lookup when extraction is available.

## How the workflow runs

```text
Prompt → Natasha · brief and routing
              │
              ├─ Research → Odin → Taghi → Meti
              ├─ Design   → Taghi → Meti
              └─ Build    → Meti

Meti → Docker commands → Phase checks → Result
```

- **Natasha — coordinator:** produces a typed task brief and chooses the next lead. Can query existing vault nodes and connections.
- **Odin — researcher:** searches vault graph metadata and related nodes to produce findings and a recommended stack. Research notes automatically list resolved source notes. The current agent has vault tools; no dedicated web-search tool is registered.
- **Taghi — architect:** produces an architecture overview, dependencies, and ordered execution phases with explicit validation commands.
- **Meti — implementer:** writes code through Docker commands and validates phases in order. A reported success is downgraded to failure if any phase remains unvalidated.

Agents run sequentially along the selected route. Research requests continue through design and implementation; design requests continue through implementation.

## Quick start

### 1. Prepare the environment

You need **Python 3.11+**, **Docker installed and running**, and a ChatGPT account with access to the configured model through the provider's sign-in flow. Network access is needed for authentication, model calls, and image or dependency downloads. Obsidian is optional for viewing notes.

Clone the repository if you have not already done so:

```bash
git clone https://github.com/Dutch-panda/AgentPlatform.git
cd AgentPlatform
```

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
docker info
```

On Windows, activate the environment with `.venv\Scripts\Activate.ps1` in PowerShell.

### 2. Configure the model (optional)

The CLI loads `.env` automatically. These are the settings read by the authentication helper, shown with their current code defaults:

```dotenv
OPENAI_MODEL=gpt-6.1-sol
CHATGPT_AUTH_FILE=.env.chatgpt-auth.json
```

Relative credential paths resolve from the repository root; `~` is expanded. The CLI uses ChatGPT OAuth through Pydantic AI. On the first run, open the printed authorization URL and complete sign-in. Credentials are saved locally for reuse. The default credential filename is covered by `.gitignore`; keep any custom credential file out of version control too.

### 3. Give the team a task

```bash
python main.py "Build a compound interest calculator" --project my-awesome-app
```

For a standalone task, omit the project:

```bash
python main.py "Create a small CSV validation utility with tests"
```

Run commands from the repository root so `./vault` and `./workspace` resolve correctly. Inspect the CLI without starting a workflow:

```bash
python main.py --help
```

The first sandbox command pulls `node:18-bullseye-slim` if it is missing locally. Generated files live in `workspace/<task_id>/`; implementation summaries and phase results are saved under `vault/code-reviews/`. A returned failed implementation makes the CLI exit with status `1`.

## Resume a task

The CLI creates a permanent task ID before routing and prints it for later use. Each run is saved in a local SQLite ledger at `.state/tasks.db`. If a workflow fails or is interrupted, resume it from the same repository root:

```bash
python main.py --resume task-20261024-build-csv-validator-012345abcdef
```

Replace the example ID with the one printed by your run. Resume reuses the saved prompt, project ID, stage outputs, and `workspace/<task_id>/`. Do not supply a new prompt or `--project` together with `--resume`.

The ledger tracks `PENDING`, `RESEARCHING`, `ARCHITECTING`, `IMPLEMENTING`, `COMPLETED`, and `FAILED`. Completed routing, research, and specification outputs are reused. During implementation, validated phases are skipped and prior validation history is retained. A resumed task that proceeds to execution starts a new numbered run with a fresh three-attempt budget for unfinished phases. A completed task returns without calling a model or rerunning agents.

Command checkpoints are saved before execution and after results are recorded. If interruption happens between those points, the CLI reports the command's outcome as unknown. Inspect the workspace and any external side effects before resuming; a container may still be running after an abrupt process exit. An unfinished command or stage may execute again. Resume does **not** guarantee exactly-once execution or restore the entire model conversation; Meti receives the saved plan, validation history, and interrupted-command information in a fresh conversation.

Back up `.state/`, the corresponding task workspace, and `vault/` together when no workflow is running. Git does not back up the ignored ledger, workspaces, or generated notes. The ledger stores prompts, structured stage outputs, and validation logs locally; it does not replace the generated workspace or vault files. A missing workspace after implementation has begun causes resume to fail rather than silently discard saved work. Only tasks created with the ledger can be resumed; older vault artifacts are not imported automatically. Local per-task locks prevent concurrent CLI runs of the same task and release when the process exits. Unknown IDs and unreadable checkpoints fail explicitly.

## Keep related tasks connected

Reuse a project ID across requests:

```bash
python main.py "Design a SQLite-backed task tracker" --project task-tracker
python main.py "Build a CSV import utility for a task tracker" --project task-tracker
```

Agent Platform creates `vault/projects/task-tracker.md` if needed and preserves existing project-note content. Produced briefs, reports, specifications, and implementation reviews include a visible project link and frontmatter:

```yaml
project: "[[projects/task-tracker]]"
```

Project IDs accept letters, digits, underscores, and hyphens, and must start with a letter or digit. Project grouping links the notes. Each new task receives a separate workspace; resumed runs reuse that task’s existing workspace.

```text
Briefs ──────────┐
Research ────────┤
Specifications ──┼──→ Shared project note
Reviews ─────────┘    projects/<project_id>.md

Saved notes → Graphify (when available) → Agent queries
```

Open **`vault/` as an Obsidian vault** to browse the notes and project wikilinks. Those links work independently of Graphify.

Graph updates are attempted after stage artifacts are saved. Graphify Markdown extraction requires its own supported backend; if extraction fails, Agent Platform logs a warning and continues with saved notes. Without a usable graph, knowledge queries may return no context.

### Research source references

Odin records nodes retrieved from its initial task lookup and its search and neighbor-query tools. Search matches node IDs, labels, source-file paths, and properties. Each saved research report includes a **Related vault sources** section with relative Markdown links and corresponding wikilinks in its `links` frontmatter.

Source paths come from Graphify's `source_file` metadata, including that field inside `properties` when present. Only existing Markdown files inside the vault are listed; duplicate paths are removed, and missing files or paths outside the vault are omitted. The returned `ResearchReport.vault_sources` contains the same vault-relative paths, overriding any model-generated list.

These references identify retrieved graph context. They do not establish that the full source notes were read or that each finding is supported by a particular note. If no source files can be resolved, the report states that explicitly. Graph extraction still requires a working Graphify backend.

## What stays on disk

Each new task gets a permanent ID shaped like `task-YYYYMMDD-<prompt-slug>-<twelve-character-id>`. The slug is derived from the prompt before any model call; resume keeps the same ID.

```text
.state/tasks.db                      Local workflow ledger and checkpoints
.state/<task_id>.lock                Local process lock file (may remain after exit)
workspace/<task_id>/                  Generated source, tests, docs, dependencies
vault/
├── tasks/<task_id>-brief.md          Routing brief with the permanent task ID
├── research/research-<task_id>.md     Research report, when Odin runs
├── specs/spec-<task_id>.md            Specification, when Taghi runs
├── code-reviews/review-<task_id>.md   Implementation summary and validated phases
├── projects/<project_id>.md          Optional shared project note
└── .graphify/graph.json              Knowledge graph, when available
```

The local `.state/` directory, generated workspace files, stage notes, and graph artifacts are ignored by Git. Project notes under `vault/projects/` are **not currently ignored**; review them before committing.

## Execution and validation

- Each command runs in a **fresh Docker container**, with only the task directory mounted at `/app/workspace/<task_id>/`.
- Files in that mount persist across commands. Container-local installs and changes outside it do not; keep durable dependencies in the mounted directory.
- Each phase must pass its **exact validation command**, submitted separately with its phase name, in the declared order. Successful command exit codes are recorded as validation results.
- Failed phase validation returns combined stdout/stderr to Meti with the remaining attempt count. Meti can repair and rerun the same check, up to **three validation attempts per phase per run** (one initial attempt and two retries). The third failure stops execution before more sandbox commands or later phases.
- Straightforward tasks receive a fast-track phase that asks Meti to create and run a task-specific validation script.
- The runner defaults to a **120-second wait timeout** per command and removes the container after execution.

### Recovery and attempt history

When a validation command fails, Meti receives its output and can issue repair commands before retrying that phase. Rejected calls with the wrong phase or validation command do not consume an attempt. Running an exact declared validation command without its phase name is rejected. Repair commands are separate from the three-attempt validation budget.

If the model returns a final response while a failed phase still has attempts remaining, the application sends the failure logs back into the same conversation. If that recovery round returns without another validation attempt, the run ends as failed rather than repeatedly asking without progress. Model-run errors and retry exhaustion also produce a failed review note.

The review note records each phase's attempt number, command, exit code, captured output, and final resolution: passed, passed on retry, retry limit exhausted, stopped early, or not validated. Docker wait/execution errors preserve available container logs; image acquisition errors return failure feedback. This is bounded recovery within a run; `--resume` reuses saved progress and starts a new run budget. Neither mechanism guarantees that an autonomous repair will succeed.

## Repository map

```text
.
├── main.py                    CLI, task IDs, routing, and orchestration
├── agents/
│   ├── natasha.py             Structured briefs and routing
│   ├── odin.py                Research reports
│   ├── taghi.py               Specifications and execution phases
│   └── meti.py                Docker tools and phase validation tracking
├── tools/
│   ├── chatgpt_auth.py        OAuth credential storage and model setup
│   ├── docker_runner.py      Container lifecycle and workspace mounts
│   ├── graphify_tool.py      Graph extraction, node search, and neighbors
│   ├── project_notes.py      Project IDs, note creation, and shared links
│   └── task_ledger.py        SQLite checkpoints and per-task process locks
├── .github/workflows/tests.yml  Automated platform tests
├── tests/                    Deterministic platform tests
├── scripts/validate.py        Local test runner
├── docs/index.html           GitHub Pages presentation
├── pyproject.toml            Package metadata and dependencies
├── vault/                    Local Markdown knowledge base
└── workspace/                Generated task workspaces
```

## Troubleshooting

- **Docker connection fails:** start Docker and confirm `docker info` succeeds in the same terminal. The CLI uses the Docker SDK's environment configuration.
- **Authentication fails:** check the authorization callback completes and the credential file is readable. `CHATGPT_AUTH_FILE` selects the local credential file; `OPENAI_MODEL` selects the model. An API key alone does not replace this CLI's OAuth flow.
- **Graph extraction fails:** inspect the logged Graphify error. Extraction runs as `python -m graphify extract <vault>` using the CLI's Python interpreter, with `GRAPHIFY_OUT` pointing to `vault/.graphify`. Each extraction has a 300-second timeout. Saved Markdown remains available if extraction fails.
- **Dependencies disappear between commands:** install them inside the mounted task directory. Each command starts a new container.
- **Implementation reports failure:** inspect `vault/code-reviews/review-<task_id>.md` and terminal output. A phase is recorded only when its exact validation command exits successfully with the expected phase name.
- **Unknown task ID on resume:** run from the same repository root and use the permanent ID printed by the CLI. Confirm the original `.state/tasks.db` is present; older tasks created before the ledger cannot be resumed automatically.
- **Saved workspace is missing:** restore `workspace/<task_id>/` from the same backup as the ledger. A checkpoint records progress, not a copy of generated source files.
- **Task is already running:** another CLI process holds the task lock. Let it finish or stop that process; a leftover `.lock` file alone does not mean the lock is held. Do not delete lock files to bypass a running task.
- **Interrupted command outcome is unknown:** inspect the existing files, running containers, and external side effects before resuming. Commands may have partially completed and can run again.
- **Invalid checkpoint:** preserve the original ledger and restore a consistent backup if available. Do not edit phase completion flags to force a resume; start a new task if the checkpoint cannot be recovered.
- **A linked note is missing:** research and specification notes exist only when their stages run. New briefs use permanent task IDs; older artifacts may still contain unresolved temporary brief links.

## Development and documentation

The installed distribution is named `v2-agent-system`; run the CLI from the checkout with `python main.py`. There is no installed console-script entry point. Runtime dependencies and Python requirements are declared in [pyproject.toml](pyproject.toml); dependency versions are lower bounds rather than a locked environment.

The agent classes can also be called directly with a `model_name` (model string or Pydantic AI model object) and a `vault_path`. `MetiImplementer` additionally accepts `workspace_path`. Programmatic Meti calls can supply `checkpoint`, `checkpoint_callback`, and a new `run_number` to persist and restore implementation progress; the CLI connects these to the ledger automatically. The CLI supplies one OAuth-backed model to every stage; these constructor options are not CLI flags.

### Testing

Install the test extra and run the local validation command from the repository root:

```bash
python -m pip install -e '.[test]'
python scripts/validate.py
```

The script runs the platform tests in `tests/`; extra pytest arguments can be appended, for example `python scripts/validate.py -k validation`. Test discovery excludes generated workspaces. The suite uses Pydantic AI `TestModel` for structured outputs and `FunctionModel` for scripted tool calls, blocks real model requests, replaces Docker and graph extraction, and writes artifacts in temporary directories. It covers routing contracts, project links, graph retrieval, source resolution and report references, phase validation, bounded recovery, Docker failure feedback, ledger persistence, and resume behavior; it does not assess live model routing quality.

The [Platform tests workflow](.github/workflows/tests.yml) runs the same validation command on pushes and pull requests using Ubuntu with Python 3.11 and 3.14. Open [CI results](https://github.com/Dutch-panda/AgentPlatform/actions/workflows/tests.yml) to inspect runs. To start a manual run, select **Run workflow**, choose a branch, and confirm. Results and failure logs appear on the commit or pull request; no model credentials or Docker service are needed. Requiring passing checks before merging is a separate repository setting.

An end-to-end run still requires model access and Docker and writes local artifacts; review generated output before using it.

Documentation has three roles:

- This README describes the implemented platform and its operational limits.
- [Implementation delegation proposal](1746900806.md) and [web access proposal](web-acess) describe future work.
- `vault/` and `workspace/` contain local run artifacts and examples. Historical reports describe individual runs, not guaranteed platform capabilities. They are not the public platform manual.

## Current limitations

Agent Platform is version **0.1.0**. These details matter when interpreting its output:

- **Natasha note-writing tool:** the registered `write_research_note` tool references a `research_dir` attribute that its constructor does not initialize. Calling this optional tool fails; the normal routing-brief writer uses `tasks_dir` separately.
- **Optional stage links:** specification and review frontmatter can link to skipped stages; a wikilink does not guarantee its target exists.
- **Container isolation:** network access is enabled, the task directory is writable, and the runner does not configure CPU or memory limits.
- **Runtime availability:** the default container is a Node image. Python and other runtimes are not provisioned by the runner; tasks that need them must arrange installation or use an adapted image.
- **Validation scope:** phase completion reflects command exit codes. It does not independently establish test quality or provide a separate human code review.

<div align="center">

<sub>Built with Python · Pydantic AI · Docker · Markdown · Graphify</sub>

</div>
