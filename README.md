<div align="center">

<img src="docs/brand/logo.svg" alt="BuildRelay Forward B logo" width="96" height="96">

# BuildRelay

### An AI development team that plans, builds, and checks your code.

Describe your development task. BuildRelay coordinates research, design, implementation, and validation, with saved progress you can resume.

![Version](https://img.shields.io/badge/version-0.1.0-6366f1?style=flat-square)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![Pydantic AI](https://img.shields.io/badge/agents-Pydantic_AI-e92063?style=flat-square)
![Docker](https://img.shields.io/badge/execution-Docker-2496ED?style=flat-square&logo=docker&logoColor=white)
![Obsidian](https://img.shields.io/badge/notes-Obsidian-7C3AED?style=flat-square&logo=obsidian&logoColor=white)

[Website](https://dutch-panda.github.io/BuildRelay/) · [Tests](#testing) · [CI results](https://github.com/Dutch-panda/BuildRelay/actions/workflows/tests.yml) · [Quick start](#quick-start) · [Workflow](#how-the-workflow-runs) · [Resume a task](#resume-a-task) · [Project memory](#keep-related-tasks-connected) · [Components](#component-connections) · [Security](#security-and-isolation-boundaries) · [Repository](#repository-map) · [Troubleshooting](#troubleshooting)

</div>

---

BuildRelay is a Python CLI that coordinates an engineering team built with Pydantic AI. Natasha selects the entry point for each request; Odin researches, Taghi designs, and Meti implements through Docker commands. Each stage saves Markdown artifacts to a local vault, with Graphify providing graph lookup when extraction is available.

## How the workflow runs

<img src="docs/diagrams/workflow.svg" alt="Natasha routes requests through research, design, or direct implementation, ending with Meti and validation." width="760">

- **Natasha — coordinator:** produces a typed task brief, a 5-sentence intent alignment brief, and chooses the next lead. Prompts with a low-friction clarification wizard for ambiguous requirements and supports mid-way intent pivots. Can query existing vault nodes and connections.
- **Odin — researcher:** searches vault graph metadata and related nodes to produce findings and a recommended stack. Research notes automatically list resolved source notes. The current agent has vault tools; no dedicated web-search tool is registered.
- **Taghi — architect:** produces an architecture overview, dependencies, and ordered execution phases with explicit validation commands. Phases are constrained to actionable sandbox validation; conditional gates or unprovided external credentials are documented in architecture overview notes rather than active execution phases.
- **Meti — implementer:** writes code through Docker commands with live progress spinners and validates phases in order. Generates a workspace `README.md` with run/test instructions, logs execution details to `.state/task.log`, and renders a file tree and `How to Run & Test` banner. A reported success is downgraded to failure if any phase remains unvalidated.

Agents run sequentially along the selected route. Research requests continue through design and implementation; design requests continue through implementation.

## Quick start

### 1. Prepare the environment

You need **Python 3.11+**, **Docker installed and running**, and a ChatGPT account with access to the configured model through the provider's sign-in flow. Network access is needed for authentication, model calls, and image or dependency downloads. Obsidian is optional for viewing notes.

Clone the repository if you have not already done so:

```bash
git clone https://github.com/Dutch-panda/BuildRelay.git
cd BuildRelay
```

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
docker info
```

On Windows, activate the environment with `.venv\Scripts\Activate.ps1` in PowerShell.

### 2. Configure credentials & providers

BuildRelay provides an interactive setup wizard to configure your preferred LLM provider, models, and execution tiers in seconds.

#### Interactive Setup Wizard (Recommended)

Run the configuration wizard directly at any time:

```bash
python main.py config
# Or using the console script:
buildrelay config
# Or via CLI flag:
python main.py --config
```

If you launch BuildRelay on a fresh machine without credentials, the CLI automatically detects the zero-config state and prompts:
```
⚡ BuildRelay — No AI credentials detected. Launching interactive setup wizard...
```

The wizard guides you through:
1. **Provider Selection:**
   - **ChatGPT Web Auth (Codex / Browser Subscription):** Connects to your ChatGPT Plus/Team subscription with zero API key charges. Supports Codex models (`gpt-6.1-sol`, `gpt-6.1`, `gpt-6`, `gpt-5.5`).
   - **OpenAI API:** Direct API key for GPT-4o, GPT-4o-mini, o3-mini, o1.
   - **Anthropic Claude:** Direct API key for Claude 3.7 Sonnet, Claude 3.5 Haiku.
   - **Google Gemini:** Direct API key for Gemini 2.0 Flash, Gemini 2.5 Pro.
   - **Local LLM (Ollama / LocalAI):** Free, local offline models (e.g. `llama3.3`, `qwen2.5-coder` at `http://localhost:11434/v1`).
   - **Custom / OpenRouter Gateway:** OpenRouter or custom OpenAI-compatible proxies.
2. **Masked Input & Validation:**
   - Inputs are masked for security (`password=True`).
   - A non-blocking reachability ping checks syntax and endpoint connectivity before saving, gracefully handling offline or sandboxed setups.
3. **Execution Tier Preset:**
   - Sets your default tier: `balanced` (default), `fast`, or `powerful`.
4. **Lead-Specific Model Customization (Optional):**
   - Customize models for individual leads: Natasha (Coordinator), Odin (Researcher), Taghi (Architect), Meti (Implementer).
5. **Safe Atomic Persistence:**
   - Saved directly to `.env` preserving existing comments and settings.
   - Enforces strict `0600` file permissions (owner read/write only).

#### Manual Configuration via `.env` (Alternative)

If you prefer editing `.env` directly:

**Option A: ChatGPT Web Auth (Codex Subscription — No API Key Required)**
```dotenv
OPENAI_MODEL=gpt-6.1-sol
CHATGPT_AUTH_FILE=.env.chatgpt-auth.json
DEFAULT_TIER=balanced
```

**Option B: Standard Direct API Keys**
```dotenv
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
DEFAULT_TIER=balanced

# Or Anthropic:
# ANTHROPIC_API_KEY=sk-ant-...
# ANTHROPIC_MODEL=claude-3-7-sonnet

# Or Gemini:
# GEMINI_API_KEY=AIza...
# GEMINI_MODEL=gemini-2.0-flash

# Optional per-lead overrides:
# MODEL_NATASHA=google:gemini-2.0-flash
# MODEL_ODIN=anthropic:claude-3-5-haiku
# MODEL_TAGHI=openai:gpt-6
# MODEL_METI=openai:gpt-6.1-sol
```

You can also override models at runtime using `--model` (e.g., `--model anthropic:claude-3-7-sonnet`) or per-lead flags (`--model-taghi`, `--model-meti`).

### 3. Give the team a task

```bash
python main.py "Build a compound interest calculator" --project my-awesome-app
```

For a standalone task, omit the project:

```bash
python main.py "Create a small CSV validation utility with tests"
```

To specify or override the Docker sandbox image:

```bash
python main.py "Build a Python utility" --image python:3.11-slim
```

Run commands from the repository root so `./vault` and `./workspace` resolve correctly. Inspect the CLI without starting a workflow:

```bash
python main.py --help
```

The first sandbox command pulls the selected container image (defaulting to `node:18-bullseye-slim` or the configured `DEFAULT_SANDBOX_IMAGE` / `--image`) if it is missing locally. Generated files live in `workspace/<project_id>/` (or `workspace/<task_id>/` for standalone tasks); implementation summaries and phase results are saved under `vault/code-reviews/`. A returned failed implementation makes the CLI exit with status `1`.

## Interactive alignment and execution modes

To eliminate early misunderstandings and prevent wasted model calls, BuildRelay provides an interactive alignment gate:

1. **Natasha's 5-Sentence Intent Brief:**
   - **Goal:** Exactly what is being built.
   - **Features:** Key functionality in scope.
   - **Stack:** Runtime, frameworks, and base Docker image.
   - **Exclusions:** Out-of-scope or deferred requirements.
   - **Next Steps:** Target lead and first deliverable.
2. **Smart Clarification Wizard:**
   - If technical ambiguity is detected, Natasha presents 1–2 targeted multiple-choice questions with preselected defaults.
   - Pressing **`[Enter]`** immediately confirms all recommended defaults with zero friction.
   - Pressing **`[e]`** allows typing a custom clarification or pivoting intent.
3. **Execution Flags:**
   - **Default interactive:** Runs the alignment gate before initiating research or design.
   - **Headless mode (`-y`, `--yes`, `--auto`):** Automatically accepts recommended defaults without terminal prompts; ideal for scripting and CI.
   - **Step-by-step mode (`--step`):** Prompts for confirmation before handing off to each lead (Natasha → Odin/Taghi → Meti). If the user pivots during a step gate, downstream checkpoints in `.state/tasks.db` are safely rolled back and re-routed.

## Token usage and cost analytics

BuildRelay tracks exact prompt (input) and completion (output) token consumption across every lead using PydanticAI metrics:

- **Cost Estimation Engine:** Calculates USD costs based on published model rates (OpenAI, Anthropic, Gemini).
- **Local & Test Models:** Displays `$0.00 (Local)` for Ollama/vLLM and test runs.
- **Inline Badges:** Natasha brief panels and Taghi specification cards display token tallies as each stage finishes (e.g. `Tokens Used: 1,550 (~$0.006)`).
- **Obsidian Vault Reports:** Meti's review notes under `vault/code-reviews/` record full token metrics and costs.
- **Completion Table:** At workflow completion, a styled Rich table summarizes prompt, completion, total tokens, and estimated cost per lead with grand totals.

## Tiered model routing and token optimization

To balance execution speed, reasoning depth, and cost efficiency, BuildRelay provides tiered model routing and context compression:

- **Model Tiers (`--tier`):**
  - **Fast (`--tier fast`):** Routes lightweight, fast models across all leads (`gpt-4o-mini`, `claude-3-5-haiku`, `gemini-2.0-flash`). Ideal for quick scripts, prototyping, and high speed.
  - **Balanced (`--tier balanced` — default):** Pairs fast models for routing (Natasha) and graph search (Odin) with high-reasoning models for architecture (Taghi: `o3-mini`) and implementation (Meti: `gpt-4o` / `claude-3-7-sonnet`).
  - **Powerful (`--tier powerful`):** Assigns top-tier frontier models across all design and execution phases.
- **Lead-Specific Overrides:**
  - Override individual leads via CLI flags: `--model-natasha`, `--model-odin`, `--model-taghi`, `--model-meti`.
  - Scoped overrides take precedence over global `--model` and `--tier`.
- **Model Lineup Approval Gate:**
  - On launch, BuildRelay renders a 2-column model lineup card displaying the active model for each lead, cost tier label, caching status, and estimated budget.
  - Interactive users can press **`[Enter]`** to confirm, **`[c]`** to quickly switch tiers, or **`[q]`** to abort. Auto/headless runs (`-y`/`--auto`) accept automatically.
- **Prompt Prefix Caching:**
  - All agent system prompts, static guidelines, and contracts are stabilized at prompt prefixes.
  - Provider prompt caching (`model_settings={"cache": True}`) is enabled across Anthropic, OpenAI, and Gemini, reducing latency by up to 80% and input token costs by up to 90% during Meti's Docker retry cycles.
  - Cached tokens are detected and discounted in token summary badges and ledger reports.
- **Context Pruning & Compression:**
  - **Markdown Sanitization:** `prune_markdown` strips verbose YAML frontmatter, empty sections, and backlink blocks.
  - **Semantic Graph Pruning:** `prune_graph_context` scores and ranks vault nodes by keyword overlap, passing only the top 3–5 relevant snippets to Odin rather than raw graph dumps.
  - **Docker Log Slicing:** `prune_docker_log` automatically detects failure tracebacks and assertion errors in long build logs, slicing around the error signature to prevent context window dilution during retry loops.

## Dynamic progress and project delivery

- **Live Progress Spinners:** Active Docker operations and LLM generation phases display animated Rich status spinners (`rich.status.Status`) instead of terminal dumps.
- **Clean Execution Logs:** Docker stdout and stderr are routed to `.state/task.log`. Set `BUILDRELAY_DEBUG=1` to echo full container outputs directly to the terminal.
- **Auto-Generated Workspace README:** Meti ensures that a clean `workspace/<project_id>/README.md` is generated upon task completion, containing architecture overviews, quickstart run commands, and validation instructions.
- **Workspace File Tree:** Renders a clean `rich.tree.Tree` showing generated project files while filtering noisy build artifacts (`__pycache__`, `.git`, `.venv`).
- **How to Run & Test Banner:** Displays prominent quickstart commands based on the detected project stack (e.g. Python, Node.js, Rust, Go).

## Resume a task

The CLI creates a permanent task ID before routing and prints it for later use. Each run is saved in a local SQLite ledger at `.state/tasks.db`. If a workflow fails or is interrupted, resume it from the same repository root:

```bash
python main.py --resume task-build-csv-validator-20261024
```

Replace the example ID with the one printed by your run. Resume reuses the saved prompt, project ID, stage outputs, and workspace. Do not supply a new prompt or `--project` together with `--resume`.

The ledger tracks `PENDING`, `RESEARCHING`, `ARCHITECTING`, `IMPLEMENTING`, `COMPLETED`, and `FAILED`. Completed routing, research, and specification outputs are reused. During implementation, validated phases are skipped and prior validation history is retained. A resumed task that proceeds to execution starts a new numbered run with a fresh three-attempt budget for unfinished phases. A completed task returns without calling a model or rerunning agents.

Command checkpoints are saved before execution and after results are recorded. If interruption happens between those points, the CLI reports the command's outcome as unknown. Inspect the workspace and any external side effects before resuming; a container may still be running after an abrupt process exit. An unfinished command or stage may execute again. Resume does **not** guarantee exactly-once execution or restore the entire model conversation; Meti receives the saved plan, validation history, and interrupted-command information in a fresh conversation.

Back up `.state/`, the corresponding task workspace, and `vault/` together when no workflow is running. Git does not back up the ignored ledger, workspaces, or generated notes. The ledger stores prompts, structured stage outputs, and validation logs locally; it does not replace the generated workspace or vault files. A missing workspace after implementation has begun causes resume to fail rather than silently discard saved work. Only tasks created with the ledger can be resumed; older vault artifacts are not imported automatically. Local per-task locks prevent concurrent CLI runs of the same task and release when the process exits. Unknown IDs and unreadable checkpoints fail explicitly.

## Keep related tasks connected

Reuse a project ID across requests:

```bash
python main.py "Design a SQLite-backed task tracker" --project task-tracker
python main.py "Build a CSV import utility for a task tracker" --project task-tracker
```

BuildRelay creates `vault/projects/task-tracker.md` if needed and preserves existing project-note content. Produced briefs, reports, specifications, and implementation reviews include a visible project link and frontmatter:

```yaml
project: "[[projects/task-tracker]]"
```

Project IDs accept letters, digits, underscores, and hyphens, and must start with a letter or digit. Project grouping links the notes and codebases: tasks sharing a project ID share the same workspace (`workspace/<project_id>/`), allowing successive tasks to build upon existing project modules and tests. Resumed runs reuse that task's workspace. Standalone tasks without a project ID use `workspace/<task_id>/`.

<img src="docs/diagrams/saved-data.svg" alt="Stage notes connect to project notes and Graphify; the SQLite ledger saves resume progress, and Docker writes generated code to workspaces." width="760">

Open **`vault/` as an Obsidian vault** to browse the notes and project wikilinks. Those links work independently of Graphify.

Graph updates are attempted after stage artifacts are saved. Graphify Markdown extraction requires its own supported backend; if extraction fails, BuildRelay logs a warning and continues with saved notes. Without a usable graph, knowledge queries may return no context.

### Research source references

Odin records nodes retrieved from its initial task lookup and its search and neighbor-query tools. Search matches node IDs, labels, source-file paths, and properties. Each saved research report includes a **Related vault sources** section with relative Markdown links and corresponding wikilinks in its `links` frontmatter.

Source paths come from Graphify's `source_file` metadata, including that field inside `properties` when present. Only existing Markdown files inside the vault are listed; duplicate paths are removed, and missing files or paths outside the vault are omitted. The returned `ResearchReport.vault_sources` contains the same vault-relative paths, overriding any model-generated list.

These references identify retrieved graph context. They do not establish that the full source notes were read or that each finding is supported by a particular note. If no source files can be resolved, the report states that explicitly. Graph extraction still requires a working Graphify backend.

## What stays on disk

Each new task gets a permanent ID shaped like `task-<prompt-slug>-YYYYMMDD` (e.g. `task-build-csv-validator-20261026`). The slug is derived from the prompt before any model call; resume keeps the same ID.

```text
.state/tasks.db                      Local workflow ledger and checkpoints
.state/<task_id>.lock                Local process lock file (may remain after exit)
workspace/<project_or_task_id>/       Generated source, tests, docs, dependencies
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

- Each command runs in a **fresh Docker container**, with the project or task workspace mounted at `/app/workspace/<project_or_task_id>/`.
- Files in that mount persist across commands. Container-local installs and changes outside it do not; keep durable dependencies in the mounted directory.
- Each phase must pass its **exact validation command**, submitted separately with its phase name, in the declared order. Successful command exit codes are recorded as validation results.
- Failed phase validation returns combined stdout/stderr to Meti with the remaining attempt count. Meti can repair and rerun the same check, up to **three validation attempts per phase per run** (one initial attempt and two retries). The third failure stops execution before more sandbox commands or later phases.
- Straightforward tasks receive a fast-track phase that asks Meti to create and run a task-specific validation script.
- The runner defaults to a **120-second wait timeout** per command and removes the container after execution.

### Recovery and attempt history

When a validation command fails, Meti receives its output and can issue repair commands before retrying that phase. Rejected calls with the wrong phase or validation command do not consume an attempt. Running an exact declared validation command without its phase name is rejected. Repair commands are separate from the three-attempt validation budget.

If the model returns a final response while a failed phase still has attempts remaining, the application sends the failure logs back into the same conversation. If that recovery round returns without another validation attempt, the run ends as failed rather than repeatedly asking without progress. Model-run errors and retry exhaustion also produce a failed review note.

The review note records each phase's attempt number, command, exit code, captured output, and final resolution: passed, passed on retry, retry limit exhausted, stopped early, or not validated. Docker wait/execution errors preserve available container logs; image acquisition errors return failure feedback. This is bounded recovery within a run; `--resume` reuses saved progress and starts a new run budget. Neither mechanism guarantees that an autonomous repair will succeed.

## Brand assets

The selected logo is **Forward B**, an orange BuildRelay monogram. Use [the canonical SVG](docs/brand/logo.svg) for the README, website, and icon applications. See [brand usage](docs/brand/README.md) for sizing and color guidance.

## Component connections

<img src="docs/diagrams/components.svg" alt="Main coordinates model setup, agents, and the task ledger. Agents use vault tools, shared contracts, and Meti’s Docker runner." width="760">

Arrows show which component uses another. Shared contracts define stage outputs, handoffs, and checkpoints used by orchestration, agents, and the ledger. Vault tools support graph lookup and project-note links; each agent saves its own stage artifacts.

## Repository map

```text
.
├── main.py                    CLI, task IDs, routing, and orchestration
├── contracts/
│   └── __init__.py            Shared typed checkpoints, stage outputs, and handoff contracts
├── agents/
│   ├── natasha.py             Structured briefs and routing
│   ├── odin.py                Research reports
│   ├── taghi.py               Specifications and execution phases
│   ├── execution_policy.py    Phase validation ordering, retry budgets, and recovery policy
│   ├── review_renderer.py     Markdown code review report rendering
│   └── meti.py                Implementation coordination and Docker tools
├── tools/
│   ├── chatgpt_auth.py        OAuth credential storage and model setup
│   ├── context_pruner.py      Markdown stripping, graph context ranking, and Docker log slicing
│   ├── docker_runner.py      Container lifecycle and workspace mounts
│   ├── graphify_tool.py      Graph extraction, node search, and neighbors
│   ├── model_tiers.py        Tiered routing presets, budget estimation, and lead overrides
│   ├── project_notes.py      Project IDs, note creation, and shared links
│   ├── task_ledger.py        SQLite checkpoints and per-task process locks
│   ├── token_analytics.py    Token usage tracking, model pricing, and summary tables
│   ├── ui.py                  Terminal styling, agent color badges, panels, and phase tables
│   └── vault_infra.py        Safe Markdown writing, graph tool wiring, and graph updates
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
- **Authentication fails:** verify that direct API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `GEMINI_API_KEY`) are present in `.env` or system environment, or complete the ChatGPT OAuth flow in your browser on first run. If using OAuth, verify that the authorization callback finishes and the credentials file is readable (defaulting to `.env.chatgpt-auth.json` or configured via `CHATGPT_AUTH_FILE`).
- **Graph extraction fails:** inspect the logged Graphify error. Extraction runs as `python -m graphify extract <vault>` using the CLI's Python interpreter, with `GRAPHIFY_OUT` pointing to `vault/.graphify`. Each extraction has a 300-second timeout. Saved Markdown remains available if extraction fails.
- **Dependencies disappear between commands:** install them inside the mounted task directory. Each command starts a new container.
- **Implementation reports failure:** inspect `vault/code-reviews/review-<task_id>.md` and terminal output. A phase is recorded only when its exact validation command exits successfully with the expected phase name.
- **Unknown task ID on resume:** run from the same repository root and use the permanent ID printed by the CLI. Confirm the original `.state/tasks.db` is present; older tasks created before the ledger cannot be resumed automatically.
- **Saved workspace is missing:** restore `workspace/<project_id>/` (or `workspace/<task_id>/`) from the same backup as the ledger. A checkpoint records progress, not a copy of generated source files.
- **Task is already running:** another CLI process holds the task lock. Let it finish or stop that process; a leftover `.lock` file alone does not mean the lock is held. Do not delete lock files to bypass a running task.
- **Interrupted command outcome is unknown:** inspect the existing files, running containers, and external side effects before resuming. Commands may have partially completed and can run again.
- **Invalid checkpoint:** preserve the original ledger and restore a consistent backup if available. Do not edit phase completion flags to force a resume; start a new task if the checkpoint cannot be recovered.
- **A linked note is missing:** research and specification notes exist only when their stages run. New briefs use permanent task IDs; older artifacts may still contain unresolved temporary brief links.

## Security and isolation boundaries

BuildRelay protects host credentials and filesystem integrity through multiple layers of sandboxing:

- **Credential & API Key Isolation:** Docker containers executed by Meti do **not** inherit host environment variables. Host API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, etc.) are never passed to containers. Running `env`, `printenv`, or inspecting process environments inside the container reveals only standard container defaults.
- **Workspace Containment:** Docker containers mount strictly the target task or project workspace (`workspace/<task_id>/` or `workspace/<project_id>/`) to `/app/workspace/<task_id>/`. The host project root, `.env`, `.git/`, and `.state/` directories are **never mounted**. Path traversal via task IDs is blocked by strict regex validation (`^[A-Za-z0-9][A-Za-z0-9_-]*$`) and filesystem root containment checks.
- **Agent Tool Boundaries:** Host-level agents (Natasha, Odin, Taghi) operate with read-only Obsidian vault graph queries and safe Markdown note writers. They have no terminal, shell, or arbitrary filesystem access.
- **Safe Vault Artifact Writing:** Stage artifacts are written using `safe_write_markdown`, which rejects directory traversal (`..`) and strictly enforces file confinement within designated vault directories (`tasks/`, `research/`, `specs/`, `code-reviews/`).
- **No Host Execution:** The host Python application never runs `eval()`, `exec()`, or `subprocess` on generated user code from `workspace/`. All compilation, execution, and tests occur strictly inside Docker containers.
- **Credential Storage Security:** `.env` and `.env.*` (including `.env.chatgpt-auth.json`) are ignored by Git. The interactive onboarding wizard (`tools/onboarding.py`) and OAuth credential flows enforce atomic file writes with strict `0o600` permissions (readable and writable only by the owner). Host credentials are never mounted into containers or stored in global locations.

## Development and documentation

The installed distribution provides the console script entry point `buildrelay` (e.g. `buildrelay "prompt"` or `buildrelay config`), or you can run directly from the checkout with `python main.py`. Runtime dependencies and Python requirements are declared in [pyproject.toml](pyproject.toml); dependency versions are lower bounds rather than a locked environment.

The agent classes can also be called directly with a `model_name` (model string or Pydantic AI model object) and a `vault_path`. Agents support explicit dependency injection: `graph_manager`, custom artifact storage directories (`tasks_dir`, `research_dir`, `specs_dir`, `code_reviews_dir`), and `MetiImplementer` additionally accepts custom `sandbox` runners (e.g. `DockerSandboxRunner` or mock test runners). Constructors defer Docker connections and directory creation until operations actually require them. Programmatic Meti calls can supply `checkpoint`, `checkpoint_callback`, and a new `run_number` to persist and restore implementation progress; the CLI connects these to the ledger automatically. The CLI supplies one model to every stage; these constructor options are not CLI flags.

### Testing

Install the test extra and run the local validation command from the repository root:

```bash
python -m pip install -e '.[test]'
python scripts/validate.py
```

The script runs the platform tests in `tests/` (173 passing unit tests); extra pytest arguments can be appended, for example `python scripts/validate.py -k validation`. Test discovery excludes generated workspaces. The suite uses Pydantic AI `TestModel` for structured outputs and `FunctionModel` for scripted tool calls, blocks real model requests, replaces Docker and graph extraction, and writes artifacts in temporary directories. It covers routing contracts, project links, explicit dependency injection, graph retrieval, source resolution and report references, phase validation, bounded recovery, container isolation invariants, Docker failure feedback, ledger persistence, and resume behavior; it does not assess live model routing quality.

The [Platform tests workflow](.github/workflows/tests.yml) runs the same validation command on pushes and pull requests using Ubuntu with Python 3.11 and 3.14. Open [CI results](https://github.com/Dutch-panda/BuildRelay/actions/workflows/tests.yml) to inspect runs. To start a manual run, select **Run workflow**, choose a branch, and confirm. Results and failure logs appear on the commit or pull request; no model credentials or Docker service are needed. Requiring passing checks before merging is a separate repository setting.

An end-to-end run still requires model access and Docker and writes local artifacts; review generated output before using it.

Documentation has two roles:

- This README describes the implemented platform and its operational limits.
- `vault/` and `workspace/` contain local run artifacts and examples. Historical reports describe individual runs, not guaranteed platform capabilities. They are not the public platform manual.

## Current limitations

BuildRelay is version **0.1.0**. These details matter when interpreting its output:

- **Optional stage links:** specification and review frontmatter can link to skipped stages; a wikilink does not guarantee its target exists.
- **Container isolation:** network access is enabled, the task directory is writable, and the runner does not configure CPU or memory limits.
- **Validation scope:** phase completion reflects command exit codes. It does not independently establish test quality or provide a separate human code review.

<div align="center">

<sub>Built with Python · Pydantic AI · Docker · Markdown · Graphify</sub>

</div>
