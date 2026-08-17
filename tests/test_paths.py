from pathlib import Path

import todo_store


def test_default_path_is_under_project_dir(tmp_path):
    env = {"CLAUDE_PROJECT_DIR": str(tmp_path)}
    assert todo_store.resolve_path(env) == tmp_path / ".claude/TODO.md"


def test_claude_todo_file_wins_over_plugin_option(tmp_path):
    env = {
        "CLAUDE_PROJECT_DIR": str(tmp_path),
        "CLAUDE_TODO_FILE": "a.md",
        "CLAUDE_PLUGIN_OPTION_TODO_FILE": "b.md",
    }
    assert todo_store.resolve_path(env) == tmp_path / "a.md"


def test_plugin_option_used_when_no_explicit_override(tmp_path):
    env = {
        "CLAUDE_PROJECT_DIR": str(tmp_path),
        "CLAUDE_PLUGIN_OPTION_TODO_FILE": "notes/b.md",
    }
    assert todo_store.resolve_path(env) == tmp_path / "notes/b.md"


def test_empty_env_var_falls_through_to_default(tmp_path):
    env = {"CLAUDE_PROJECT_DIR": str(tmp_path), "CLAUDE_TODO_FILE": ""}
    assert todo_store.resolve_path(env) == tmp_path / ".claude/TODO.md"


def test_absolute_path_is_passed_through(tmp_path):
    target = tmp_path / "elsewhere/T.md"
    env = {"CLAUDE_PROJECT_DIR": "/somewhere/else", "CLAUDE_TODO_FILE": str(target)}
    assert todo_store.resolve_path(env) == target


def test_falls_back_to_cwd_without_project_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert todo_store.resolve_path({}) == tmp_path / ".claude/TODO.md"


def test_user_home_is_expanded():
    env = {"CLAUDE_TODO_FILE": "~/T.md"}
    assert todo_store.resolve_path(env) == Path.home() / "T.md"
