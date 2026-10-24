<div align="center">

# Agent Platform

### One prompt. Four agent roles. A connected knowledge trail.

Turn engineering requests into structured briefs, research, phased specifications, and validated implementations.

![Version](https://img.shields.io/badge/version-0.1.0-6366f1?style=flat-square)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![Pydantic AI](https://img.shields.io/badge/agents-Pydantic_AI-e92063?style=flat-square)
![Docker](https://img.shields.io/badge/execution-Docker-2496ED?style=flat-square&logo=docker&logoColor=white)
![Obsidian](https://img.shields.io/badge/notes-Obsidian-7C3AED?style=flat-square&logo=obsidian&logoColor=white)

[Website](https://dutch-panda.github.io/AgentPlatform/) · [Tests](#testing) · [CI results](https://github.com/Dutch-panda/AgentPlatform/actions/workflows/tests.yml) · [Quick start](#quick-start) · [Workflow](#how-the-workflow-runs) · [Project memory](#keep-related-tasks-connected) · [Repository](#repository-map) · [Troubleshooting](#troubleshooting)

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

Project IDs accept letters, digits, underscores, and hyphens, and must start with a letter or digit. Project grouping links the notes; each run still receives a separate task workspace.

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

Each run gets an ID shaped like `task-YYYYMMDD-<slug>-<six-character-id>`.

```text
workspace/<task_id>/                  Generated source, tests, docs, dependencies
vault/
├── tasks/task-temp-brief.md          Routing brief (see limitation below)
├── research/research-<task_id>.md     Research report, when Odin runs
├── specs/spec-<task_id>.md            Specification, when Taghi runs
├── code-reviews/review-<task_id>.md   Implementation summary and validated phases
├── projects/<project_id>.md          Optional shared project note
└── .graphify/graph.json              Knowledge graph, when available
```

Generated workspace files, stage notes, and graph artifacts are ignored by Git. Project notes under `vault/projects/` are **not currently ignored**; review them before committing.

## Execution and validation

- Each command runs in a **fresh Docker container**, with only the task directory mounted at `/app/workspace/<task_id>/`.
- Files in that mount persist across commands. Container-local installs and changes outside it do not; keep durable dependencies in the mounted directory.
- Each phase must pass its **exact validation command**, submitted separately with its phase name, in the declared order. Successful command exit codes are recorded as validation results.
- Failed phase validation returns combined stdout/stderr to Meti with the remaining attempt count. Meti can repair and rerun the same check, up to **three validation attempts per phase** (one initial attempt and two retries). The third failure stops execution before more sandbox commands or later phases.
- Straightforward tasks receive a fast-track phase that asks Meti to create and run a task-specific validation script.
- The runner defaults to a **120-second wait timeout** per command and removes the container after execution.

### Recovery and attempt history

When a validation command fails, Meti receives its output and can issue repair commands before retrying that phase. Rejected calls with the wrong phase or validation command do not consume an attempt. Running an exact declared validation command without its phase name is rejected. Repair commands are separate from the three-attempt validation budget.

If the model returns a final response while a failed phase still has attempts remaining, the application sends the failure logs back into the same conversation. If that recovery round returns without another validation attempt, the run ends as failed rather than repeatedly asking without progress. Model-run errors and retry exhaustion also produce a failed review note.

The review note records each phase's attempt number, command, exit code, captured output, and final resolution: passed, passed on retry, retry limit exhausted, stopped early, or not validated. Docker wait/execution errors preserve available container logs; image acquisition errors return failure feedback. This is bounded recovery within a run, not checkpoint/resume support or a guarantee that an autonomous repair will succeed.

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
│   └── project_notes.py      Project IDs, note creation, and shared links
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
- **A linked note is missing:** research and specification notes exist only when their stages run. The temporary routing-brief issue below also affects task links.

## Development and documentation

The installed distribution is named `v2-agent-system`; run the CLI from the checkout with `python main.py`. There is no installed console-script entry point. Runtime dependencies and Python requirements are declared in [pyproject.toml](pyproject.toml); dependency versions are lower bounds rather than a locked environment.

The agent classes can also be called directly with a `model_name` (model string or Pydantic AI model object) and a `vault_path`. `MetiImplementer` additionally accepts `workspace_path`. The CLI supplies one OAuth-backed model to every stage; these constructor options are not CLI flags.

### Testing

Install the test extra and run the local validation command from the repository root:

```bash
python -m pip install -e '.[test]'
python scripts/validate.py
```

The script runs the platform tests in `tests/`; extra pytest arguments can be appended, for example `python scripts/validate.py -k validation`. Test discovery excludes generated workspaces. The suite uses Pydantic AI `TestModel` for structured outputs and `FunctionModel` for scripted tool calls, blocks real model requests, replaces Docker and graph extraction, and writes artifacts in temporary directories. It covers routing contracts, project links, graph retrieval, source resolution and report references, phase validation, bounded recovery, and Docker failure feedback; it does not assess live model routing quality.

The [Platform tests workflow](.github/workflows/tests.yml) runs the same validation command on pushes and pull requests using Ubuntu with Python 3.11 and 3.14. Open [CI results](https://github.com/Dutch-panda/AgentPlatform/actions/workflows/tests.yml) to inspect runs. To start a manual run, select **Run workflow**, choose a branch, and confirm. Results and failure logs appear on the commit or pull request; no model credentials or Docker service are needed. Requiring passing checks before merging is a separate repository setting.

An end-to-end run still requires model access and Docker and writes local artifacts; review generated output before using it.

Documentation has three roles:

- This README describes the implemented platform and its operational limits.
- [Implementation delegation proposal](1746900806.md) and [web access proposal](web-acess) describe future work.
- `vault/` and `workspace/` contain local run artifacts and examples. Historical reports describe individual runs, not guaranteed platform capabilities. They are not the public platform manual.

## Current limitations

Agent Platform is version **0.1.0**. These details matter when interpreting its output:

- **Routing brief identity:** Natasha writes `task-temp-brief.md` before the orchestrator assigns the final task ID. The saved brief is not renamed or rewritten, so later task-specific brief links may not resolve and subsequent runs overwrite that temporary brief.
- **Natasha note-writing tool:** the registered `write_research_note` tool references a `research_dir` attribute that its constructor does not initialize. Calling this optional tool fails; the normal routing-brief writer uses `tasks_dir` separately.
- **Optional stage links:** specification and review frontmatter can link to skipped stages; a wikilink does not guarantee its target exists.
- **Container isolation:** network access is enabled, the task directory is writable, and the runner does not configure CPU or memory limits.
- **Runtime availability:** the default container is a Node image. Python and other runtimes are not provisioned by the runner; tasks that need them must arrange installation or use an adapted image.
- **Validation scope:** phase completion reflects command exit codes. It does not independently establish test quality or provide a separate human code review.

<div align="center">

<sub>Built with Python · Pydantic AI · Docker · Markdown · Graphify</sub>

</div>
