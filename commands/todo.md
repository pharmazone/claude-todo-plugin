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
