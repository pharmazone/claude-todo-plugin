# claude-todo-plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Claude Code plugin whose `/todo` command captures an idea mid-run without costing a turn, lists open items in a picker, hands one to Claude, opens one in a real editor, and marks it done.

**Architecture:** Three focused Python modules under `scripts/` — `todo_store.py` (line-level markdown mutations), `editor.py` (editor resolution + terminal-overlay launch), `todo.py` (CLI + hook adapter). A `UserPromptExpansion` hook calls `todo.py add --from-hook` and blocks expansion so capture never becomes an LLM turn. A command and a skill carry the Claude-facing flows.

**Tech Stack:** Python 3.9+, standard library only at runtime. `uv` + `pytest` for development. GitHub Actions for CI.

**Spec:** `docs/superpowers/specs/2026-08-17-todo-plugin-design.md`

## Global Constraints

- Repo root: `~/project/claude-todo-plugin`. All paths below are relative to it.
- Runtime code imports **standard library only**. The hook runs bare `python3`; it must never need `uv`, a virtualenv, or a third-party package.
- `requires-python = ">=3.9"`. Every module starts with `from __future__ import annotations` so `list[str]` annotations work on 3.9.
- **The todo file is human-owned.** Every mutation is a line-level edit. Never parse the file into a model and re-serialize it. Headings, prose, and blank lines around the list survive untouched. This is the single most important invariant in the codebase and every mutation test asserts it.
- Plugin name: `claude-todo`. Marketplace name: `claude-todo-plugin`. Repo: `pharmazone/claude-todo-plugin`.
- License: MIT. Author: `pharmazone`.
- Default todo file: `.claude/TODO.md`.
- Editor auto-detection order: `nvim --clean`, `vim -u NONE -N`, `nano`. The plugin-free flags apply **only** to auto-detection; an editor the user set in `$VISUAL`, `$EDITOR`, or `todo_editor` is honored verbatim.
- The hook must **never** exit with code 2 — that blocks the expansion. Blocking is expressed only via `hookSpecificOutput.block`.
- Tests are functional pytest: plain `test_*` functions, `tmp_path`, no classes.
- Commit messages: conventional commits, no emojis, no `Co-Authored-By`.

---

## File Structure

| File | Responsibility |
|---|---|
| `scripts/todo_store.py` | Path resolution, parsing, and line-level mutation of the markdown file. No I/O beyond the todo file. No subprocess. |
| `scripts/editor.py` | Resolve which editor to run and which terminal overlay to run it in. One subprocess call. Knows nothing about todos. |
| `scripts/todo.py` | CLI entry point and `UserPromptExpansion` hook adapter. Wires the other two together. |
| `tests/test_store.py` | Parsing and mutation behaviour, including the human-owned-file invariant. |
| `tests/test_paths.py` | Path resolution precedence. |
| `tests/test_editor.py` | Editor resolution, launcher selection, wrapper rendering, `edit_file` orchestration — all with a faked environment and a captured runner. |
| `tests/test_cli.py` | CLI surface: exit codes, JSON output, hook payload handling. |
| `tests/test_manifests.py` | `plugin.json` / `marketplace.json` / `hooks.json` parse and agree with each other. |
| `.claude-plugin/plugin.json` | Manifest, `userConfig`. |
| `.claude-plugin/marketplace.json` | Makes the repo its own marketplace. |
| `commands/todo.md` | The `/todo` command. |
| `skills/todo-workflow/SKILL.md` | Standing guidance: next-step picker, done-marking. |
| `hooks/hooks.json` | `UserPromptExpansion` registration. |

---

### Task 1: Repo scaffold

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `LICENSE`, `CHANGELOG.md`, `.github/workflows/ci.yml`, `tests/__init__.py`

**Interfaces:**
- Consumes: nothing.
- Produces: a working `uv run pytest` invocation with `scripts/` on the import path, so every later task can `import todo_store` / `import editor` / `import todo`.

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "claude-todo-plugin"
version = "0.1.0"
description = "Capture ideas while Claude Code works, then pick them back up"
readme = "README.md"
requires-python = ">=3.9"
license = { text = "MIT" }
dependencies = []

