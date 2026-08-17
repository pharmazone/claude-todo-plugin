# claude-todo

Capture an idea while Claude is working, without breaking its stride, and pick
it back up when you're ready. `/todo <idea>` drops a line into a project todo
list at essentially no cost; `/todo` on its own opens a picker over what's
still open so Claude can work the item, edit it, or tick it off.

## Install

```
/plugin marketplace add pharmazone/claude-todo-plugin
/plugin install claude-todo@claude-todo-plugin
```

## Usage

Run `/todo <text>` any time an idea occurs to you, whether or not Claude is
mid-turn. It gets appended to the todo list as a new open item.

Run `/todo` with no arguments to see what's open. Claude lists the open items
and asks two things: which one, and what to do with it. The second question
has three options:

- **Work on it** — Claude takes the item's text (and any notes under it) as
  the task and starts.
- **Edit it** — Claude opens the item in your editor, in a terminal overlay,
  so you can reword it or add notes.
- **Mark done** — the item is ticked off without anyone working on it.

You don't have to mark anything done yourself: once Claude finishes work it
picked up from the list — whether that started from "Work on it" above or
from noticing an open item once it runs out of other things to do — it ticks
the item off as the last step.

## How capture stays free

> Typing `/todo <idea>` while Claude is working does not interrupt it. Like any
> message, it queues and Claude keeps going. When it runs, a `UserPromptExpansion`
> hook writes the line and blocks the expansion, so it never becomes a Claude turn:
> no tokens, no context. It is not the same as `/btw`, which is a built-in with its
> own side-channel and no file access — a plugin command cannot run mid-turn. What it
> does guarantee is that capturing an idea never derails the run and never costs a
> turn.

## Instant capture from any terminal

`/todo` still has to wait its turn in the queue before the hook writes it. If
you want the write to land immediately — say, from a plain shell, with no
Claude Code session involved at all — add an alias:

```sh
alias todo='python3 ~/.claude/plugins/cache/claude-todo-plugin/claude-todo/*/scripts/todo.py add'
```

`CLAUDE_PROJECT_DIR` is only set inside a Claude Code session, so outside one
the todo path resolves against the current directory instead — run the alias
from the project root.

## The file

The list lives at `.claude/TODO.md` (configurable, see below) as plain
Markdown: a `# TODO` heading and a checklist, `- [ ] like this` for open items
and `- [x] like this` once done. Indented lines directly under an item are
kept as its notes.

The file is yours. Every edit the plugin makes is a line-level insert or
find-and-replace against the existing text, never a parse-and-regenerate — so
any headings, prose, or extra blank lines you put around the list are left
exactly as you wrote them. Only the top-level checklist items are ever
touched.

The plugin does not touch `.gitignore`. Commit `.claude/TODO.md` if you want
the list shared with the rest of the team, or add it to `.gitignore` yourself
if you'd rather keep it private.

## Configuration

Two plugin settings, under `/plugin`:

- **`todo_file`** — where the list lives. Relative paths resolve against the
  project root; default is `.claude/TODO.md`.
- **`todo_editor`** — the command used to open an item for the Edit action,
  overriding `$VISUAL` and `$EDITOR`.

For use outside a Claude Code session (the shell alias above, for instance),
the `CLAUDE_TODO_FILE` environment variable overrides `todo_file` the same
way — and wins over it if both are set.

## The editor

The Edit action resolves an editor in this order:

1. the `todo_editor` plugin setting
2. `$VISUAL`
3. `$EDITOR`
4. the first of `nvim`, `vim`, or `nano` found on `$PATH`

An editor from any of the first three is run exactly as you wrote it — your
own flags, your own config. Auto-detection is different: it starts `nvim
--clean` or `vim -u NONE -N`, deliberately with no config and no plugins, so
you get a plain buffer to type into rather than, say, a file-tree sidebar
staring back at you.

The editor needs somewhere to run, so the plugin opens a terminal overlay
appropriate to where you're working:

| Terminal | Overlay |
|---|---|
| agterm | a blocking session overlay via `agtermctl` |
| kitty | an overlay window via `kitty @ launch` |
| tmux | a popup via `tmux display-popup` |
| WezTerm | a new window via `wezterm cli spawn` |
| macOS Terminal (fallback) | a new Terminal.app window via `open -a Terminal` |

If none of these is available, the Edit action fails rather than hang:
`todo.py edit` exits with a distinct code for "no editor or overlay" versus
"the editor timed out," and Claude falls back to asking you for the corrected
text directly instead of leaving you stuck.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for local dev setup, testing the
plugin against a real Claude Code session, and the project layout.

## License

MIT. See [LICENSE](LICENSE).
