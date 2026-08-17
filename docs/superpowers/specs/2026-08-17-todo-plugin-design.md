# claude-todo-plugin — Design

Date: 2026-08-17
Status: approved for planning

## Problem

While Claude Code is working, ideas arrive. Today the only way to record one is to
interrupt the turn or hold it in your head. Both are bad: the first derails Claude,
the second loses the idea.

This plugin gives you a `/todo` command that captures an idea without derailing the
run, lists what is still open, hands a chosen item to Claude as the next task, and
marks it done when Claude finishes.

## Constraint discovered during design

The original request asked for `/todo` to behave like `/btw` — to run mid-turn without
interrupting. **This is not reachable for a plugin command**, and the design does not
pretend otherwise:

- `/btw` is a built-in with a dedicated side-channel. It is "available while Claude is
  working", but it has **no tool access**: it "answers only from what is already in
  context. Claude can't read files, run commands, or search." It could not write a todo
  file even if a plugin could hook into it.
- Only `/status`, `/tasks`, and `/usage` run immediately. Every other command,
  including every plugin command, queues: "If you send a command while Claude is
  responding, it queues and runs after the current turn finishes."
- No frontmatter field or hook event opts a custom command into the immediate path.

**What we deliver instead.** Typing `/todo <idea>` mid-turn never interrupts Claude — it
queues like any message and Claude keeps working. When it dequeues, a
`UserPromptExpansion` hook writes the line to disk and blocks the expansion, so it never
becomes a Claude turn: **zero tokens, zero context**. The idea is captured and Claude's
train of thought is untouched. The only residual gap versus `/btw` is that the disk write
lands at end-of-turn rather than at keypress.

For genuinely instant, out-of-band capture, the same script ships as a standalone CLI and
the README documents a shell alias, so `todo "idea"` works from any terminal at any time.

## Component map

```
claude-todo-plugin/
├── .claude-plugin/
│   ├── plugin.json          manifest, userConfig
│   └── marketplace.json     repo doubles as its own marketplace
├── commands/todo.md         the /todo command
├── skills/todo-workflow/SKILL.md   standing guidance: next-step picker, done-marking
├── hooks/hooks.json         UserPromptExpansion, matcher: todo
├── scripts/
│   ├── todo.py              stdlib CLI: add | list | done | edit | path
│   └── editor.py            editor resolution + terminal-overlay launcher
├── tests/                   pytest, functional
├── .github/workflows/ci.yml
├── README.md  CONTRIBUTING.md  LICENSE  CHANGELOG.md
```

Every unit is independently testable: `todo.py` is file-in/file-out, `editor.py` is a pure
function of the environment plus one subprocess call.

## Storage

Default `.claude/TODO.md`, relative to `CLAUDE_PROJECT_DIR`. Plain GitHub-flavored
markdown, no IDs and no timestamps:

```markdown
# TODO

- [ ] create tik-tak-toe agents
  Use the agent scaffold in src/agents/. Two players, minimax.
- [ ] fix the login redirect
- [x] add dark mode
```

Indented lines beneath an item are its body — this is what the **Edit** flow writes.

**Firm principle: the file is human-owned.** All mutations are line-level edits. The
script never parses the file into a model and re-serializes it, so headings, prose,
blank lines, and anything else a human puts in the file survive untouched. New items
append after the last list item.

Path resolution, first hit wins:

1. `$CLAUDE_TODO_FILE`
2. `$CLAUDE_PLUGIN_OPTION_TODO_FILE` (from `userConfig.todo_file`)
3. `.claude/TODO.md`

A relative path resolves against `$CLAUDE_PROJECT_DIR`, falling back to the working
directory. Parent directories are created on first write.

## Flow 1 — capture: `/todo <text>`

`hooks/hooks.json` registers a `UserPromptExpansion` hook with `matcher: "todo"`. On fire
it runs `python3 "$CLAUDE_PLUGIN_ROOT"/scripts/todo.py add --from-hook`, reading the hook
JSON on stdin. The script takes `raw_input`, strips the leading command token, appends
`- [ ] <text>`, and emits:

```json
{
  "hookSpecificOutput": {"hookEventName": "UserPromptExpansion", "block": true},
  "systemMessage": "todo added: create tik-tak-toe agents (3 open)"
}
```

`block: true` stops the expansion, so no LLM turn happens. Cost is one `python3` process.

**Degradation is deliberate.** If hooks are disabled, the script is missing, or it exits
non-zero, the expansion is *not* blocked and the command body reaches Claude, which
appends the item through the same script. The idea is never lost — the fallback just
costs a turn.

Two behaviors the docs do not fully specify, to be settled empirically during
implementation and then documented in the README:

- whether `systemMessage` is surfaced to the user on a blocked expansion (the common
  hook schema notes "discarded by some events");
- the exact moment `UserPromptExpansion` fires relative to queueing.

Neither affects the architecture; both affect what the README promises.

## Flow 2 — pick: `/todo` with no arguments

`commands/todo.md` runs `todo.py list --open --json`, prints the numbered open items as
text, then opens one `AskUserQuestion` with two linked questions:

- **Which item** — `AskUserQuestion` caps options at four. With four or fewer open items,
  all appear. With more, the first three appear plus a "More" option that re-asks with
  the next page. The complete numbered list is printed above the dialog either way, so
  nothing is hidden.
- **What to do** — *Work on it* (default) / *Edit it* / *Mark done*.

*Work on it* feeds the item's text and body to Claude as the task. *Mark done* calls
`todo.py done`. *Edit it* enters flow 3.

With no open items, the command says so and does not open a dialog.

## Flow 3 — edit in a real editor

Claude runs `todo.py edit <n>` via Bash. The script writes the item's text and body to a
temp file, opens it in an editor inside a terminal overlay, waits, then splices the result
back as the item's text and body. An emptied file is treated as "no change" rather than as
a deletion.

### Editor resolution

1. `$CLAUDE_PLUGIN_OPTION_TODO_EDITOR` (from `userConfig.todo_editor`)
2. `$VISUAL`
3. `$EDITOR`
4. first present of `nvim --clean`, `vim -u NONE -N`, `nano`
5. otherwise `EditorUnavailable`

`--clean` / `-u NONE` apply **only to auto-detection**, which is what satisfies the
"nvim without NeoTree or any plugin" requirement — `nvim --clean` loads no user config
and no plugins while keeping defaults and syntax highlighting (verified against nvim
0.12.4). An editor the user configured explicitly is honored verbatim; we do not
second-guess their own setting.

### Overlay launcher

Detected in order, first match wins:

| Terminal | Detection | Launch |
|---|---|---|
| agterm | `AGTERM_ENABLED=1` and `agtermctl` on PATH | `agtermctl session overlay open "<cmd>" --block --size-percent 80` |
| kitty | `$KITTY_LISTEN_ON` set, or `TERM=xterm-kitty` and `kitty @ ls` succeeds | `kitty @ launch --type=overlay --wait-for-child-to-exit --cwd <dir> -- <cmd>` |
| tmux | `$TMUX` set | `tmux display-popup -E -w 90% -h 90% -d <dir> "<cmd>"` |
| WezTerm | `$WEZTERM_PANE` set | `wezterm cli spawn --new-window --cwd <dir> -- <cmd>` |
| macOS | `darwin`, nothing above matched | `open -a Terminal <wrapper>` |
| none | — | `EditorUnavailable` |

All five launch paths and `nvim --clean` were verified to exist on this machine before
being written into the design.

### One completion mechanism for all launchers

Some launchers block (agterm `--block`, kitty `--wait-for-child-to-exit`) and some return
immediately (wezterm, `open -a Terminal`). Rather than special-casing each, every launcher
runs the editor wrapped:

```sh
sh -c '<editor> <tmp>; echo $? > <tmp>.done'
```

and the caller polls for `<tmp>.done`. One mechanism, uniform behavior, and the exit
status comes back the same way everywhere.

**Timeout.** The Bash tool caps at 600s, so polling gives up at 570s and reports that the
edit timed out and `/todo` can be re-run. The temp file is left on disk and named in the
message so nothing typed is lost.

**Last-resort fallback.** On `EditorUnavailable` the script exits with a distinct code and
the command falls back to Claude asking what to add and writing it directly. Editing
always works; the overlay is a comfort, not a dependency.