[dependency-groups]
dev = ["pytest>=8.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["scripts"]
addopts = "-q"
```

`pythonpath = ["scripts"]` is what lets tests import the runtime modules without packaging them. The runtime itself never relies on it: `python3 scripts/todo.py` puts `scripts/` on `sys.path` automatically.

- [ ] **Step 2: Create `.gitignore`**

```gitignore
__pycache__/
*.py[cod]
.venv/
.pytest_cache/
.DS_Store
```

- [ ] **Step 3: Create `LICENSE`**

MIT license text, copyright line: `Copyright (c) 2026 pharmazone`.

- [ ] **Step 4: Create `CHANGELOG.md`**

```markdown
# Changelog

## [Unreleased]

### Added
- `/todo <text>` captures an idea without costing a Claude turn.
- `/todo` opens a picker over open items.
- Edit action opens the item in a real editor inside a terminal overlay.
- Items are marked done automatically once Claude finishes them.
```

- [ ] **Step 5: Create `tests/__init__.py`**

Empty file.

- [ ] **Step 6: Create `.github/workflows/ci.yml`**

```yaml
name: ci

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true
      - run: uv run pytest
```

Manifest validation is a pytest test (Task 10), not a separate CI step, so CI stays a single command.

- [ ] **Step 7: Verify the harness runs**

Run: `cd ~/project/claude-todo-plugin && uv run pytest --collect-only`
Expected: exits 0, collects 0 items, no import errors.

- [ ] **Step 8: Commit**

```bash
cd ~/project/claude-todo-plugin
git add pyproject.toml .gitignore LICENSE CHANGELOG.md .github tests
git commit -m "chore: scaffold plugin repo with uv and pytest"
```

---

### Task 2: Path resolution and parsing

**Files:**
- Create: `scripts/todo_store.py`
- Test: `tests/test_paths.py`, `tests/test_store.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `DEFAULT_TODO_FILE: str = ".claude/TODO.md"`
  - `Item` dataclass with fields `n: int`, `line: int`, `text: str`, `done: bool`, `body: list[str]`
  - `resolve_path(env: Mapping | None = None) -> Path`
  - `read_lines(path: Path) -> list[str]` (returns `[]` for a missing file; lines keep their `\n`)
  - `write_lines(path: Path, lines: list[str]) -> None`
  - `parse(lines: list[str]) -> list[Item]` (`n` numbers all items from 1)
  - `select(path: Path, only_open: bool = True) -> list[Item]` (filters, then renumbers `n` from 1 over the returned list)
  - `find(items: list[Item], selector: str) -> Item`

- [ ] **Step 1: Write the failing tests**

`tests/test_paths.py`:

```python
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
```

`tests/test_store.py`:

```python
import todo_store

SAMPLE = """# TODO

Some prose a human wrote.

- [ ] create tik-tak-toe agents
  Use the agent scaffold in src/agents/.
  Two players, minimax.
- [x] add dark mode
- [ ] fix the login redirect

## Notes

Trailing prose.
"""


def write(tmp_path, text):
    p = tmp_path / "TODO.md"
    p.write_text(text, encoding="utf-8")
    return p


def test_parse_finds_every_item(tmp_path):
    items = todo_store.parse(SAMPLE.splitlines(keepends=True))
    assert [i.text for i in items] == [
        "create tik-tak-toe agents",
        "add dark mode",
        "fix the login redirect",
    ]
    assert [i.n for i in items] == [1, 2, 3]
    assert [i.done for i in items] == [False, True, False]


def test_parse_collects_indented_body(tmp_path):
    items = todo_store.parse(SAMPLE.splitlines(keepends=True))
    assert items[0].body == [
        "Use the agent scaffold in src/agents/.",
        "Two players, minimax.",
    ]
    assert items[1].body == []


def test_parse_records_line_numbers(tmp_path):
    lines = SAMPLE.splitlines(keepends=True)
    items = todo_store.parse(lines)
    for item in items:
        assert lines[item.line].startswith("- [")


def test_parse_ignores_a_checkbox_that_is_not_top_level():
    lines = "- [ ] real\n  - [ ] nested\n".splitlines(keepends=True)
    items = todo_store.parse(lines)
    assert [i.text for i in items] == ["real"]
    assert items[0].body == ["- [ ] nested"]


def test_parse_on_empty_file():
    assert todo_store.parse([]) == []


def test_read_lines_on_missing_file(tmp_path):
    assert todo_store.read_lines(tmp_path / "nope.md") == []


def test_select_open_renumbers_from_one(tmp_path):
    p = write(tmp_path, SAMPLE)
    items = todo_store.select(p, only_open=True)
    assert [(i.n, i.text) for i in items] == [
        (1, "create tik-tak-toe agents"),
        (2, "fix the login redirect"),
    ]


def test_select_all_includes_done(tmp_path):
    p = write(tmp_path, SAMPLE)
    assert len(todo_store.select(p, only_open=False)) == 3


def test_find_by_index(tmp_path):
    p = write(tmp_path, SAMPLE)
    items = todo_store.select(p)
    assert todo_store.find(items, "2").text == "fix the login redirect"


def test_find_by_substring_is_case_insensitive(tmp_path):
    p = write(tmp_path, SAMPLE)
    items = todo_store.select(p)
    assert todo_store.find(items, "TIK-TAK").text == "create tik-tak-toe agents"


def test_find_rejects_out_of_range_index(tmp_path):
    p = write(tmp_path, SAMPLE)
    items = todo_store.select(p)
    with pytest.raises(LookupError, match="no item numbered 9"):
        todo_store.find(items, "9")


def test_find_rejects_ambiguous_substring(tmp_path):
    items = todo_store.parse("- [ ] alpha one\n- [ ] alpha two\n".splitlines(keepends=True))
    with pytest.raises(LookupError, match="ambiguous"):
        todo_store.find(items, "alpha")


def test_find_rejects_no_match(tmp_path):
    p = write(tmp_path, SAMPLE)
    items = todo_store.select(p)
    with pytest.raises(LookupError, match="no open item"):
        todo_store.find(items, "zzz")


def test_unicode_survives_a_round_trip(tmp_path):
    p = write(tmp_path, "- [ ] café ☕ — naïve\n")
    assert todo_store.select(p)[0].text == "café ☕ — naïve"
```

Add `import pytest` at the top of `tests/test_store.py`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_paths.py tests/test_store.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'todo_store'`

- [ ] **Step 3: Write `scripts/todo_store.py`**

```python
"""Reading and writing the project TODO markdown file.

The file belongs to the human, not to this script. Every mutation is a
line-level edit, so headings, prose and blank lines around the list survive
untouched. Nothing here ever reconstructs the file from a parsed model.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Optional

DEFAULT_TODO_FILE = ".claude/TODO.md"

NEW_FILE_HEADER = ["# TODO\n", "\n"]

ITEM_RE = re.compile(r"^(?P<indent>[ \t]*)- \[(?P<mark>[ xX])\] (?P<text>.*)$")


@dataclass
class Item:
    n: int
    line: int
    text: str
    done: bool
    body: list[str] = field(default_factory=list)

    @property
    def open(self) -> bool:
        return not self.done


def resolve_path(env: Optional[Mapping[str, str]] = None) -> Path:
    env = os.environ if env is None else env
    raw = (
        env.get("CLAUDE_TODO_FILE")
        or env.get("CLAUDE_PLUGIN_OPTION_TODO_FILE")
        or DEFAULT_TODO_FILE
    )
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    root = env.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return Path(root).expanduser() / path


def read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines(keepends=True)
    except FileNotFoundError:
        return []


def write_lines(path: Path, lines: Iterable[str]) -> None:
    text = "".join(lines)
    if text and not text.endswith("\n"):
        text += "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _top_level(raw: str):
    match = ITEM_RE.match(raw)
    return match if match and match.group("indent") == "" else None


def parse(lines: list[str]) -> list[Item]:
    items: list[Item] = []
    i = 0
    while i < len(lines):
        match = _top_level(lines[i].rstrip("\n"))
        if match is None:
            i += 1
            continue
        body: list[str] = []
        j = i + 1
        while j < len(lines):
            nxt = lines[j].rstrip("\n")
            if not nxt.strip() or not nxt[:1].isspace():
                break
            body.append(nxt.strip())
            j += 1
        items.append(
            Item(
                n=len(items) + 1,
                line=i,
                text=match.group("text").strip(),
                done=match.group("mark").lower() == "x",
                body=body,
            )
        )
        i = j
    return items


def select(path: Path, only_open: bool = True) -> list[Item]:
    items = parse(read_lines(path))
    if only_open:
        items = [item for item in items if item.open]
    for n, item in enumerate(items, start=1):
        item.n = n
    return items


def find(items: list[Item], selector: str) -> Item:
    needle = selector.strip()
    if not needle:
        raise LookupError("no selector given")
    if needle.isdigit():
        n = int(needle)
        if 1 <= n <= len(items):
            return items[n - 1]
        raise LookupError(f"no item numbered {n} (there are {len(items)})")
    matches = [item for item in items if needle.lower() in item.text.lower()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise LookupError(f"no open item matching {needle!r}")
    raise LookupError("ambiguous selector, matches: " + "; ".join(m.text for m in matches))
```

A nested `- [ ]` is deliberately body text, not an item: sub-tasks are out of scope, and treating an indented checkbox as a real item would make `n` disagree with what the user was shown.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_paths.py tests/test_store.py`
Expected: PASS, 20 tests.

- [ ] **Step 5: Commit**

```bash
git add scripts/todo_store.py tests/test_paths.py tests/test_store.py
git commit -m "feat: parse the todo file and resolve its path"
```

---

### Task 3: Adding an item

**Files:**
- Modify: `scripts/todo_store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `parse`, `read_lines`, `write_lines`, `Item` from Task 2.
- Produces: `add(path: Path, text: str) -> Item` — appends `- [ ] <text>` after the last existing item (or at end of file when there are none), creating the file with `# TODO` when missing. Collapses whitespace in `text`. Raises `ValueError` on empty text.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_store.py`:

```python
def test_add_creates_the_file_with_a_heading(tmp_path):
    p = tmp_path / "nested" / "TODO.md"
    todo_store.add(p, "first idea")
    assert p.read_text(encoding="utf-8") == "# TODO\n\n- [ ] first idea\n"


def test_add_appends_after_the_last_item(tmp_path):
    p = write(tmp_path, SAMPLE)
    todo_store.add(p, "new idea")
    lines = p.read_text(encoding="utf-8").splitlines()
    assert lines[lines.index("- [ ] fix the login redirect") + 1] == "- [ ] new idea"


def test_add_preserves_surrounding_prose(tmp_path):
    p = write(tmp_path, SAMPLE)
    todo_store.add(p, "new idea")
    text = p.read_text(encoding="utf-8")
    assert "Some prose a human wrote." in text
    assert "## Notes" in text
    assert "Trailing prose." in text
    assert "  Two players, minimax." in text


def test_add_to_a_file_with_prose_but_no_items(tmp_path):
    p = write(tmp_path, "# Notes\n\nJust prose.\n\n\n")
    todo_store.add(p, "first idea")
    assert p.read_text(encoding="utf-8") == "# Notes\n\nJust prose.\n\n- [ ] first idea\n"


def test_add_collapses_whitespace(tmp_path):
    p = tmp_path / "TODO.md"
    item = todo_store.add(p, "  spread   over\n  lines  ")
    assert item.text == "spread over lines"
    assert "- [ ] spread over lines\n" in p.read_text(encoding="utf-8")


def test_add_rejects_empty_text(tmp_path):
    with pytest.raises(ValueError):
        todo_store.add(tmp_path / "TODO.md", "   ")


def test_add_returns_the_new_item_numbered_over_open_items(tmp_path):
    p = write(tmp_path, SAMPLE)
    item = todo_store.add(p, "new idea")
    assert item.text == "new idea"
    assert item.n == 3
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_store.py -k add`
Expected: FAIL with `AttributeError: module 'todo_store' has no attribute 'add'`

- [ ] **Step 3: Implement `add`**

Append to `scripts/todo_store.py`:

```python
def add(path: Path, text: str) -> Item:
    collapsed = " ".join(text.split())
    if not collapsed:
        raise ValueError("todo text is empty")

    lines = read_lines(path)
    items = parse(lines)
    new_line = f"- [ ] {collapsed}\n"

    if not lines:
        lines = list(NEW_FILE_HEADER)
        lines.append(new_line)
    elif items:
        last = items[-1]
        lines.insert(last.line + 1 + len(last.body), new_line)
    else:
        end = len(lines)
        while end > 0 and not lines[end - 1].strip():
            end -= 1
        lines = lines[:end] + ["\n", new_line]

    write_lines(path, lines)
    return next(item for item in select(path) if item.text == collapsed)
```

The no-items branch trims trailing blank lines and re-adds exactly one, so repeated adds to a prose-only file do not accumulate whitespace.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_store.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/todo_store.py tests/test_store.py
git commit -m "feat: append a todo item without disturbing the rest of the file"
```

---

### Task 4: Marking an item done

**Files:**
- Modify: `scripts/todo_store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `select`, `find`, `read_lines`, `write_lines` from Task 2.
- Produces: `mark_done(path: Path, selector: str) -> tuple[Item, bool]` — returns the item and whether the file changed. An already-done item matched by substring is a no-op returning `(item, False)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_store.py`:

```python
def test_mark_done_by_index(tmp_path):
    p = write(tmp_path, SAMPLE)
    item, changed = todo_store.mark_done(p, "2")
    assert (item.text, changed) == ("fix the login redirect", True)
    assert "- [x] fix the login redirect" in p.read_text(encoding="utf-8")


def test_mark_done_by_substring(tmp_path):
    p = write(tmp_path, SAMPLE)
    item, changed = todo_store.mark_done(p, "tik-tak")
    assert changed is True
    assert "- [x] create tik-tak-toe agents" in p.read_text(encoding="utf-8")


def test_mark_done_keeps_the_body(tmp_path):
    p = write(tmp_path, SAMPLE)
    todo_store.mark_done(p, "tik-tak")
    assert "  Two players, minimax." in p.read_text(encoding="utf-8")


def test_mark_done_on_an_already_done_item_is_a_noop(tmp_path):
    p = write(tmp_path, SAMPLE)
    before = p.read_text(encoding="utf-8")
    item, changed = todo_store.mark_done(p, "dark mode")
    assert (item.text, changed) == ("add dark mode", False)
    assert p.read_text(encoding="utf-8") == before


def test_mark_done_preserves_surrounding_prose(tmp_path):
    p = write(tmp_path, SAMPLE)
    todo_store.mark_done(p, "1")
    text = p.read_text(encoding="utf-8")
    assert "Some prose a human wrote." in text
    assert "## Notes" in text


def test_mark_done_rejects_an_unknown_selector(tmp_path):
    p = write(tmp_path, SAMPLE)
    with pytest.raises(LookupError):
        todo_store.mark_done(p, "nothing like this")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_store.py -k mark_done`
Expected: FAIL with `AttributeError: module 'todo_store' has no attribute 'mark_done'`

- [ ] **Step 3: Implement `mark_done`**

Append to `scripts/todo_store.py`:

```python
def mark_done(path: Path, selector: str) -> tuple[Item, bool]:
    open_items = select(path, only_open=True)
    try:
        item = find(open_items, selector)
    except LookupError:
        # Already-done items are not in the open list. Matching one is a no-op
        # rather than an error: Claude may finish an item twice in a session.
        if selector.strip().isdigit():
            raise
        done_items = [i for i in select(path, only_open=False) if i.done]
        item = find(done_items, selector)
        return item, False

    lines = read_lines(path)
    lines[item.line] = lines[item.line].replace("- [ ]", "- [x]", 1)
    write_lines(path, lines)
    return item, True
```

`item.line` is a file-wide line number even when `select` renumbered `n`, so the edit lands on the right line regardless of filtering.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_store.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/todo_store.py tests/test_store.py
git commit -m "feat: mark an item done by index or substring"
```

---

### Task 5: Replacing an item's text and body

**Files:**
- Modify: `scripts/todo_store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `select`, `find`, `read_lines`, `write_lines` from Task 2.
- Produces:
  - `render_item(item: Item) -> str` — the item as editable text: first line is the text, remaining lines are the body.
  - `replace(path: Path, selector: str, blob: str) -> Item` — splice edited text back. First non-empty line becomes the text; the rest become the body, indented two spaces. A blob with no non-empty line raises `ValueError` (an emptied file means "no change", never a deletion).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_store.py`:

```python
def test_render_item_puts_text_first_then_body(tmp_path):
    p = write(tmp_path, SAMPLE)
    item = todo_store.select(p)[0]
    assert todo_store.render_item(item) == (
        "create tik-tak-toe agents\n"
        "Use the agent scaffold in src/agents/.\n"
        "Two players, minimax.\n"
    )


def test_replace_updates_text_and_body(tmp_path):
    p = write(tmp_path, SAMPLE)
    todo_store.replace(p, "1", "renamed task\nfirst note\nsecond note\n")
    text = p.read_text(encoding="utf-8")
    assert "- [ ] renamed task\n  first note\n  second note\n" in text
    assert "create tik-tak-toe agents" not in text


def test_replace_can_drop_the_body(tmp_path):
    p = write(tmp_path, SAMPLE)
    todo_store.replace(p, "1", "just the title\n")
    text = p.read_text(encoding="utf-8")
    assert "- [ ] just the title\n- [x] add dark mode\n" in text


def test_replace_can_add_a_body_to_a_bare_item(tmp_path):
    p = write(tmp_path, SAMPLE)
    todo_store.replace(p, "2", "fix the login redirect\nit 302s to /\n")
    assert "- [ ] fix the login redirect\n  it 302s to /\n" in p.read_text(encoding="utf-8")


def test_replace_preserves_surrounding_prose(tmp_path):
    p = write(tmp_path, SAMPLE)
    todo_store.replace(p, "1", "renamed\n")
    text = p.read_text(encoding="utf-8")
    assert "Some prose a human wrote." in text
    assert "## Notes" in text
    assert "- [x] add dark mode" in text


def test_replace_rejects_an_empty_blob(tmp_path):
    p = write(tmp_path, SAMPLE)
    with pytest.raises(ValueError):
        todo_store.replace(p, "1", "\n  \n")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_store.py -k "render_item or replace"`
Expected: FAIL with `AttributeError: module 'todo_store' has no attribute 'render_item'`

- [ ] **Step 3: Implement `render_item` and `replace`**

Append to `scripts/todo_store.py`:

```python
def render_item(item: Item) -> str:
    return "".join(line + "\n" for line in [item.text, *item.body])


def replace(path: Path, selector: str, blob: str) -> Item:
    stripped = [line.strip() for line in blob.splitlines()]
    kept = [line for line in stripped if line]
    if not kept:
        raise ValueError("edited text is empty; nothing was changed")

    items = select(path, only_open=False)
    for n, item in enumerate([i for i in items if i.open], start=1):
        item.n = n
    target = find([i for i in items if i.open], selector)

    mark = "x" if target.done else " "
    replacement = [f"- [{mark}] {kept[0]}\n"] + [f"  {line}\n" for line in kept[1:]]

    lines = read_lines(path)
    lines[target.line : target.line + 1 + len(target.body)] = replacement
    write_lines(path, lines)
    return Item(n=target.n, line=target.line, text=kept[0], done=target.done, body=kept[1:])
```

Blank lines inside the edited blob are dropped rather than kept, because `parse` ends a body at the first blank line — keeping them would silently truncate the body on the next read.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_store.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/todo_store.py tests/test_store.py
git commit -m "feat: splice an edited item back into the file"
```

---

### Task 6: Editor resolution and launcher selection

**Files:**
- Create: `scripts/editor.py`
- Test: `tests/test_editor.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `class EditorUnavailable(RuntimeError)`
  - `DEFAULT_EDITORS: tuple[tuple[str, list[str]], ...]`
  - `resolve_editor(env=None, which=shutil.which) -> list[str]`
  - `pick_launcher(env=None, which=shutil.which, platform=sys.platform) -> str | None` returning one of `"agterm" | "kitty" | "tmux" | "wezterm" | "macos" | None`
  - `render_wrapper(editor_argv: list[str], target: Path, sentinel: Path, cwd: str) -> str`
  - `build_command(launcher: str, wrapper: Path, cwd: str) -> list[str]`

- [ ] **Step 1: Write the failing tests**

`tests/test_editor.py`:

```python
from pathlib import Path

import pytest

import editor


def none_installed(name):
    return None


def all_installed(name):
    return "/usr/bin/" + name


def test_plugin_option_beats_visual_and_editor():
    env = {
        "CLAUDE_PLUGIN_OPTION_TODO_EDITOR": "code --wait",
        "VISUAL": "emacs",
        "EDITOR": "ed",
    }
    assert editor.resolve_editor(env, which=all_installed) == ["code", "--wait"]


def test_visual_beats_editor():
    env = {"VISUAL": "emacs", "EDITOR": "ed"}
    assert editor.resolve_editor(env, which=all_installed) == ["emacs"]


def test_empty_editor_var_falls_through():
    env = {"VISUAL": "  ", "EDITOR": "ed"}
    assert editor.resolve_editor(env, which=all_installed) == ["ed"]


def test_autodetect_prefers_plugin_free_nvim():
    assert editor.resolve_editor({}, which=all_installed) == ["nvim", "--clean"]


def test_autodetect_falls_back_to_vim_without_config():
    which = lambda name: "/usr/bin/vim" if name == "vim" else None
    assert editor.resolve_editor({}, which=which) == ["vim", "-u", "NONE", "-N"]


def test_autodetect_falls_back_to_nano():
    which = lambda name: "/usr/bin/nano" if name == "nano" else None
    assert editor.resolve_editor({}, which=which) == ["nano"]


def test_no_editor_at_all_raises():
    with pytest.raises(editor.EditorUnavailable, match="no editor"):
        editor.resolve_editor({}, which=none_installed)


def test_configured_editor_is_honoured_verbatim():
    """A user who sets $EDITOR gets their own config, plugins and all."""
    assert editor.resolve_editor({"EDITOR": "nvim"}, which=all_installed) == ["nvim"]


def test_agterm_wins_when_enabled():
    env = {"AGTERM_ENABLED": "1", "TMUX": "/tmp/x", "KITTY_LISTEN_ON": "unix:/x"}
    assert editor.pick_launcher(env, which=all_installed, platform="darwin") == "agterm"


def test_agterm_ignored_without_agtermctl():
    which = lambda name: None if name == "agtermctl" else "/usr/bin/" + name
    env = {"AGTERM_ENABLED": "1", "TERM": "xterm-kitty"}
    assert editor.pick_launcher(env, which=which, platform="darwin") == "kitty"


def test_kitty_detected_by_listen_socket():
    env = {"KITTY_LISTEN_ON": "unix:/tmp/k"}
    assert editor.pick_launcher(env, which=all_installed, platform="linux") == "kitty"


def test_kitty_detected_by_term():
    env = {"TERM": "xterm-kitty"}
    assert editor.pick_launcher(env, which=all_installed, platform="linux") == "kitty"


def test_tmux_detected():
    env = {"TMUX": "/tmp/tmux-501/default,1,0"}
    assert editor.pick_launcher(env, which=all_installed, platform="linux") == "tmux"


def test_wezterm_detected():
    env = {"WEZTERM_PANE": "3"}
    assert editor.pick_launcher(env, which=all_installed, platform="linux") == "wezterm"


def test_macos_is_the_floor_on_darwin():
    assert editor.pick_launcher({}, which=none_installed, platform="darwin") == "macos"


def test_nothing_available_on_bare_linux():
    assert editor.pick_launcher({}, which=none_installed, platform="linux") is None


def test_wrapper_runs_the_editor_then_writes_the_sentinel(tmp_path):
    script = editor.render_wrapper(
        ["nvim", "--clean"], tmp_path / "t.md", tmp_path / "t.done", str(tmp_path)
    )
    assert script.startswith("#!/bin/sh\n")
    assert f"cd '{tmp_path}'" in script
    assert f"nvim --clean '{tmp_path / 't.md'}'" in script
    assert f"echo $? > '{tmp_path / 't.done'}'" in script


def test_wrapper_quotes_awkward_paths(tmp_path):
    target = tmp_path / "it's here.md"
    script = editor.render_wrapper(["nano"], target, tmp_path / "s.done", str(tmp_path))
    # shlex.quote wraps the whole path, so the leading quote sits before the
    # directory, not before "it".
    assert "it'\"'\"'s here.md'" in script


def test_build_command_agterm(tmp_path):
    wrapper = tmp_path / "w.command"
    assert editor.build_command("agterm", wrapper, "/proj") == [
        "agtermctl", "session", "overlay", "open", f"sh {wrapper}",
        "--block", "--size-percent", "80",
    ]


def test_build_command_kitty(tmp_path):
    wrapper = tmp_path / "w.command"
    assert editor.build_command("kitty", wrapper, "/proj") == [
        "kitty", "@", "launch", "--type=overlay",
        "--wait-for-child-to-exit", "--cwd", "/proj", "sh", str(wrapper),
    ]


def test_build_command_tmux(tmp_path):
    wrapper = tmp_path / "w.command"
    assert editor.build_command("tmux", wrapper, "/proj") == [
        "tmux", "display-popup", "-E", "-w", "90%", "-h", "90%",
        "-d", "/proj", f"sh {wrapper}",
    ]


def test_build_command_wezterm(tmp_path):
    wrapper = tmp_path / "w.command"
    assert editor.build_command("wezterm", wrapper, "/proj") == [
        "wezterm", "cli", "spawn", "--new-window", "--cwd", "/proj",
        "--", "sh", str(wrapper),
    ]


def test_build_command_macos(tmp_path):
    wrapper = tmp_path / "w.command"
    assert editor.build_command("macos", wrapper, "/proj") == [
        "open", "-a", "Terminal", str(wrapper),
    ]


def test_build_command_rejects_an_unknown_launcher(tmp_path):
    with pytest.raises(editor.EditorUnavailable):
        editor.build_command("nope", tmp_path / "w.command", "/proj")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_editor.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'editor'`

- [ ] **Step 3: Write `scripts/editor.py`**

```python
"""Open a file in the user's editor, inside whatever overlay this terminal offers.

Knows nothing about todos. Given a path, it works out which editor to run and
which terminal can host it, then runs the editor there and reports its exit
status.

Every launcher runs the same generated wrapper script, which writes the
editor's exit code to a sentinel file when it finishes. Some launchers block
until the editor exits and some return immediately; polling for the sentinel
covers both without special-casing either.
"""

from __future__ import annotations

import shlex
import shutil
import sys
from pathlib import Path
from typing import Callable, Mapping, Optional

DEFAULT_EDITORS = (
    ("nvim", ["nvim", "--clean"]),
    ("vim", ["vim", "-u", "NONE", "-N"]),
    ("nano", ["nano"]),
)

OVERLAY_SIZE_PERCENT = "80"


class EditorUnavailable(RuntimeError):
    """No editor, or no terminal able to host one."""


def resolve_editor(
    env: Optional[Mapping[str, str]] = None,
    which: Callable[[str], Optional[str]] = shutil.which,
) -> list[str]:
    env = _env(env)
    for key in ("CLAUDE_PLUGIN_OPTION_TODO_EDITOR", "VISUAL", "EDITOR"):
        configured = (env.get(key) or "").strip()
        if configured:
            # Honoured verbatim: the user's own choice, their own config.
            return shlex.split(configured)
    for name, argv in DEFAULT_EDITORS:
        if which(name):
            # Auto-detected only, so start clean: no user config, no plugins.
            return list(argv)
    raise EditorUnavailable(
        "no editor found; set $EDITOR or the plugin's todo_editor option"
    )


def pick_launcher(
    env: Optional[Mapping[str, str]] = None,
    which: Callable[[str], Optional[str]] = shutil.which,
    platform: str = sys.platform,
) -> Optional[str]:
    env = _env(env)
    if env.get("AGTERM_ENABLED") == "1" and which("agtermctl"):
        return "agterm"
    if (env.get("KITTY_LISTEN_ON") or env.get("TERM") == "xterm-kitty") and which("kitty"):
        return "kitty"
    if env.get("TMUX") and which("tmux"):
        return "tmux"
    if env.get("WEZTERM_PANE") and which("wezterm"):
        return "wezterm"
    if platform == "darwin":
        return "macos"
    return None


def render_wrapper(
    editor_argv: list[str], target: Path, sentinel: Path, cwd: str
) -> str:
    command = shlex.join([*editor_argv, str(target)])
    return (
        "#!/bin/sh\n"
        f"cd {shlex.quote(cwd)}\n"
        f"{command}\n"
        f"echo $? > {shlex.quote(str(sentinel))}\n"
    )


def build_command(launcher: str, wrapper: Path, cwd: str) -> list[str]:
    run_wrapper = f"sh {wrapper}"
    if launcher == "agterm":
        return [
            "agtermctl", "session", "overlay", "open", run_wrapper,
            "--block", "--size-percent", OVERLAY_SIZE_PERCENT,
        ]
    if launcher == "kitty":
        return [
            "kitty", "@", "launch", "--type=overlay",
            "--wait-for-child-to-exit", "--cwd", cwd, "sh", str(wrapper),
        ]
    if launcher == "tmux":
        return [
            "tmux", "display-popup", "-E", "-w", "90%", "-h", "90%",
            "-d", cwd, run_wrapper,
        ]
    if launcher == "wezterm":
        return [
            "wezterm", "cli", "spawn", "--new-window", "--cwd", cwd,
            "--", "sh", str(wrapper),
        ]
    if launcher == "macos":
        return ["open", "-a", "Terminal", str(wrapper)]
    raise EditorUnavailable(f"unknown launcher {launcher!r}")


def _env(env: Optional[Mapping[str, str]]) -> Mapping[str, str]:
    import os

    return os.environ if env is None else env
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_editor.py`
Expected: PASS, 24 tests.

- [ ] **Step 5: Commit**

```bash
git add scripts/editor.py tests/test_editor.py
git commit -m "feat: resolve an editor and pick a terminal overlay to host it"
```

---

### Task 7: Running the editor and waiting for it

**Files:**
- Modify: `scripts/editor.py`
- Test: `tests/test_editor.py`

**Interfaces:**
- Consumes: everything from Task 6.
- Produces: `edit_file(target, env=None, timeout=570.0, poll=0.2, which=shutil.which, platform=sys.platform, runner=subprocess.run, sleep=time.sleep, clock=time.monotonic) -> int` — returns the editor's exit code. Raises `EditorUnavailable` when no launcher exists or the launcher itself fails, `TimeoutError` when the sentinel never appears.

`timeout` defaults to 570s because the Bash tool that invokes this dies at 600s; the script must give up first so it can report a useful message.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_editor.py`:

```python
class FakeRun:
    """Stands in for subprocess.run, optionally writing the sentinel."""

    def __init__(self, returncode=0, sentinel_code=None):
        self.returncode = returncode
        self.sentinel_code = sentinel_code
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        if self.sentinel_code is not None:
            # The wrapper is not always the last argument: the agterm command
            # ends with "--size-percent 80". Find it by suffix instead.
            wrapper = next(
                Path(part.replace("sh ", "")) for part in cmd if part.endswith(".command")
            )
            wrapper.with_suffix(".done").write_text(f"{self.sentinel_code}\n")
        return type("P", (), {"returncode": self.returncode, "stderr": "boom"})()


def agterm_env(tmp_path):
    return {"AGTERM_ENABLED": "1", "CLAUDE_PROJECT_DIR": str(tmp_path), "EDITOR": "nano"}


def test_edit_file_returns_the_editor_exit_code(tmp_path):
    target = tmp_path / "t.md"
    target.write_text("hello\n")
    run = FakeRun(sentinel_code=0)
    code = editor.edit_file(
        target, env=agterm_env(tmp_path), which=all_installed, runner=run
    )
    assert code == 0
    assert run.calls[0][0] == "agtermctl"


def test_edit_file_propagates_a_nonzero_editor_exit(tmp_path):
    target = tmp_path / "t.md"
    target.write_text("hello\n")
    run = FakeRun(sentinel_code=1)
    code = editor.edit_file(
        target, env=agterm_env(tmp_path), which=all_installed, runner=run
    )
    assert code == 1


def test_edit_file_cleans_up_wrapper_and_sentinel(tmp_path):
    target = tmp_path / "t.md"
    target.write_text("hello\n")
    editor.edit_file(
        target, env=agterm_env(tmp_path), which=all_installed,
        runner=FakeRun(sentinel_code=0),
    )
    assert list(tmp_path.glob("*.command")) == []
    assert list(tmp_path.glob("*.done")) == []


def test_edit_file_raises_when_no_launcher_exists(tmp_path):
    target = tmp_path / "t.md"
    target.write_text("hello\n")
    with pytest.raises(editor.EditorUnavailable, match="no terminal"):
        editor.edit_file(
            target,
            env={"EDITOR": "nano", "CLAUDE_PROJECT_DIR": str(tmp_path)},
            which=none_installed,
            platform="linux",
            runner=FakeRun(sentinel_code=0),
        )


def test_edit_file_raises_when_the_launcher_itself_fails(tmp_path):
    """kitty with remote control disabled looks exactly like this."""
    target = tmp_path / "t.md"
    target.write_text("hello\n")
    with pytest.raises(editor.EditorUnavailable, match="boom"):
        editor.edit_file(
            target, env=agterm_env(tmp_path), which=all_installed,
            runner=FakeRun(returncode=1),
        )


def test_edit_file_times_out_when_the_sentinel_never_appears(tmp_path):
    target = tmp_path / "t.md"
    target.write_text("hello\n")
    ticks = iter([0.0, 1.0, 2.0, 3.0, 999.0, 1000.0])
    with pytest.raises(TimeoutError):
        editor.edit_file(
            target, env=agterm_env(tmp_path), which=all_installed,
            runner=FakeRun(returncode=0), timeout=10.0,
            sleep=lambda _: None, clock=lambda: next(ticks),
        )


def test_edit_file_leaves_the_target_when_it_times_out(tmp_path):
    target = tmp_path / "t.md"
    target.write_text("hello\n")
    ticks = iter([0.0, 999.0, 1000.0])
    with pytest.raises(TimeoutError, match=str(target)):
        editor.edit_file(
            target, env=agterm_env(tmp_path), which=all_installed,
            runner=FakeRun(returncode=0), timeout=10.0,
            sleep=lambda _: None, clock=lambda: next(ticks),
        )
    assert target.read_text() == "hello\n"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_editor.py -k edit_file`
Expected: FAIL with `AttributeError: module 'editor' has no attribute 'edit_file'`

- [ ] **Step 3: Implement `edit_file`**

Add `import subprocess`, `import time`, and `import os` to the imports of `scripts/editor.py`, remove the local `import os` inside `_env`, then append:

```python
def edit_file(
    target: Path,
    env: Optional[Mapping[str, str]] = None,
    timeout: float = 570.0,
    poll: float = 0.2,
    which: Callable[[str], Optional[str]] = shutil.which,
    platform: str = sys.platform,
    runner: Callable[..., object] = subprocess.run,
    sleep: Callable[[float], object] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    env = _env(env)
    editor_argv = resolve_editor(env, which=which)
    launcher = pick_launcher(env, which=which, platform=platform)
    if launcher is None:
        raise EditorUnavailable("no terminal overlay available on this platform")

    cwd = env.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    wrapper = target.with_suffix(".command")
    sentinel = target.with_suffix(".done")
    sentinel.unlink(missing_ok=True)
    wrapper.write_text(render_wrapper(editor_argv, target, sentinel, cwd), encoding="utf-8")
    wrapper.chmod(0o755)

    try:
        proc = runner(build_command(launcher, wrapper, cwd), capture_output=True, text=True)
        if getattr(proc, "returncode", 0) != 0 and not sentinel.exists():
            detail = (getattr(proc, "stderr", "") or "").strip()
            raise EditorUnavailable(f"{launcher} could not open an overlay: {detail}")

        deadline = clock() + timeout
        while not sentinel.exists():
            if clock() > deadline:
                raise TimeoutError(
                    f"editor did not finish within {timeout:.0f}s; "
                    f"your text is still at {target}"
                )
            sleep(poll)
        return int((sentinel.read_text(encoding="utf-8").strip() or "1"))
    finally:
        wrapper.unlink(missing_ok=True)
        sentinel.unlink(missing_ok=True)
```

`Path.unlink(missing_ok=True)` requires Python 3.8, which the 3.9 floor satisfies.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_editor.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/editor.py tests/test_editor.py
git commit -m "feat: run the editor in an overlay and wait for its exit status"
```

---

### Task 8: The CLI

**Files:**
- Create: `scripts/todo.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `todo_store` (Tasks 2–5), `editor` (Tasks 6–7).
- Produces:
  - `strip_command(raw: str) -> str`
  - `main(argv: list[str] | None = None) -> int`
  - Subcommands: `add <text...>`, `list [--all] [--json]`, `done <selector>`, `edit <selector>`, `path`
  - Exit codes: `0` success, `1` usage or lookup error, `3` `EditorUnavailable` (the distinct code the command falls back on), `4` edit timed out.

- [ ] **Step 1: Write the failing tests**

`tests/test_cli.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_cli.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'todo'`

- [ ] **Step 3: Write `scripts/todo.py`**

```python
#!/usr/bin/env python3
"""Command line entry point for the claude-todo plugin.

Also the adapter for the UserPromptExpansion hook: `add --from-hook` reads the
hook payload on stdin, appends the item, and asks Claude Code to block the
expansion so capturing an idea never becomes an LLM turn.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import editor
import todo_store

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NO_EDITOR = 3
EXIT_TIMEOUT = 4


def strip_command(raw: str) -> str:
    """Recover the idea text from a raw command line.

    Handles `/todo x`, `/claude-todo:todo x` and a bare `todo x`.
    """
    text = raw.strip()
    if text.startswith("/"):
        text = text[1:]
    head, _, tail = text.partition(" ")
    if head and head.split(":")[-1] == "todo":
        return tail.strip()
    return text.strip()


def _add(args) -> int:
    path = todo_store.resolve_path()
    try:
        item = todo_store.add(path, " ".join(args.text))
    except ValueError as exc:
        print(f"todo: {exc}", file=sys.stderr)
        return EXIT_ERROR
    print(f"todo added: {item.text}")
    return EXIT_OK


def _list(args) -> int:
    path = todo_store.resolve_path()
    shown = todo_store.select(path, only_open=not args.all)
    if args.json:
        every = todo_store.select(path, only_open=False)
        print(
            json.dumps(
                {
                    "path": str(path),
                    "open": sum(1 for item in every if item.open),
                    "total": len(every),
                    "items": [
                        {"n": i.n, "text": i.text, "body": i.body, "done": i.done}
                        for i in shown
                    ],
                },
                ensure_ascii=False,
            )
        )
        return EXIT_OK
    if not shown:
        print("no open todos" if not args.all else "no todos")
        return EXIT_OK
    for item in shown:
        mark = "x" if item.done else " "
        print(f"{item.n}. [{mark}] {item.text}")
        for line in item.body:
            print(f"     {line}")
    return EXIT_OK


def _done(args) -> int:
    path = todo_store.resolve_path()
    try:
        item, changed = todo_store.mark_done(path, args.selector)
    except LookupError as exc:
        print(f"todo: {exc}", file=sys.stderr)
        return EXIT_ERROR
    print(f"todo done: {item.text}" if changed else f"todo already done: {item.text}")
    return EXIT_OK


def _edit(args) -> int:
    path = todo_store.resolve_path()
    try:
        item = todo_store.find(todo_store.select(path), args.selector)
    except LookupError as exc:
        print(f"todo: {exc}", file=sys.stderr)
        return EXIT_ERROR

    scratch = path.parent / f".todo-edit-{item.n}.md"
    scratch.write_text(todo_store.render_item(item), encoding="utf-8")
    try:
        code = editor.edit_file(scratch)
    except editor.EditorUnavailable as exc:
        scratch.unlink(missing_ok=True)
        print(f"todo: {exc}", file=sys.stderr)
        return EXIT_NO_EDITOR
    except TimeoutError as exc:
        print(f"todo: {exc}", file=sys.stderr)
        return EXIT_TIMEOUT

    try:
        if code != 0:
            print(f"todo: editor exited {code}; item unchanged", file=sys.stderr)
            return EXIT_ERROR
        try:
            updated = todo_store.replace(path, args.selector, scratch.read_text(encoding="utf-8"))
        except ValueError as exc:
            print(f"todo: {exc}", file=sys.stderr)
            return EXIT_ERROR
    finally:
        scratch.unlink(missing_ok=True)

    print(f"todo updated: {updated.text}")
    return EXIT_OK


def _path(args) -> int:
    print(todo_store.resolve_path())
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="todo", description="Project todo list")
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="append an item")
    add.add_argument("text", nargs="*")
    add.add_argument("--from-hook", action="store_true", help=argparse.SUPPRESS)
    add.set_defaults(func=_add)

    listing = sub.add_parser("list", help="show items")
    listing.add_argument("--all", action="store_true", help="include completed items")
    listing.add_argument("--json", action="store_true", help="machine-readable output")
    listing.set_defaults(func=_list)

    done = sub.add_parser("done", help="mark an item complete")
    done.add_argument("selector", help="1-based number from `list`, or a substring")
    done.set_defaults(func=_done)

    edit = sub.add_parser("edit", help="open an item in an editor")
    edit.add_argument("selector", help="1-based number from `list`, or a substring")
    edit.set_defaults(func=_edit)

    show = sub.add_parser("path", help="print the todo file path")
    show.set_defaults(func=_path)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```

`--from-hook` is declared here but wired up in Task 9 so this task's tests stay focused on the CLI surface.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_cli.py`
Expected: PASS

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest`
Expected: PASS, all tests green.

- [ ] **Step 6: Commit**

```bash
git add scripts/todo.py tests/test_cli.py
git commit -m "feat: add the todo command line interface"
```

---

### Task 9: The capture hook

**Files:**
- Modify: `scripts/todo.py`
- Create: `hooks/hooks.json`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `_add` and `strip_command` from Task 8.
- Produces: `add --from-hook`, which reads `UserPromptExpansion` JSON on stdin and prints a hook response. Contract:
  - Text present and appended → stdout carries `hookSpecificOutput.block: true`, exit `0`.
  - No text (a bare `/todo`) → **no** stdout, exit `0`, so the picker reaches Claude.
  - Any failure → message on stderr, no `block` in stdout, exit `1`.
  - **Exit code 2 is never used** — it would block the expansion and swallow the fallback.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
def hook_payload(raw):
    return json.dumps(
        {
            "session_id": "s",
            "prompt_id": "p",
            "hook_event_name": "UserPromptExpansion",
            "command_name": "todo",
            "raw_input": raw,
            "expanded_prompt": "...",
        }
    )


def run_hook(monkeypatch, tmp_path, stdin_text, **extra):
    import io

    for key, value in env(tmp_path, **extra).items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin_text))
    return todo.main(["add", "--from-hook"])


def test_hook_appends_and_blocks(monkeypatch, tmp_path, capsys):
    assert run_hook(monkeypatch, tmp_path, hook_payload("/todo create agents")) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["hookSpecificOutput"] == {
        "hookEventName": "UserPromptExpansion",
        "block": True,
    }
    assert "create agents" in payload["systemMessage"]
    assert "- [ ] create agents" in (tmp_path / "TODO.md").read_text()


def test_hook_reports_the_open_count(monkeypatch, tmp_path, capsys):
    run_hook(monkeypatch, tmp_path, hook_payload("/todo one"))
    capsys.readouterr()
    run_hook(monkeypatch, tmp_path, hook_payload("/todo two"))
    assert "2 open" in json.loads(capsys.readouterr().out)["systemMessage"]


def test_hook_does_not_block_a_bare_invocation(monkeypatch, tmp_path, capsys):
    """`/todo` with no text must reach Claude so the picker runs."""
    assert run_hook(monkeypatch, tmp_path, hook_payload("/todo")) == 0
    assert capsys.readouterr().out.strip() == ""
    assert not (tmp_path / "TODO.md").exists()


def test_hook_does_not_block_on_malformed_json(monkeypatch, tmp_path, capsys):
    assert run_hook(monkeypatch, tmp_path, "not json at all") == 1
    assert "block" not in capsys.readouterr().out


def test_hook_does_not_block_when_the_write_fails(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        todo.todo_store, "add", lambda *a, **k: (_ for _ in ()).throw(OSError("read-only"))
    )
    assert run_hook(monkeypatch, tmp_path, hook_payload("/todo x")) == 1
    assert "block" not in capsys.readouterr().out


def test_hook_handles_the_namespaced_command(monkeypatch, tmp_path, capsys):
    assert run_hook(monkeypatch, tmp_path, hook_payload("/claude-todo:todo agents")) == 0
    assert "- [ ] agents" in (tmp_path / "TODO.md").read_text()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -k hook`
