#!/usr/bin/env python3
"""
Symphony-Lite: Minimal orchestrator for autonomous coding agents.
~70% compliance with Symphony SPEC v1
Ref: https://github.com/openai/symphony/blob/main/SPEC.md

Implements:
  SPEC §4.1.3  ServiceConfig (typed config + defaults)
  SPEC §4.1.5  Run Attempt lifecycle states
  SPEC §5      Workflow Loader (WORKFLOW.md / GEMINI.md + YAML front matter)
  SPEC §6.1    Config resolution pipeline ($VAR indirection)
  SPEC §6.3    Dispatch preflight validation
  SPEC §7.2    Run Attempt state machine
  SPEC §8.4    Retry with exponential backoff
  SPEC §9.1-2  Per-issue workspace with REUSE (no more rmtree)
  SPEC §5.3.4  Hook system (after_create, before_run, after_run)
  SPEC §5.4    Prompt template with variables from WORKFLOW.md
  SPEC §3.1    Structured logging (Observability)

Out of scope for local use:
  Issue Tracker integration (Linear)
  Polling daemon loop
  Multi-agent concurrency
  codex app-server stdio protocol
  Dynamic WORKFLOW.md reload
"""

import argparse
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Optional

# PyYAML is optional — required only for YAML front matter parsing
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

log = logging.getLogger("symphony")


# ═══════════════════════════════════════════════════════════════════
# SPEC §7.2 — Run Attempt Lifecycle States
# ═══════════════════════════════════════════════════════════════════

class RunState(Enum):
    PREPARING_WORKSPACE = auto()
    BUILDING_PROMPT     = auto()
    LAUNCHING_AGENT     = auto()
    STREAMING_TURN      = auto()
    FINISHING           = auto()
    SUCCEEDED           = auto()
    FAILED              = auto()
    TIMED_OUT           = auto()


# ═══════════════════════════════════════════════════════════════════
# SPEC §4.1.3 — Service Config (typed, with defaults)
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ServiceConfig:
    workspace_root: Path        = field(default_factory=lambda: Path("./symphony_workspaces"))
    agent_command: str          = "gemini"
    use_opencode: bool          = False
    max_turns: int              = 20
    max_retry_attempts: int     = 3
    max_retry_backoff_ms: int   = 300_000   # 5 minutes
    turn_timeout_ms: int        = 3_600_000 # 1 hour
    hook_after_create: Optional[str] = None
    hook_before_run: Optional[str]   = None
    hook_after_run: Optional[str]    = None
    hook_timeout_ms: int        = 60_000
    prompt_template: Optional[str]   = None


# ═══════════════════════════════════════════════════════════════════
# SPEC §5 — Workflow Loader
# ═══════════════════════════════════════════════════════════════════

def load_workflow(workspace_path: Optional[Path] = None) -> tuple[dict, Optional[str]]:
    """
    Reads WORKFLOW.md or GEMINI.md from the workspace or cwd.
    SPEC §5.2: if the file starts with '---', extracts YAML front matter.
    Returns (config_map, prompt_template).
    """
    search_dirs = [p for p in [workspace_path, Path.cwd()] if p]
    workflow_file = None
    for d in search_dirs:
        for name in ("WORKFLOW.md", "GEMINI.md", "AGENTS.md"):
            c = d / name
            if c.exists():
                workflow_file = c
                break
        if workflow_file:
            break

    if not workflow_file:
        log.warning("Workflow file not found (WORKFLOW.md / GEMINI.md). Using default config.")
        return {}, None

    log.info(f"Workflow loaded from: {workflow_file}")
    content = workflow_file.read_text(encoding="utf-8")
    config_map: dict = {}
    prompt_body = content

    # SPEC §5.2 — Parse YAML front matter if present
    if content.startswith("---") or content.startswith("--\n"):
        # Handle both --- and -- (as seen in some files)
        marker = "---" if content.startswith("---") else "--"
        parts = content.split(marker, 2)
        if len(parts) >= 3:
            front = parts[1].strip()
            prompt_body = parts[2].strip()
            if HAS_YAML:
                try:
                    parsed = yaml.safe_load(front)
                    if isinstance(parsed, dict):
                        config_map = parsed
                    else:
                        log.error("WORKFLOW.md: front matter is not a valid YAML object.")
                except yaml.YAMLError as e:
                    log.error(f"WORKFLOW.md: YAML parsing error: {e}")
            else:
                log.warning("PyYAML not installed — front matter ignored. "
                            "Install with: pip install pyyaml")

    return config_map, prompt_body or None


