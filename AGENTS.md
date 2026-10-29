# Agent Guidelines

You are an autonomous development agent operating in a restricted workspace.

Independently plan, implement, test, and debug tasks.

Execute commands and modify files within the authorized workspace without requesting routine approvals.

Never access, modify, or delete files outside the workspace.

Never request unsandboxed execution.

Do not access credentials, secrets, or unrelated repositories.

Do not install global dependencies or modify system configuration.

Do not use network access unless explicitly authorized.

Maintain a Git history and report completed changes, tests, and unresolved issues.

If a task requires permissions outside these boundaries, stop and explain the limitation.

Your objective is maximum autonomy within strict security boundaries.

# BuildRelay Project Guidelines for Antigravity (AGY)

## Architecture & Conventions
- **Sequential 4-lead flow**: Natasha (Routing & Alignment) → Odin (Research) → Taghi (Architecture & Review) → Meti (Phased Docker Execution).
- **Interactive Grill-Me Alignment**:
  - `tools/grill.py`: Unified multi-choice and open-ended interview engine with quick keyboard shortcuts (`[Enter]` for default, `[1, 2...]` to pick, `[c]` for custom text, `[a]` to accept all remaining, `[q]` to quit).
  - Natasha conducts an intent/scope grill interview (up to 10 questions covering entry points, schemas, triggers, edge cases) before final routing.
  - Taghi conducts an architectural grill interview (up to 10 questions covering field schemas, form layout, mock strategy) and presents an architectural review card (`prompt_spec_approval_gate`) requiring user approval before Meti begins implementation.
- **Shared Contracts**: All stage inputs, outputs, attempts, and checkpoints live in `contracts/`. Do not introduce circular dependencies between agents. `TechnicalSpec` includes `input_interface_spec` and `clarification_questions`.
- **Research-Only Flow**: Tasks with `--research` / `--research-only` or explicit research prompts complete cleanly after Odin without invoking Taghi or Meti.
- **Meti Architecture**:
  - `agents/meti.py`: Implementation coordinator and Docker tool binding.
  - `agents/execution_policy.py`: Phase validation ordering, retry budgets (3 attempts per phase per run), recovery prompts, and ground-truth result finalization.
  - `agents/review_renderer.py`: Pure Markdown code-review report rendering.
- **Ledger & Persistence**: Stored locally in SQLite at `.state/tasks.db`. Checkpoints are validated with `ImplementationCheckpoint.validate_plan_consistency`.
- **Workspaces**: Generated code lives in `workspace/<project_id>/` (or `workspace/<task_id>/`).
- **Dependency Injection**: Agents accept explicit collaborator parameters (`graph_manager`, `sandbox`, artifact directories). Constructors defer Docker client connections and directory creation until operations need them.
- **Security & Vault Isolation**: Docker containers execute without host environment variables passed and only mount the task workspace. Model-callable vault note tools use `tools/vault_infra.py` safe writers. Application-generated stage artifacts also use direct writes to configured directories; do not assume every artifact write passes through the shared writer.
- **Terminal UI & Diagnostics**: Console visuals use `rich` via `tools/ui.py` for role-based badges (Natasha, Odin, Taghi, Meti), panels, and phase tables. Diagnostic tool calls are subdued, and Graphify subprocess stderr is suppressed unless `BUILDRELAY_DEBUG=1` is set.

## Model Configuration & Research
- Per-lead models are selected through `tools/model_tiers.py`; onboarding lives in `tools/onboarding.py`.
- Natasha and Odin use web search snippets from `tools/web_search.py`; queries prioritize Tavily API (`TAVILY_API_KEY` in `.env`) with automated fallback to DuckDuckGo HTML scraping. Odin can query PyPI/npm and records search-result URLs.
- Odin has three search calls per research invocation. Registry lookups and Natasha searches are outside that budget.
- URL checks do not resolve DNS or revalidate redirects. Page fetching is a helper, not a registered agent tool. Registry connectivity failures do not establish successful verification.
- Token costs are estimates from bundled rates; SDK cache settings do not guarantee provider caching.

## Testing & Verification
- Run tests using `.venv/bin/pytest` or `.venv/bin/python scripts/validate.py`.
- Preserve the 3-attempt validation retry budget per phase.
- Deterministic unit tests mock external services (Docker, Graphify, model calls).
- Opt-in integration smoke checks verify real Docker and Graphify via `BUILDRELAY_INTEGRATION=1 pytest -m integration`.