Expected: FAIL — `--from-hook` currently falls through to `_add` with empty text and returns 1.

- [ ] **Step 3: Wire up `--from-hook`**

In `scripts/todo.py`, replace `_add` with:

```python
def _add(args) -> int:
    if args.from_hook:
        return _add_from_hook()
    path = todo_store.resolve_path()
    try:
        item = todo_store.add(path, " ".join(args.text))
    except ValueError as exc:
        print(f"todo: {exc}", file=sys.stderr)
        return EXIT_ERROR
    print(f"todo added: {item.text}")
    return EXIT_OK


def _add_from_hook() -> int:
    """Append an item from a UserPromptExpansion payload, then block expansion.

    Blocking is what keeps capture free: the command never becomes an LLM turn.
    Any failure deliberately does NOT block, so the command body reaches Claude
    and the idea still gets recorded, just at the cost of a turn. Exit code 2 is
    never used here; it would block the expansion and swallow that fallback.
    """
    try:
        payload = json.load(sys.stdin)
        text = strip_command(payload.get("raw_input") or "")
    except (json.JSONDecodeError, AttributeError, TypeError) as exc:
        print(f"todo: unreadable hook payload: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if not text:
        # A bare `/todo` opens the picker, which needs Claude. Let it through.
        return EXIT_OK

    try:
        path = todo_store.resolve_path()
        item = todo_store.add(path, text)
        open_count = sum(1 for entry in todo_store.select(path) if entry.open)
    except (OSError, ValueError) as exc:
        print(f"todo: could not record the item: {exc}", file=sys.stderr)
        return EXIT_ERROR

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptExpansion",
                    "block": True,
                },
                "systemMessage": f"todo added: {item.text} ({open_count} open)",
            },
            ensure_ascii=False,
        )
    )
    return EXIT_OK
```

