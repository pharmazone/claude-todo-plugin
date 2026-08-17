import pytest

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
