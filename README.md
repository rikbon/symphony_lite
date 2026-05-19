# 🎼 Symphony-Lite

> **A minimal orchestrator for autonomous coding agents**, inspired by [OpenAI's Symphony](https://github.com/openai/symphony).

[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![SPEC Compliance](https://img.shields.io/badge/Symphony%20SPEC-~70%25-blueviolet)](https://github.com/openai/symphony/blob/main/SPEC.md)
[![Agent](https://img.shields.io/badge/Agent-Gemini%20CLI%20%7C%20OpenCode-orange)](https://github.com/google-gemini/gemini-cli)

---

## Table of Contents

- [What is Symphony-Lite](#what-is-symphony-lite)
- [Inspiration: OpenAI Symphony](#inspiration-openai-symphony)
- [Philosophy & Differences](#philosophy--differences)
- [How it Works](#how-it-works)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [CLI Reference](#cli-reference)
- [WORKFLOW.md / GEMINI.md](#workflowmd--geminimd)
- [Architecture](#architecture)
- [SPEC Compliance](#spec-compliance)
- [Roadmap](#roadmap)
- [License](#license)
- [Links](#links)

---

## What is Symphony-Lite

**Symphony-Lite** is a lightweight Python orchestrator that automates the full lifecycle of an AI coding agent. Given a Git repository URL and a task description, it:

1. **Isolates** work by cloning the repo into a dedicated per-task workspace and creating a unique Git branch — with **workspace reuse** across runs of the same task.
2. **Loads** `WORKFLOW.md` or `GEMINI.md` from the repository, parsing YAML front matter into a typed runtime config.
3. **Validates** configuration before dispatching (preflight validation).
4. **Runs** lifecycle hooks (`after_create`, `before_run`, `after_run`).
5. **Delegates** the task to the chosen CLI agent (Gemini or OpenCode) with a structured prompt and timeout.
6. **Retries** automatically on failure using exponential backoff.
7. **Prepares the handoff** by committing changes to the isolated branch, ready for a Pull Request.

The goal: shift from *supervising* AI sessions to *managing work* at a higher level — the core vision of OpenAI's Symphony.

---

## Inspiration: OpenAI Symphony

[Symphony](https://github.com/openai/symphony) is an open-source framework by OpenAI that redefines the relationship between engineers and AI agents. It emerged from a practical observation: **developers hit a human attention bottleneck** when managing more than 3–5 concurrent AI coding sessions.

### The Problem

Traditional agent interaction is *synchronous and supervised*: open a session, write a prompt, monitor progress, correct, relaunch. This doesn't scale beyond a handful of sessions.

### Symphony's Solution

Symphony introduces a **control plane** that:
- Integrates an **issue tracker** (Linear) as the source of truth for work.
- **Spawns isolated agents** per issue, each in its own workspace.
- Requires **Proof of Work**: CI green, code review feedback, walkthrough video.
- **Automatically handles failures**: stalled or crashed agents are restarted.

> *"Engineers managing work, not AI sessions."*

### Key Components

| Component | Description |
|---|---|
| `SPEC.md` | Language-agnostic formal protocol spec |
| Elixir Implementation | Reference impl using Elixir/BEAM for concurrency & fault tolerance |
| Linear Integration | Automatic board monitoring to acquire new tasks |
| Proof of Work | CI status, PR review, complexity analysis, walkthrough video |
| Harness Engineering | Making codebases machine-legible and self-verifiable |

**Languages in the original repo:** Elixir (95.5%), Python (3%), CSS (1.2%)

---

## Philosophy & Differences

| Aspect | Symphony (OpenAI) | Symphony-Lite |
|---|---|---|
| **Complexity** | Distributed, Elixir/BEAM | Single-file Python script |
| **PM Integration** | Linear board, webhooks | `--task` CLI flag |
| **Parallelism** | Dozens of concurrent agents | One task at a time |
| **Proof of Work** | CI, PR review, walkthrough video | Agent exit code + project tests |
| **Failure handling** | BEAM supervision tree | Try/finally + exponential backoff |
| **Target** | Enterprise engineering teams | Individual devs / small teams |
| **Agents supported** | Codex (OpenAI) | Gemini CLI, OpenCode |
| **Workspace** | Per-issue, persisted | Per-issue, reused across runs |
| **Config** | `WORKFLOW.md` + YAML | `WORKFLOW.md` / `GEMINI.md` + YAML |

---

## How it Works

### Phase 1 — Workspace Setup (with Reuse)

```bash
# First run: clone + create branch
git clone <repo_url> symphony_workspaces/<task-id>
git checkout -b symphony/<task-id>

# Subsequent runs: reuse existing workspace (SPEC §9.1)
git fetch origin
git checkout symphony/<task-id>
```

Workspaces are **never destroyed** between runs of the same task.

### Phase 2 — Config & Validation

Reads `WORKFLOW.md` or `GEMINI.md`, extracts YAML front matter into a typed `ServiceConfig`, resolves `$ENV_VAR` references, and runs **preflight validation** before dispatching.

### Phase 3 — Hooks + Agent Execution

```
[after_create]  → runs only when workspace is newly created
[before_run]    → runs before each agent attempt
    gemini -y "<prompt>"   OR   opencode run "<prompt>"
[after_run]     → runs after each attempt (even on failure)
```

The prompt is built from the `WORKFLOW.md` body template with `{{ task }}` and `{{ attempt }}` variables.

### Phase 4 — Retry + Handoff

On failure, retries with exponential backoff:
```
delay = min(10000ms × 2^(attempt-1), max_retry_backoff_ms)
```
On success, changes are committed to the isolated branch, ready for push and PR.

---

## Requirements

- **Python** 3.9+
- **Git** on PATH
- At least one CLI agent:
  - [`gemini`](https://github.com/google-gemini/gemini-cli) *(default)*
  - [`opencode`](https://github.com/sst/opencode) *(via `--opencode`)*
- **PyYAML** *(optional)*: `pip install pyyaml` — needed for YAML front matter parsing

### Target Repository

Should follow **Harness Engineering** principles with a `WORKFLOW.md` or `GEMINI.md` documenting:
- Dependency installation commands
- Linting / formatting commands
- Test suite execution commands

---

## Installation

```bash
git clone https://github.com/<your-user>/symphony_lite.git
cd symphony_lite

# Optional: virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/macOS

# Install the package globally in editable mode
pip install -e .

# Optional: YAML front matter support (already included if you install via pip above)
# pip install pyyaml
```

---

## Usage

### Basic (Gemini CLI)

```bash
symphony-lite \
  --url https://github.com/your-org/your-repo.git \
  --task "Add email validation to the registration form" \
  --id feat-email-validation
```

### With OpenCode

```bash
symphony-lite \
  --url https://github.com/your-org/your-repo.git \
  --task "Fix bug #42: NullPointerException in CSV parser" \
  --id fix-42 \
  --opencode
```

### No retry + verbose logging

```bash
symphony-lite \
  --url https://github.com/your-org/your-repo.git \
  --task "Refactor the authentication module" \
  --id refactor-auth \
  --no-retry --verbose
```

### Expected output

```
10:30:01 [INFO    ] ============================================================
10:30:01 [INFO    ]   Symphony-Lite — Starting
10:30:01 [INFO    ]   Repo  : https://github.com/your-org/your-repo.git
10:30:01 [INFO    ]   Task  : Add email validation to the registration form
10:30:01 [INFO    ]   Branch: symphony/feat-email-validation
10:30:01 [INFO    ] ============================================================
10:30:01 [INFO    ] Preflight validation: OK
10:30:03 [INFO    ] [Workspace] Cloning repository...
10:30:08 [INFO    ] Workflow loaded from: WORKFLOW.md

[Symphony] Starting agent (attempt 1)...
------------------------------------------------------------
... (agent output) ...
------------------------------------------------------------
[Symphony] Agent completed successfully.

[DONE] Task complete! Branch: 'symphony/feat-email-validation'
       Run: git push origin symphony/feat-email-validation  (then open a PR)
```

---

## CLI Reference

| Flag | Alias | Required | Default | Description |
|---|---|---|---|---|
| `--url` | `-u` | ✅ | — | Git repository URL to clone |
| `--task` | `-t` | ✅ | — | Task description for the agent |
| `--id` | `-i` | ❌ | `task-auto` | Unique task ID → branch `symphony/<id>` |
| `--opencode` | — | ❌ | `False` | Use OpenCode instead of Gemini CLI |
| `--no-retry` | — | ❌ | `False` | Disable automatic retry on failure |
| `--verbose` | `-v` | ❌ | `False` | Enable debug-level logging |

---

## WORKFLOW.md / GEMINI.md

This file is the repository's **harness**: the configuration source for Symphony-Lite and the document the agent reads to operate autonomously.

### YAML Front Matter Schema

```yaml
---
workspace:
  root: ./symphony_workspaces   # or $SYMPHONY_WORKSPACE_ROOT

agent:
  max_turns: 20
  max_retry_backoff_ms: 300000  # 5 minutes

codex:
  command: gemini               # or opencode / $AGENT_CMD
  turn_timeout_ms: 3600000      # 1 hour

hooks:
  after_create: |
    pip install -r requirements.txt
  before_run: |
    git pull origin main --rebase
  after_run: |
    echo "Run completed"
  timeout_ms: 60000
---
```

### Prompt Template Body

The Markdown body below the front matter becomes the agent prompt. Supported variables:

| Variable | Description |
|---|---|
| `{{ task }}` | Task description from `--task` |
| `{{ attempt }}` | Current attempt number |

### Minimal WORKFLOW.md (no front matter)

```markdown
## Setup
pip install -r requirements.txt

## Linting
ruff check . --fix && black .

## Tests
pytest tests/ -v

## Rules
- Every new feature must have at least one unit test.
- Code must pass linting before committing.
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        symphony_lite.py                       │
│                                                              │
│  Workflow Loader (§5) ──▶ Config Layer (§6.1)               │
│                                   │                          │
│                        Preflight Validation (§6.3)           │
│                                   │                          │
│                     Workspace Manager (§9)                   │
│              per-issue path · clone/fetch · reuse            │
│                                   │                          │
│                       Hook Runner (§5.3.4)                   │
│           after_create → before_run → agent → after_run      │
│                                   │                          │
│              Agent Runner + Retry (§3.1, §7.2, §8.4)        │
│         RunState machine · timeout · exponential backoff     │
│                                   │                          │
│                          Handoff                             │
│                git add · commit · branch → PR                │
└──────────────────────────────────────────────────────────────┘
```

### Error Handling

| Scenario | Behavior |
|---|---|
| Git clone fails | Hard abort |
| `WORKFLOW.md` missing | Warning + default config |
| YAML parse error | Error logged + default config |
| Preflight fails | Hard abort (exit 1) |
| `after_create`/`before_run` hook fails | Hard abort |
| `after_run` hook fails | Error logged, execution continues |
| Agent timeout | `TIMED_OUT` state, retry scheduled |
| Agent error | `FAILED` state, retry with backoff |
| All retries exhausted | Exit code 1 |
| Working directory | `finally` block always restores original cwd |

---

## SPEC Compliance

Compliance against [Symphony SPEC v1](https://github.com/openai/symphony/blob/main/SPEC.md):

| Component | SPEC § | Status |
|---|---|---|
| Workflow Loader (WORKFLOW.md + YAML front matter) | §5 | ✅ |
| Config Layer (typed + defaults + $VAR resolution) | §6.1 | ✅ |
| Preflight Validation | §6.3 | ✅ |
| Workspace Manager (per-issue + reuse, no destroy) | §9.1-9.2 | ✅ |
| Workspace key sanitization | §4.2 | ✅ |
| Hook system (after_create / before_run / after_run) | §5.3.4 | ✅ |
| Prompt template with variables | §5.4 | ✅ |
| Agent Runner with timeout | §5.3.6 | ✅ |
| Run Attempt lifecycle states | §7.2 | ✅ |
| Retry with exponential backoff | §8.4 | ✅ |
| Structured logging (Observability) | §3.1 | ✅ |
| Issue Tracker (Linear) | §3.1 | ❌ out of scope |
| Polling daemon loop | §8.1 | ❌ out of scope |
| Multi-agent concurrency | §8.3 | ❌ out of scope |
| `codex app-server` stdio protocol | §5.3.6 | ❌ out of scope |
| Dynamic WORKFLOW.md reload | §6.2 | ❌ out of scope |

**Estimated compliance: ~70%**

### What's Missing (Out of Scope for Local Use)

To reach 100% compliance, the following SPEC requirements would need to be implemented. They were deliberately excluded as they target enterprise/distributed environments rather than local development:
1. **Issue Tracker Integration (SPEC §3.1)**: Connecting directly to Linear (or others) to fetch "To Do" tasks and transition states.
2. **Polling Daemon Loop (SPEC §8.1)**: Running as a continuous background daemon that polls for new work every X seconds.
3. **Multi-Agent Concurrency (SPEC §8.3)**: Managing `max_concurrent_agents` running in parallel.
4. **`codex app-server` STDIO Protocol (SPEC §5.3.6)**: Communicating with the agent via a structured JSON protocol over stdio instead of a standard CLI execution.
5. **Dynamic Config Reload (SPEC §6.2)**: Hot-reloading `WORKFLOW.md` changes without restarting the orchestrator.

---

## Roadmap

- [ ] Multi-task support: sequential execution from JSON/YAML file
- [ ] Linear integration: automatic board polling for new issues
- [ ] Structured Proof of Work: parse test output, generate markdown report
- [ ] Slack/Discord notifications on task completion
- [ ] Docker support: fully isolated workspace via container
- [ ] Dynamic `WORKFLOW.md` reload without restart (SPEC §6.2)
- [ ] Web dashboard: monitor running and completed tasks

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Links

| Resource | Link |
|---|---|
| 🎼 Symphony (OpenAI) — GitHub | [github.com/openai/symphony](https://github.com/openai/symphony) |
| 📄 Symphony SPEC.md | [SPEC.md](https://github.com/openai/symphony/blob/main/SPEC.md) |
| 📖 OpenAI Blog | [openai.com/index/open-source-codex-orchestration-symphony/](https://openai.com/index/open-source-codex-orchestration-symphony/) |
| 🔧 Harness Engineering | [openai.com/index/harness-engineering/](https://openai.com/index/harness-engineering/) |
| 🤖 Gemini CLI | [github.com/google-gemini/gemini-cli](https://github.com/google-gemini/gemini-cli) |
| ⚡ OpenCode | [github.com/sst/opencode](https://github.com/sst/opencode) |

---

<p align="center">
  <em>Built with the Symphony philosophy: manage work, not sessions.</em>
</p>