`argparse` exposes `--from-hook` as `args.from_hook`.

- [ ] **Step 4: Create `hooks/hooks.json`**

```json
{
  "hooks": {
    "UserPromptExpansion": [
      {
        "matcher": "todo",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/scripts/todo.py\" add --from-hook",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

Shell form on purpose: the script reads `CLAUDE_PLUGIN_OPTION_*` from the environment, and shell-form plugin hooks reject `${user_config.*}` references.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/todo.py hooks/hooks.json tests/test_cli.py
git commit -m "feat: capture a todo from the prompt-expansion hook without a turn"
```

---

### Task 10: Plugin manifests

**Files:**
- Create: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`
- Test: `tests/test_manifests.py`

**Interfaces:**
- Consumes: `hooks/hooks.json` from Task 9.
- Produces: an installable plugin named `claude-todo` in a marketplace named `claude-todo-plugin`, with `userConfig` keys `todo_file` and `todo_editor`.

- [ ] **Step 1: Write the failing tests**

`tests/test_manifests.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_manifests.py`
Expected: FAIL — `FileNotFoundError` for `.claude-plugin/plugin.json`

- [ ] **Step 3: Create `.claude-plugin/plugin.json`**

```json
{
  "$schema": "https://json.schemastore.org/claude-code-plugin-manifest.json",
  "name": "claude-todo",
  "displayName": "Todo",
  "version": "0.1.0",
  "description": "Capture ideas while Claude works, then pick them back up. /todo <text> records an idea without costing a turn; /todo on its own opens a picker over what is still open.",
  "author": { "name": "pharmazone" },
  "homepage": "https://github.com/pharmazone/claude-todo-plugin",
  "repository": "https://github.com/pharmazone/claude-todo-plugin",
  "license": "MIT",
  "keywords": ["todo", "tasks", "notes", "productivity", "workflow"],
  "userConfig": {
    "todo_file": {
      "type": "string",
      "title": "Todo file",
      "description": "Where the todo list lives. Relative paths resolve against the project root.",
      "default": ".claude/TODO.md"
    },
    "todo_editor": {
      "type": "string",
      "title": "Editor command",
      "description": "Editor used by the Edit action, overriding $VISUAL and $EDITOR. Example: nvim --clean",
      "required": false
    }
  }
}
```

- [ ] **Step 4: Create `.claude-plugin/marketplace.json`**

```json
{
  "name": "claude-todo-plugin",
  "owner": {
    "name": "pharmazone",
    "url": "https://github.com/pharmazone"
  },
  "plugins": [
    {
      "name": "claude-todo",
      "source": "./",
      "description": "Capture ideas while Claude works, then pick them back up.",
      "version": "0.1.0",
      "author": { "name": "pharmazone" }
    }
  ]
}
```

- [ ] **Step 5: Create the directories the root test requires**

`commands/` and `skills/` are filled in by Task 11. Create them now with a placeholder-free `.gitkeep` so this task's tests pass on their own:

```bash
mkdir -p commands skills
touch commands/.gitkeep skills/.gitkeep
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/test_manifests.py`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add .claude-plugin commands skills tests/test_manifests.py
git commit -m "feat: add the plugin and marketplace manifests"
```

