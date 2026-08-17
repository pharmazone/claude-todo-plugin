import json

import pytest

import todo


def env(tmp_path, **extra):
    base = {"CLAUDE_PROJECT_DIR": str(tmp_path), "CLAUDE_TODO_FILE": "TODO.md"}
    base.update(extra)
    return base


def run(monkeypatch, tmp_path, *argv, **extra):
    for key, value in env(tmp_path, **extra).items():
        monkeypatch.setenv(key, value)
    return todo.main(list(argv))


def test_strip_command_handles_the_bare_form():
    assert todo.strip_command("/todo create agents") == "create agents"


def test_strip_command_handles_the_namespaced_form():
    assert todo.strip_command("/claude-todo:todo create agents") == "create agents"


def test_strip_command_handles_no_leading_slash():
    assert todo.strip_command("todo create agents") == "create agents"


def test_strip_command_returns_empty_for_a_bare_invocation():
    assert todo.strip_command("/todo") == ""
    assert todo.strip_command("  /todo   ") == ""


def test_strip_command_keeps_text_that_is_not_a_command():
    assert todo.strip_command("just some text") == "just some text"


def test_add_writes_the_item(monkeypatch, tmp_path, capsys):
    assert run(monkeypatch, tmp_path, "add", "create", "agents") == 0
    assert "- [ ] create agents" in (tmp_path / "TODO.md").read_text()
    assert "create agents" in capsys.readouterr().out


def test_add_rejects_empty_text(monkeypatch, tmp_path):
    assert run(monkeypatch, tmp_path, "add", "  ") == 1


def test_list_json_reports_open_items(monkeypatch, tmp_path, capsys):
    run(monkeypatch, tmp_path, "add", "one")
    run(monkeypatch, tmp_path, "add", "two")
    run(monkeypatch, tmp_path, "done", "1")
    capsys.readouterr()

    assert run(monkeypatch, tmp_path, "list", "--json") == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["open"] == 1
    assert payload["total"] == 2
    assert payload["items"] == [{"n": 1, "text": "two", "body": [], "done": False}]
    assert payload["path"].endswith("TODO.md")


def test_list_all_includes_done(monkeypatch, tmp_path, capsys):
    run(monkeypatch, tmp_path, "add", "one")
    run(monkeypatch, tmp_path, "done", "1")
    capsys.readouterr()

    run(monkeypatch, tmp_path, "list", "--all", "--json")
    assert len(json.loads(capsys.readouterr().out)["items"]) == 1


def test_list_plain_output_is_numbered(monkeypatch, tmp_path, capsys):
    run(monkeypatch, tmp_path, "add", "one")
    capsys.readouterr()
    run(monkeypatch, tmp_path, "list")
    assert "1. one" in capsys.readouterr().out


def test_list_on_an_empty_file_says_so(monkeypatch, tmp_path, capsys):
    assert run(monkeypatch, tmp_path, "list") == 0
    assert "no open todos" in capsys.readouterr().out.lower()


def test_done_by_substring(monkeypatch, tmp_path):
    run(monkeypatch, tmp_path, "add", "fix the login redirect")
    assert run(monkeypatch, tmp_path, "done", "login") == 0
    assert "- [x] fix the login redirect" in (tmp_path / "TODO.md").read_text()


def test_done_with_an_unknown_selector_exits_one(monkeypatch, tmp_path):
    run(monkeypatch, tmp_path, "add", "one")
    assert run(monkeypatch, tmp_path, "done", "zzz") == 1


def test_path_prints_the_resolved_file(monkeypatch, tmp_path, capsys):
    assert run(monkeypatch, tmp_path, "path") == 0
    assert capsys.readouterr().out.strip() == str(tmp_path / "TODO.md")


def test_edit_splices_the_edited_text_back(monkeypatch, tmp_path):
    run(monkeypatch, tmp_path, "add", "original")

    def fake_edit(target, **kwargs):
        target.write_text("renamed\nwith a note\n", encoding="utf-8")
        return 0

    monkeypatch.setattr(todo.editor, "edit_file", fake_edit)
    assert run(monkeypatch, tmp_path, "edit", "1") == 0
    assert "- [ ] renamed\n  with a note\n" in (tmp_path / "TODO.md").read_text()


def test_edit_leaves_the_item_alone_when_the_editor_fails(monkeypatch, tmp_path):
    run(monkeypatch, tmp_path, "add", "original")

    def fake_edit(target, **kwargs):
        target.write_text("scribble\n", encoding="utf-8")
        return 1

    monkeypatch.setattr(todo.editor, "edit_file", fake_edit)
    assert run(monkeypatch, tmp_path, "edit", "1") == 1
    assert "- [ ] original" in (tmp_path / "TODO.md").read_text()


def test_edit_exits_three_when_no_editor_is_available(monkeypatch, tmp_path):
    run(monkeypatch, tmp_path, "add", "original")

    def fake_edit(target, **kwargs):
        raise todo.editor.EditorUnavailable("nothing here")

    monkeypatch.setattr(todo.editor, "edit_file", fake_edit)
    assert run(monkeypatch, tmp_path, "edit", "1") == 3


def test_edit_exits_four_on_timeout(monkeypatch, tmp_path):
    run(monkeypatch, tmp_path, "add", "original")

    def fake_edit(target, **kwargs):
        raise TimeoutError("too slow")

    monkeypatch.setattr(todo.editor, "edit_file", fake_edit)
    assert run(monkeypatch, tmp_path, "edit", "1") == 4
