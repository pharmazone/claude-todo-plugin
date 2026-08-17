# Contributing

## Dev setup

```
uv sync
uv run pytest
```

## Testing the plugin locally

From the repo's parent directory:

```
/plugin marketplace add ./claude-todo-plugin
/plugin install claude-todo@claude-todo-plugin
```

Reload the session after changing `hooks.json` or the manifests — Claude Code
reads those at session start.

## Layout

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

## House rules

- **Standard library only at runtime.** The `UserPromptExpansion` hook runs
  bare `python3` — no virtualenv, no third-party package. Anything under
  `scripts/` has to work with nothing beyond what ships with Python.
- **The todo file is human-owned.** Every mutation is a line-level edit.
  Never parse it into a model and re-serialize it — headings, prose, and
  blank lines around the list must survive untouched.
- **Tests are functional pytest.** Plain `test_*` functions, `tmp_path`, no
  test classes.
- **Commit messages are conventional commits.** No emoji.

## Adding a terminal launcher

New launcher support means two branches and two tests:

1. A branch in `pick_launcher` (`scripts/editor.py`) that recognizes the
   terminal and returns its name.
2. A branch in `build_command` that turns that name into the command that
   opens an overlay and runs the wrapper script inside it.
3. A test for each of the two branches above.

You don't need to make the new launcher block until the editor exits. Every
launcher runs the same generated wrapper, which writes the editor's exit code
to a sentinel file when it finishes; `edit_file` polls for that sentinel
regardless of whether the launcher itself blocks or returns immediately, so
both styles of launcher work without special-casing.
