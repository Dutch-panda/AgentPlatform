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
- **Sequential 4-lead flow**: Natasha (Routing) → Odin (Research) → Taghi (Architecture) → Meti (Phased Docker Execution).
- **Shared Contracts**: All stage inputs, outputs, attempts, and checkpoints live in `contracts/`. Do not introduce circular dependencies between agents.
- **Meti Architecture**:
  - `agents/meti.py`: Implementation coordinator and Docker tool binding.
  - `agents/execution_policy.py`: Phase validation ordering, retry budgets (3 attempts per phase per run), recovery prompts, and ground-truth result finalization.
  - `agents/review_renderer.py`: Pure Markdown code-review report rendering.
- **Ledger & Persistence**: Stored locally in SQLite at `.state/tasks.db`. Checkpoints are validated with `ImplementationCheckpoint.validate_plan_consistency`.
- **Workspaces**: Generated code lives in `workspace/<project_id>/` (or `workspace/<task_id>/`).
- **Security & Vault Isolation**: Docker containers execute without host environment variables passed and only mount the task workspace. Vault notes and graph tools are registered and written strictly through `tools/vault_infra.py` safe writers.
- **Terminal UI & Diagnostics**: Console visuals use `rich` via `tools/ui.py` for role-based badges (Natasha, Odin, Taghi, Meti), panels, and phase tables. Diagnostic tool calls are subdued, and Graphify subprocess stderr is suppressed unless `BUILDRELAY_DEBUG=1` is set.

## Testing & Verification
- Run tests using `.venv/bin/pytest` or `.venv/bin/python scripts/validate.py`.
- Preserve the 3-attempt validation retry budget per phase.
- Deterministic unit tests mock external services (Docker, Graphify, model calls).
