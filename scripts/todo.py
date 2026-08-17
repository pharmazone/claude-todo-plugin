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