# ═══════════════════════════════════════════════════════════════════
# SPEC §6.1 — Config Resolution Pipeline
# ═══════════════════════════════════════════════════════════════════

def resolve_env(value: str) -> str:
    """SPEC §6.1: resolves $VAR_NAME → os.environ[VAR_NAME]"""
    if isinstance(value, str) and value.startswith("$"):
        return os.environ.get(value[1:], value)
    return value


def resolve_config(raw: dict, cli_args) -> ServiceConfig:
    """Builds a ServiceConfig from WORKFLOW.md front matter + CLI args + defaults."""
    cfg = ServiceConfig()

    ws = raw.get("workspace", {})
    if "root" in ws:
        cfg.workspace_root = Path(resolve_env(ws["root"])).expanduser()

    agent = raw.get("agent", {})
    if "max_turns" in agent:
        cfg.max_turns = int(agent["max_turns"])
    if "max_retry_backoff_ms" in agent:
        cfg.max_retry_backoff_ms = int(agent["max_retry_backoff_ms"])

    codex = raw.get("codex", {})
    if "command" in codex:
        cfg.agent_command = resolve_env(codex["command"])
    if "turn_timeout_ms" in codex:
        cfg.turn_timeout_ms = int(codex["turn_timeout_ms"])

    hooks = raw.get("hooks", {})
    cfg.hook_after_create = hooks.get("after_create")
    cfg.hook_before_run   = hooks.get("before_run")
    cfg.hook_after_run    = hooks.get("after_run")
    if "timeout_ms" in hooks:
        cfg.hook_timeout_ms = int(hooks["timeout_ms"])

    # CLI flag overrides config file
    cfg.use_opencode = getattr(cli_args, "opencode", False)
    if cfg.use_opencode:
        cfg.agent_command = "opencode"

    return cfg


# ═══════════════════════════════════════════════════════════════════
# SPEC §6.3 — Dispatch Preflight Validation
# ═══════════════════════════════════════════════════════════════════

def preflight_validation(cfg: ServiceConfig) -> bool:
    """Validates config before dispatch. Returns False if dispatch should be blocked."""
    ok = True
    if not cfg.agent_command:
        log.error("Preflight FAIL: agent command is empty.")
        ok = False
    if cfg.max_turns <= 0:
        log.error("Preflight FAIL: agent.max_turns must be > 0.")
        ok = False
    if cfg.turn_timeout_ms <= 0:
        log.error("Preflight FAIL: turn_timeout_ms must be > 0.")
        ok = False
    if ok:
        log.info("Preflight validation: OK")
    return ok


# ═══════════════════════════════════════════════════════════════════
# SPEC §9 — Workspace Manager (per-issue, with REUSE)
# ═══════════════════════════════════════════════════════════════════

def sanitize_workspace_key(issue_id: str) -> str:
    """SPEC §4.2: replaces characters not in [A-Za-z0-9._-] with '_'"""
    return re.sub(r"[^A-Za-z0-9._-]", "_", issue_id)