---

### Task 11: The command and the skill

**Files:**
- Create: `commands/todo.md`, `skills/todo-workflow/SKILL.md`
- Delete: `commands/.gitkeep`, `skills/.gitkeep`

**Interfaces:**
- Consumes: the CLI from Tasks 8–9.
- Produces: `/todo` (also reachable as `/claude-todo:todo`) and the `claude-todo:todo-workflow` skill.

- [ ] **Step 1: Create `commands/todo.md`**

````markdown
---
description: Capture an idea without interrupting Claude, or pick up an open todo. `/todo <text>` records it; `/todo` alone opens the picker.
argument-hint: "[idea text, or empty to pick from open todos]"
disable-model-invocation: true
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/todo.py *), AskUserQuestion
---

# Todo

The todo list is a markdown file the user owns. Everything below goes through
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/todo.py`; never edit the file directly with
Read/Edit/Write, because the script makes line-level edits that preserve the prose
around the list.

Arguments: $ARGUMENTS

## If arguments were given

You are on the fallback path — normally the capture hook records the idea with no turn
at all, and you never see it. The hook did not fire, so record it now:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/todo.py" add "$ARGUMENTS"
```

Confirm in one short line. Do not start working on it, and do not ask a follow-up
question: the user is mid-flight on something else and wants the idea parked, not
discussed.

