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