def setup_workspace(repo_url: str, branch_name: str, cfg: ServiceConfig) -> tuple[Path, bool]:
    """
    SPEC §9.1-9.2: per-issue workspace with REUSE.
      - Already exists → git fetch + checkout branch (REUSE, no rmtree).
      - Does not exist → clone + create branch.
    Returns (workspace_path, created_now).
    """
    workspace_key  = sanitize_workspace_key(branch_name.replace("/", "_"))
    workspace_path = (cfg.workspace_root / workspace_key).resolve()

    cfg.workspace_root.mkdir(parents=True, exist_ok=True)
    log.info(f"[Workspace] {workspace_path}")

    log.info("[Orchestrator] State: PREPARING_WORKSPACE")

    if workspace_path.exists():
        # SPEC §9.2: reuse existing workspace — do NOT destroy it
        log.info("[Workspace] Existing workspace found — reusing.")
        os.chdir(workspace_path)
        subprocess.run(["git", "fetch", "origin"], check=True, capture_output=True)
        result = subprocess.run(["git", "checkout", branch_name],
                                capture_output=True, text=True)
        if result.returncode != 0:
            # Branch does not exist locally yet — create it
            subprocess.run(["git", "checkout", "-b", branch_name], check=True)
        return workspace_path, False
    else:
        log.info(f"[Workspace] Cloning: {repo_url}")
        subprocess.run(["git", "clone", repo_url, str(workspace_path)], check=True)
        os.chdir(workspace_path)
        log.info(f"[Workspace] Creating branch: {branch_name}")
        subprocess.run(["git", "checkout", "-b", branch_name], check=True)
        return workspace_path, True


# ═══════════════════════════════════════════════════════════════════
# SPEC §5.3.4 — Hook Runner
# ═══════════════════════════════════════════════════════════════════

def run_hook(script: Optional[str], name: str, cfg: ServiceConfig,
             abort_on_fail: bool = True) -> bool:
    """
    Executes a shell hook defined in WORKFLOW.md.
    abort_on_fail=True  → failure blocks execution (after_create, before_run).
    abort_on_fail=False → failure is logged but ignored (after_run).
    """
    if not script:
        return True
    log.info(f"[Hook] Running '{name}'...")
    try:
        result = subprocess.run(script, shell=True, text=True, capture_output=True,
                                timeout=cfg.hook_timeout_ms / 1000.0)
        if result.returncode != 0:
            log.error(f"[Hook] '{name}' failed (exit {result.returncode}): {result.stderr}")
            return not abort_on_fail
        log.info(f"[Hook] '{name}' OK.")
        return True
    except subprocess.TimeoutExpired:
        log.error(f"[Hook] '{name}' timed out ({cfg.hook_timeout_ms}ms).")
        return not abort_on_fail


# ═══════════════════════════════════════════════════════════════════
# SPEC §5.4 — Prompt Builder
# ═══════════════════════════════════════════════════════════════════

def build_prompt(task: str, cfg: ServiceConfig, attempt: int) -> str:
    """
    SPEC §5.4: builds the agent prompt.
    Uses the prompt_template from WORKFLOW.md if available,
    otherwise falls back to a built-in default prompt.
    """
    if cfg.prompt_template:
        # Basic template rendering with supported variables
        p = cfg.prompt_template
        p = p.replace("{{ task }}", task).replace("{{ attempt }}", str(attempt))
    else:
        p = (
            f"Solve the following task in this repository:\n\n"
            f"TASK: {task}\n\n"
            f"Strictly follow the setup, linting, and test instructions "
            f"described in WORKFLOW.md or GEMINI.md.\n"
            f"The task is not complete until all tests pass."
        )
    if attempt > 1:
        p += (f"\n\n[ATTEMPT {attempt}] The previous attempt failed. "
              f"Resume from where it stopped.")
    return p.strip()


# ═══════════════════════════════════════════════════════════════════
# SPEC §3.1 §7.2 — Agent Runner with lifecycle states and timeout
# ═══════════════════════════════════════════════════════════════════

