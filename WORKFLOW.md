---
# ==============================================================================
# SYMPHONY ENGINE CONFIGURATION (YAML Front Matter)
# ==============================================================================

# 1. Orchestration Substrate & Concurrency
version: "1.0"
engine: "symphony-lite"
concurrency_limit: 2       # Maximum number of concurrent isolated agent sessions
poll_interval_seconds: 30  # Cadence for ticking the project tracker board

# 2. Issue Tracker Layer Configuration
tracker:
  kind: "linear"           # Can be "linear", "github_projects", or "markdown"
  project_slug: "Symphony-Lite-Demo"
  active_states:
    - "Todo"
    - "Rework"
  progress_state: "In Progress"
  review_state: "Human Review"
  terminal_states:
    - "Done"
    - "Closed"

# 3. Isolated Workspace Settings
workspace:
  root: "~/.symphony_workspaces"
  clean_on_terminal: true   # Wipe the ephemeral folder when moved to Done/Closed
  prevent_traversal: true   # Security check against symlink path escapes

# 4. Lifecycle Quality Gate Hooks
hooks:
  # Triggered immediately upon checking out a dedicated workspace per issue
  after_create:
    - "git clone https://github.com/rikbon/symphony_lite.git ."
    - "git checkout -b sym/issue-{{ issue.identifier }}"
  
  # Triggered prior to dispatching a turn to the coding agent
  before_turn:
    - "git fetch origin main"
    - "git rebase origin/main || (git rebase --abort && exit 1)"
  
  # Quality gate execution after the agent claims a turn is finished. 
  # Non-zero exits force a rollback/retry up to max turns.
  after_turn:
    - "npm install"
    - "npm run lint"
    - "npm run test"

# 5. Agent Model Parameters
agent:
  provider: "openai"
  model: "gpt-4o"
  max_turns_per_issue: 5    # Hard stop to prevent autonomous infinite loops
  temperature: 0.1

---

# ==============================================================================
# AGENT EXECUTION INSTRUCTIONS (Markdown Prompt Template)
# ==============================================================================

## Executive Directive
You are an autonomous senior software engineer operating via the OpenAI Symphony specification. You have been assigned to resolve the following issue completely independent of interactive human supervision. 

### Issue Context
* **Identifier:** {{ issue.identifier }}
* **Title:** {{ issue.title }}
* **Priority:** {{ issue.priority }}
* **Target Branch:** `sym/issue-{{ issue.identifier }}`

### Problem Description
{{ issue.description }}

---

## Required Execution Flow

### Step 1: Initialize the Workpad
Before modifying application source files, you MUST find or create an active issue status tracking block in the tracker platform called the **Codex Workpad**.
1. Look for a comment header titled `## Codex Workpad`. If it does not exist, initialize it.
2. Inject an environment stamp at the top of the workpad containing your environment metadata: 
   ```text
   [WORKPAD STAMP] HOSTNAME:WORK_DIR@SHORT_SHA
Break the issue down into a strict checklist of granular steps, actionable Acceptance Criteria, and a deterministic Verification/Testing plan.

Step 2: Implement and Build
Write clean, self-documenting code following the existing paradigms within the symphony_lite architecture.

Keep your scope tightly constrained to the parameters outlined in the problem description. Do not rewrite unrequested modules.

Step 3: Self-Review & Quality Gates
Before notifying the orchestrator that you are done, run the repository test suite and validation scripts locally.

Fix any compilation, linting, or testing regressions you introduced.

If you find yourself blocked or encounter ambiguities that cannot be resolved safely, document your findings explicitly under a ### Confusions header in the Workpad, abort execution safely, and request human intervention.

Step 4: Finalize and Hand Off
Once the task is fully validated:

Update your Workpad checklist confirming all criteria are satisfied.

Commit your code using standard semantic commit messaging conventions.

Open a Pull Request referencing the issue ID and push back proof-of-work (e.g., test suite output, impacted areas).

Relinquish control back to Symphony so it can transition the ticket status to Human Review.
