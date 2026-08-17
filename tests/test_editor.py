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
