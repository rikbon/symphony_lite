import pytest
from pathlib import Path
from symphony_lite import resolve_config, run_hook, build_prompt, ServiceConfig

class MockArgs:
    def __init__(self, opencode=False):
        self.opencode = opencode

def test_resolve_config_aliases():
    raw = {
        "hooks": {
            "before_turn": "echo before",
            "after_turn": "echo after"
        }
    }
    args = MockArgs()
    cfg = resolve_config(raw, args)
    assert cfg.hook_before_run == "echo before"
    assert cfg.hook_after_run == "echo after"

def test_resolve_config_precedence():
    raw = {
        "hooks": {
            "before_run": "echo real_before",
            "before_turn": "echo alias_before"
        }
    }
    args = MockArgs()
    cfg = resolve_config(raw, args)
    assert cfg.hook_before_run == "echo real_before"

def test_run_hook_list(caplog):
    import logging
    caplog.set_level(logging.INFO)
    cfg = ServiceConfig(hook_timeout_ms=1000)
    scripts = ["echo command1", "echo command2"]
    assert run_hook(scripts, "test_hook", cfg) is True
    assert "Running 'test_hook' (2 commands)" in caplog.text
    assert "Command OK: echo command1..." in caplog.text
    assert "Command OK: echo command2..." in caplog.text

def test_run_hook_fail_abort():
    cfg = ServiceConfig(hook_timeout_ms=1000)
    scripts = ["exit 1", "echo should_not_run"]
    assert run_hook(scripts, "test_hook", cfg, abort_on_fail=True) is False

def test_run_hook_fail_no_abort():
    cfg = ServiceConfig(hook_timeout_ms=1000)
    scripts = ["exit 1", "echo should_run"]
    # Currently run_hook returns False if any command fails and abort_on_fail is True.
    # If abort_on_fail is False, it should continue and return True? 
    # Let's check the implementation.
    # for cmd in commands:
    #     ...
    #     if result.returncode != 0:
    #         if abort_on_fail: return False
    # ...
    # return True
    assert run_hook(scripts, "test_hook", cfg, abort_on_fail=False) is True

def test_build_prompt_substitution():
    cfg = ServiceConfig(prompt_template="Task: {{ task }}, Attempt: {{ attempt }}, Issue: {{ issue.identifier }}")
    context = {"issue": {"identifier": "ID-123"}}
    prompt = build_prompt("My Task", cfg, 1, context=context)
    assert "Task: My Task" in prompt
    assert "Attempt: 1" in prompt
    assert "Issue: ID-123" in prompt

def test_build_prompt_default():
    cfg = ServiceConfig(prompt_template=None)
    prompt = build_prompt("My Task", cfg, 1)
    assert "TASK: My Task" in prompt
    assert "WORKFLOW.md" in prompt