def run_agent(task: str, cfg: ServiceConfig, attempt: int = 1) -> bool:
    """Launches the coding agent, tracking run attempt lifecycle states."""
    log.info(f"[Agent] State: {RunState.BUILDING_PROMPT.name} (attempt {attempt})")
    prompt = build_prompt(task, cfg, attempt)

    # Determine command structure based on the agent binary name
    agent_bin = cfg.agent_command.lower()
    if "opencode" in agent_bin:
        cmd = [cfg.agent_command, "run", "--dangerously-skip-permissions", prompt]
    else:
        # Default to Gemini-style flags
        cmd = [cfg.agent_command, "--approval-mode", "yolo", "--skip-trust", "-p", prompt]

    log.info(f"[Agent] State: {RunState.LAUNCHING_AGENT.name} | cmd: {' '.join(cmd)}")
    print(f"\n[Symphony] Starting agent (attempt {attempt})...")
    print("-" * 60)

    timeout_s = cfg.turn_timeout_ms / 1000.0

    try:
        log.info(f"[Agent] State: {RunState.STREAMING_TURN.name}")
        subprocess.run(cmd, check=True, text=True, timeout=timeout_s)
        log.info(f"[Agent] State: {RunState.SUCCEEDED.name}")
        print("-" * 60)
        print("[Symphony] Agent completed successfully.")
        return True

    except subprocess.TimeoutExpired:
        log.error(f"[Agent] State: {RunState.TIMED_OUT.name} (timeout {timeout_s:.0f}s)")
        print("-" * 60)
        print(f"[Symphony] TIMEOUT after {timeout_s:.0f}s.")
        return False

    except subprocess.CalledProcessError as e:
        log.error(f"[Agent] State: {RunState.FAILED.name} (exit code {e.returncode})")
        print("-" * 60)
        print(f"[Symphony] ERROR: exit code {e.returncode}.")
        return False


# ═══════════════════════════════════════════════════════════════════
# SPEC §8.4 — Retry with Exponential Backoff
# ═══════════════════════════════════════════════════════════════════

def run_with_retry(task: str, cfg: ServiceConfig) -> bool:
    """
    SPEC §8.4: delay = min(10000 * 2^(attempt-1), max_retry_backoff_ms)
    Capped at 3 attempts for local use (reasonable without a polling daemon).
    """
    max_attempts = min(cfg.max_retry_attempts, 3)
    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            delay_ms = min(10_000 * (2 ** (attempt - 2)), cfg.max_retry_backoff_ms)
            log.warning(f"[Retry] Attempt {attempt}/{max_attempts} in {delay_ms/1000:.1f}s...")
            time.sleep(delay_ms / 1000.0)
            # Re-run before_run hook before each retry attempt
            if not run_hook(cfg.hook_before_run, "before_run", cfg, abort_on_fail=True):
                log.error("[Retry] before_run hook failed. Aborting retry.")
                return False

        if run_agent(task, cfg, attempt=attempt):
            return True

        if attempt < max_attempts:
            log.warning(f"[Retry] Attempt {attempt} failed. Scheduling retry...")

    log.error(f"[Retry] All {max_attempts} attempts exhausted.")
    return False


# ═══════════════════════════════════════════════════════════════════
# Handoff
# ═══════════════════════════════════════════════════════════════════

def handle_handoff(branch_name: str) -> None:
    """Commits changes to the isolated branch, ready for push and PR."""
    log.info("[Handoff] Checking for changes...")
    status = subprocess.run(["git", "status", "--porcelain"],
                            capture_output=True, text=True)
    if not status.stdout.strip():
        print("[Symphony] No changes detected in the repository.")
        return

    subprocess.run(["git", "add", "."], check=True)
    subprocess.run(["git", "commit", "-m",
                    f"ai: autonomous changes via Symphony-Lite [{branch_name}]"],
                   check=True)
    print(f"\n[DONE] Task complete! Branch: '{branch_name}'")
    print(f"       Run: git push origin {branch_name}  (then open a PR)")
    # Uncomment after configuring SSH keys or Git tokens:
    # subprocess.run(["git", "push", "origin", branch_name], check=True)


# ═══════════════════════════════════════════════════════════════════
# Logging Setup (SPEC §3.1 — Observability)
# ═══════════════════════════════════════════════════════════════════

def setup_logging(verbose: bool = False) -> logging.Logger:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)-8s] %(message)s",
        datefmt="%H:%M:%S",
    )
    return logging.getLogger("symphony")


# ═══════════════════════════════════════════════════════════════════
# CLI Entry Point
# ═══════════════════════════════════════════════════════════════════

