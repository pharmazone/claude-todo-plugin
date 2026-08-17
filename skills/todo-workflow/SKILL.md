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
