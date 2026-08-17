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