def main():
    global log
    log = setup_logging()

    # SPEC §7.2: Ensure we are in our own process group to manage children
    try:
        os.setpgrp()
    except Exception:
        pass

    def stop_all(exit_code: int = 0):
        """Aggressively terminates all processes in the group and exits."""
        # Ignore TERM in the orchestrator itself to avoid recursive signals
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        try:
            # Send SIGTERM to the entire process group (0 means current group)
            os.killpg(0, signal.SIGTERM)
        except Exception:
            pass
        sys.exit(exit_code)

    def signal_handler(sig, frame):
        print("\n[Orchestrator] Stop signal received. Stopping all...")
        stop_all(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    parser = argparse.ArgumentParser(
        description=(
            "Symphony-Lite: minimal orchestrator for autonomous coding agents.\n"
            "~70%% compliance with Symphony SPEC v1\n"
            "https://github.com/openai/symphony/blob/main/SPEC.md"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-u", "--url",  required=True,
                        help="Git repository URL to clone")
    parser.add_argument("-t", "--task", required=True,
                        help="Task description for the agent to solve")
    parser.add_argument("-i", "--id",   default="task-auto",
                        help="Unique task ID → branch name symphony/<id> (default: %(default)s)")
    parser.add_argument("--opencode",   action="store_true",
                        help="Use OpenCode instead of Gemini CLI")
    parser.add_argument("--no-retry",   action="store_true",
                        help="Disable automatic retry on failure")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable debug-level logging")
    args = parser.parse_args()

    log = setup_logging(verbose=args.verbose)

    branch_name  = f"symphony/{args.id}"
    original_dir = Path.cwd()

    log.info("=" * 60)
    log.info("  Symphony-Lite — Starting")
    log.info(f"  Repo  : {args.url}")
    log.info(f"  Task  : {args.task[:70]}{'...' if len(args.task) > 70 else ''}")
    log.info(f"  Branch: {branch_name}")
    log.info("=" * 60)

    # SPEC §6.3 — Preflight with default config (pre-workspace, early check)
    initial_cfg = ServiceConfig(use_opencode=args.opencode,
                                agent_command="opencode" if args.opencode else "gemini")
    if not preflight_validation(initial_cfg):
        log.error("Preflight validation failed. Aborting.")
        stop_all(1)

    success = False
    try:
        # SPEC §9 — Set up per-issue workspace with reuse
        workspace_path, created_now = setup_workspace(args.url, branch_name, initial_cfg)

        # SPEC §5 — Load WORKFLOW.md from the cloned workspace
        raw_config, prompt_template = load_workflow(workspace_path)
        cfg = resolve_config(raw_config, args)
        cfg.prompt_template = prompt_template

        # SPEC §6.3 — Preflight with real config (post-workflow load)
        if not preflight_validation(cfg):
            log.error("Preflight validation (post-workflow) failed. Aborting.")
            stop_all(1)

        # SPEC §5.3.4 — after_create hook (only when workspace is newly created)
        if created_now:
            if not run_hook(cfg.hook_after_create, "after_create", cfg, abort_on_fail=True):
                log.error("after_create hook failed. Aborting.")
                stop_all(1)

        # SPEC §5.3.4 — before_run hook
        if not run_hook(cfg.hook_before_run, "before_run", cfg, abort_on_fail=True):
            log.error("before_run hook failed. Aborting.")
            stop_all(1)

        # SPEC §8.4 — Run agent with optional retry
        success = run_agent(args.task, cfg) if args.no_retry else run_with_retry(args.task, cfg)

        # SPEC §5.3.4 — after_run hook (always, even on failure)
        run_hook(cfg.hook_after_run, "after_run", cfg, abort_on_fail=False)

        if success:
            handle_handoff(branch_name)
            log.info("[Orchestrator] Task complete. Stopping all and exiting.")
            stop_all(0)
        else:
            stop_all(1)

    except subprocess.CalledProcessError as e:
        log.error(f"Git/system command failed: {e}")
        stop_all(1)
    finally:
        # Always restore the original working directory
        os.chdir(original_dir)
        log.info(f"[Orchestrator] Final state: {'SUCCEEDED' if success else 'FAILED'}")
        log.info("=" * 60)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
