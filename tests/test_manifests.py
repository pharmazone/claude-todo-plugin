import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_plugin_manifest_identifies_the_plugin():
    manifest = load(".claude-plugin/plugin.json")
    assert manifest["name"] == "claude-todo"
    assert manifest["license"] == "MIT"
    assert manifest["repository"].endswith("pharmazone/claude-todo-plugin")


def test_plugin_manifest_declares_both_user_options():
    options = load(".claude-plugin/plugin.json")["userConfig"]
    assert set(options) == {"todo_file", "todo_editor"}
    for option in options.values():
        assert option["type"] == "string"
        assert option["title"]
        assert option["description"]


def test_todo_file_option_defaults_to_the_documented_path():
    options = load(".claude-plugin/plugin.json")["userConfig"]
    assert options["todo_file"]["default"] == ".claude/TODO.md"


def test_marketplace_lists_this_plugin_at_the_repo_root():
    marketplace = load(".claude-plugin/marketplace.json")
    assert marketplace["name"] == "claude-todo-plugin"
    entry, = marketplace["plugins"]
    assert entry["name"] == "claude-todo"
    assert entry["source"] == "./"


def test_marketplace_version_matches_the_plugin():
    assert (
        load(".claude-plugin/marketplace.json")["plugins"][0]["version"]
        == load(".claude-plugin/plugin.json")["version"]
    )


def test_hooks_register_the_capture_hook():
    hooks = load("hooks/hooks.json")["hooks"]["UserPromptExpansion"]
    entry, = hooks
    assert entry["matcher"] == "todo"
    command = entry["hooks"][0]["command"]
    assert "${CLAUDE_PLUGIN_ROOT}" in command
    assert command.endswith("add --from-hook")


def test_component_directories_are_at_the_plugin_root():
    """Claude Code ignores components nested inside .claude-plugin/."""
    for directory in ("commands", "skills", "hooks", "scripts"):
        assert (ROOT / directory).is_dir()
        assert not (ROOT / ".claude-plugin" / directory).exists()