## If no arguments were given

1. List what is open:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/todo.py" list --json
   ```

2. If `open` is 0, say there are no open todos and stop. Do not open a dialog.

3. Print the open items as a numbered markdown list so the user can see all of them.

4. Ask with a single `AskUserQuestion` carrying two questions:

   - **"Which todo?"** — one option per item, using the item's text as the label and the
     first line of its body as the description. `AskUserQuestion` allows at most four
     options: with four or fewer items list them all; with more, list the first three and
     add a fourth option labelled "More" that makes you re-ask with the next three.
   - **"What should I do with it?"** — exactly these three options, in this order:
     **Work on it** ("Hand me the item as the task and start"), **Edit it** ("Open it in
     your editor to reword or add notes"), **Mark done** ("Tick it off without working
     on it").

5. Act on the pair of answers:

   - **Work on it** — treat the item's text and body as the task and start on it. When
     the work is finished, mark it done as described under "Finishing an item" below.
   - **Edit it** — run the editor, using the item's number from step 1:

     ```bash
     python3 "${CLAUDE_PLUGIN_ROOT}/scripts/todo.py" edit <n>
     ```

     The editor opens in a terminal overlay and the command blocks until it closes.
     Exit code 3 means no editor or overlay is available: fall back to asking the user
     what the item should say, then rerun with their text piped in. Exit code 4 means
     the edit timed out; tell the user and offer to retry.
   - **Mark done** — run the `done` command below and confirm.

## Finishing an item

The moment work on a todo is complete, tick it off:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/todo.py" done "<number or a distinctive substring>"
```