## Flow 4 — marking done

After Claude finishes work on a picked item it runs `todo.py done <index-or-substring>`,
flipping `- [ ]` to `- [x]` in place. Accepting a substring matters because by the time
work finishes, Claude has the item's text but not necessarily its index.

The rule lives in **both** `skills/todo-workflow/SKILL.md` and the body of
`commands/todo.md`. Command bodies persist in context for the session, so once `/todo`
has been used the guidance is present regardless of whether the skill was loaded.

## Flow 5 — "what next?"

Skill guidance only; no `Stop` hook. A `Stop` hook would fire after *every* turn including
ones that were just a question, and blocking the turn to nag about todos is worse than the
problem it solves.

`skills/todo-workflow/SKILL.md` carries a description that triggers on finishing a task
with no clear next step, and instructs Claude to read the open items and offer the flow-2
picker.

## Permissions

Flows 2, 3, and 4 are Claude calling `scripts/todo.py` through Bash. Without
pre-approval, every `/todo` would raise a permission prompt, which defeats the point of a
low-friction capture tool. `commands/todo.md` therefore declares:

```yaml
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/todo.py *), AskUserQuestion
disable-model-invocation: true
argument-hint: "[idea text, or empty to pick from open todos]"
```

`${CLAUDE_PLUGIN_ROOT}` is substituted in both the command body and its `allowed-tools`
Bash rule, so the rule matches the exact command the body tells Claude to run.
`disable-model-invocation: true` keeps Claude from firing a command with side effects on
its own — the user decides when a todo is created.

`skills/todo-workflow/SKILL.md` carries the same `allowed-tools` grant, since flow 5 has
Claude reading open items on its own initiative rather than through the command. The skill
stays model-invocable — only the command is user-only.

Flow 1 needs no permission: the hook is the harness running a script, not a tool call.

## Configuration

`plugin.json` `userConfig`:

| Key | Type | Default | Purpose |
|---|---|---|---|
| `todo_file` | string | `.claude/TODO.md` | Where the list lives |
| `todo_editor` | string | (unset) | Editor command, overriding `$VISUAL`/`$EDITOR` |

Both reach hooks and scripts as `CLAUDE_PLUGIN_OPTION_TODO_FILE` /
`CLAUDE_PLUGIN_OPTION_TODO_EDITOR`. The hook is shell-form, so it reads the environment
variables rather than `${user_config.*}`, which shell-form plugin hooks reject.

## Testing

`pytest`, functional style, run with `uv run pytest`. Python 3.9+, standard library only
at runtime so the hook never depends on `uv` being installed.

- `todo.py`: add to missing file, add to existing list, list open vs all, done by index,
  done by substring, done on an already-done item is a no-op, edit splices text and body,
  unicode, an empty file, and — the important one — **surrounding prose and headings
  survive every mutation**.
- Path resolution: each precedence rung, relative against `CLAUDE_PROJECT_DIR`, absolute
  passed through.
- `editor.py`: resolution order and the launcher table, both driven by a faked
  environment, with the subprocess call captured rather than executed.
- Hook contract: real `UserPromptExpansion` JSON on stdin produces `block: true` and the
  expected file mutation; a malformed payload exits non-zero **without** blocking, so the
  fallback path engages.

CI runs the suite on push and validates `plugin.json` and `marketplace.json` parse.

## Distribution

Public repo `pharmazone/claude-todo-plugin`, MIT. `.claude-plugin/marketplace.json` at the
repo root makes the repo its own marketplace:

```
/plugin marketplace add pharmazone/claude-todo-plugin
/plugin install todo@claude-todo-plugin
```

`README.md` covers install, the four flows, configuration, the shell-alias recipe for
out-of-band capture, and an honest statement of the queueing behavior above.
`CONTRIBUTING.md` covers the `uv` dev setup, `uv run pytest`, and the local plugin
development loop via `/plugin marketplace add ./claude-todo-plugin`.

## Out of scope

Due dates, priorities, tags, sub-tasks, cross-project rollup, sync to external trackers,
and any TUI of our own. The file is markdown a human can edit by hand; that is the
feature.