A substring is usually the better selector: numbers shift as items are completed, but the
text does not. This rule stands for the rest of the session, not just this turn.

## When you run out of work

If a task finishes and there is no clear next step, run the `list --json` command above.
If anything is open, offer the picker from step 4 rather than asking an open-ended
"what next?".
````

- [ ] **Step 2: Create `skills/todo-workflow/SKILL.md`**

````markdown
---
name: todo-workflow
description: Use when a task is finished and there is no clear next step, when the user asks what is left or what to do next, or when work on a todo item completes and it needs ticking off. Reads the project todo list and offers the open items as a picker.
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/todo.py *), AskUserQuestion
---

# Todo workflow

The project keeps a markdown todo list that the user fills with ideas captured mid-run.
Two moments matter: when work finishes, and when you do not know what to do next.

Always go through `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/todo.py`. Never edit the todo
file with Read/Edit/Write: the script makes line-level edits so the prose a human wrote
around the list survives.

## When work on a todo item finishes

Tick it off immediately:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/todo.py" done "<a distinctive substring of the item>"
```

Prefer a substring over a number. Numbers shift as items are completed; the text does not.

## When there is no clear next step

Rather than asking an open-ended "what would you like to do next?", look at what is
already recorded:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/todo.py" list --json
```

If `open` is 0, say so and stop — do not invent work. Otherwise print the open items as a
numbered list, then offer them with a single `AskUserQuestion` carrying two questions:
**"Which todo?"** (one option per item, at most four, using a fourth "More" option to
page when there are more) and **"What should I do with it?"** with the options **Work on
it**, **Edit it**, and **Mark done**.

Run `todo.py edit <n>` for the edit action; it opens the item in the user's editor inside
a terminal overlay and blocks until they close it.

## What not to do

Do not add todos on your own initiative. The list is the user's capture buffer, and items
appearing in it that they did not write make it untrustworthy. `/todo <text>` is theirs
to run.
````

- [ ] **Step 3: Remove the placeholders**

```bash
rm commands/.gitkeep skills/.gitkeep
```

- [ ] **Step 4: Verify the manifest tests still pass**

Run: `uv run pytest tests/test_manifests.py`
Expected: PASS — `commands/` and `skills/` still exist, now with real content.

- [ ] **Step 5: Commit**

```bash
git add commands skills
git commit -m "feat: add the /todo command and the todo-workflow skill"
```

---

### Task 12: Documentation

**Files:**
- Create: `README.md`, `CONTRIBUTING.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: everything above.
- Produces: install and contribution docs.

- [ ] **Step 1: Write `README.md`**

Cover, in this order:

1. **What it is** — one paragraph: capture an idea while Claude is working, pick it up later.
2. **Install**

   ```
   /plugin marketplace add pharmazone/claude-todo-plugin
   /plugin install claude-todo@claude-todo-plugin
   ```

3. **Usage** — `/todo <text>` to capture, `/todo` to pick, the three picker actions, and automatic done-marking.
4. **How capture stays free** — the honest version, stated plainly:

   > Typing `/todo <idea>` while Claude is working does not interrupt it. Like any
   > message, it queues and Claude keeps going. When it runs, a `UserPromptExpansion`
   > hook writes the line and blocks the expansion, so it never becomes a Claude turn:
   > no tokens, no context. It is not the same as `/btw`, which is a built-in with its
   > own side-channel and no file access — a plugin command cannot run mid-turn. What it
   > does guarantee is that capturing an idea never derails the run and never costs a
   > turn.

5. **Instant capture from any terminal** — the shell alias, for when you want the write to land immediately rather than at end of turn:

   ```sh
   alias todo='python3 ~/.claude/plugins/cache/claude-todo-plugin/claude-todo/*/scripts/todo.py add'
   ```

   Note that `CLAUDE_PROJECT_DIR` is unset outside Claude Code, so the path resolves against the current directory — run it from the project root.
6. **The file** — the markdown format, that it is human-editable, and that the plugin never rewrites the prose around the list. State that the plugin does **not** touch `.gitignore`: commit `.claude/TODO.md` to share the list with the team, or add it to `.gitignore` to keep it private.
7. **Configuration** — the `todo_file` and `todo_editor` options and the `CLAUDE_TODO_FILE` environment override.
8. **The editor** — the resolution order, that auto-detected `nvim`/`vim` start with no config or plugins (so no file-tree sidebar), that an editor you configure yourself is used verbatim, and the overlay table (agterm, kitty, tmux, WezTerm, macOS Terminal) with the graceful fallback when none is available.
9. **Contributing** — pointer to `CONTRIBUTING.md`.
10. **License** — MIT.

- [ ] **Step 2: Write `CONTRIBUTING.md`**

Cover:

1. **Dev setup** — `uv sync`, `uv run pytest`.
2. **Testing the plugin locally** — from the repo's parent directory:

   ```
   /plugin marketplace add ./claude-todo-plugin
   /plugin install claude-todo@claude-todo-plugin
   ```

   Reload the session after changing `hooks.json` or the manifests.
3. **Layout** — the file-structure table from this plan.
4. **House rules** — standard library only at runtime (the hook runs bare `python3`); the todo file is human-owned so every mutation stays a line-level edit; functional pytest, no test classes; conventional commit messages, no emoji.
5. **Adding a terminal launcher** — add a branch to `pick_launcher`, a branch to `build_command`, and a test for each; the wrapper-plus-sentinel mechanism means a new launcher does not need to block.

- [ ] **Step 3: Update `CHANGELOG.md`**

Move the entries under a `## [0.1.0] - 2026-08-17` heading and leave `## [Unreleased]` empty above it.

- [ ] **Step 4: Verify the suite still passes**

Run: `uv run pytest`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add README.md CONTRIBUTING.md CHANGELOG.md
git commit -m "docs: add README and contributing guide"
```

---

### Task 13: Live verification and publication

**Files:**
- Modify: `README.md` (record what the two unknowns actually do)

**Interfaces:**
- Consumes: the finished plugin.
- Produces: a verified install and a public repo.

This task resolves the two behaviours the docs do not fully specify. Both were flagged in the spec as implementation-time questions.

- [ ] **Step 1: Install the plugin locally**

```
/plugin marketplace add ~/project/claude-todo-plugin
/plugin install claude-todo@claude-todo-plugin
```

- [ ] **Step 2: Verify capture end to end**

Run `/todo verify capture works` in a session. Check:
- `.claude/TODO.md` gained `- [ ] verify capture works`
- no assistant turn was produced
- whether the `systemMessage` text appeared to the user

Record the `systemMessage` answer in the README. If it is discarded on this event, drop the promise of on-screen confirmation from the README and say the write is silent.

- [ ] **Step 3: Verify the matcher**

Confirm the hook fires for both `/todo x` and `/claude-todo:todo x`. If `matcher: "todo"` misses the namespaced form, widen it to `"todo$"` in `hooks/hooks.json` and re-test.

- [ ] **Step 4: Verify the picker**

Run `/todo` with three or more open items. Confirm the numbered list prints, the dialog offers both questions, and "Work on it" hands the item over.

- [ ] **Step 5: Verify the editor overlay**

Run `/todo`, choose an item and **Edit it**. This session runs inside agterm, so expect an `agtermctl` overlay at 80% running `nvim --clean` with no file-tree sidebar. Confirm that saving and quitting splices the text back and that the surrounding prose in the file is untouched.

- [ ] **Step 6: Verify done-marking**

Pick an item, let it complete, confirm it flips to `- [x]` and that the prose around it survives.

- [ ] **Step 7: Record the findings**

Update the README's capture section with the observed behaviour. Commit:

```bash
git add README.md hooks/hooks.json
git commit -m "docs: record verified hook behaviour"
```

- [ ] **Step 8: Ask before publishing**

Creating a public repo is outward-facing and hard to reverse. Show the user the exact command and wait for explicit approval:

```bash
gh repo create pharmazone/claude-todo-plugin --public \
  --source ~/project/claude-todo-plugin \
  --description "Capture ideas while Claude Code works, then pick them back up" \
  --remote origin --push
```

Note `gh` has two accounts authenticated on this machine and `pharmazone` is **not** the active one. Either pass `--gh-host`/switch with `gh auth switch --user pharmazone` first, or confirm with the user which account should own the repo.

- [ ] **Step 9: Push and verify**

After approval, run the command, then confirm the repo is public and that a clean install works:

```
/plugin marketplace add pharmazone/claude-todo-plugin
/plugin install claude-todo@claude-todo-plugin
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| Storage format, human-owned invariant | 2, 3, 4, 5 |
| Path resolution precedence | 2 |
| Flow 1 — capture hook, degradation | 9 |
| Flow 2 — picker, four-option cap, pagination | 11 |
| Flow 3 — editor resolution, launcher table, sentinel, timeout, fallback | 6, 7, 8, 11 |
| Flow 4 — done-marking by substring | 4, 8, 11 |
| Flow 5 — skill guidance, no Stop hook | 11 |
| Permissions — `allowed-tools`, `disable-model-invocation` | 11 |
| Configuration — `userConfig` | 10 |
| Testing | 2–10 |
| Distribution — marketplace, README, CONTRIBUTING | 10, 12, 13 |
| Two empirical unknowns | 13 |

No gaps.

**Placeholder scan:** the only `.gitkeep` files are created in Task 10 and deleted in Task 11, which is a real sequencing need rather than a placeholder. Every code step carries runnable code.

**Type consistency:** `Item` fields (`n`, `line`, `text`, `done`, `body`) are used identically in Tasks 2–5, 8 and 9. `resolve_path`, `read_lines`, `write_lines`, `parse`, `select`, `find`, `add`, `mark_done`, `render_item`, `replace` keep the same signatures wherever they appear. `editor.edit_file` is called with a single positional `Path` in Task 8 and defined with that signature in Task 7; the Task 8 fakes accept `**kwargs`, matching. Exit codes `0/1/3/4` agree between Task 8's definition, its tests, and the command body in Task 11.
