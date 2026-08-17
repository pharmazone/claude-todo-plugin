"""Open a file in the user's editor, inside whatever overlay this terminal offers.

Knows nothing about todos. Given a path, it works out which editor to run and
which terminal can host it, then runs the editor there and reports its exit
status.

Every launcher runs the same generated wrapper script, which writes the
editor's exit code to a sentinel file when it finishes. Some launchers block
until the editor exits and some return immediately; polling for the sentinel
covers both without special-casing either.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Mapping, Optional

DEFAULT_EDITORS = (
    ("nvim", ["nvim", "--clean"]),
    ("vim", ["vim", "-u", "NONE", "-N"]),
    ("nano", ["nano"]),
)

OVERLAY_SIZE_PERCENT = "80"


class EditorUnavailable(RuntimeError):
    """No editor, or no terminal able to host one."""


def resolve_editor(
    env: Optional[Mapping[str, str]] = None,
    which: Callable[[str], Optional[str]] = shutil.which,
) -> list[str]:
    env = _env(env)
    for key in ("CLAUDE_PLUGIN_OPTION_TODO_EDITOR", "VISUAL", "EDITOR"):
        configured = (env.get(key) or "").strip()
        if configured:
            # Honoured verbatim: the user's own choice, their own config.
            return shlex.split(configured)
    for name, argv in DEFAULT_EDITORS:
        if which(name):
            # Auto-detected only, so start clean: no user config, no plugins.
            return list(argv)
    raise EditorUnavailable(
        "no editor found; set $EDITOR or the plugin's todo_editor option"
    )


def pick_launcher(
    env: Optional[Mapping[str, str]] = None,
    which: Callable[[str], Optional[str]] = shutil.which,
    platform: str = sys.platform,
) -> Optional[str]:
    env = _env(env)
    if env.get("AGTERM_ENABLED") == "1" and which("agtermctl"):
        return "agterm"
    if (env.get("KITTY_LISTEN_ON") or env.get("TERM") == "xterm-kitty") and which("kitty"):
        return "kitty"
    if env.get("TMUX") and which("tmux"):
        return "tmux"
    if env.get("WEZTERM_PANE") and which("wezterm"):
        return "wezterm"
    if platform == "darwin":
        return "macos"
    return None


def render_wrapper(
    editor_argv: list[str], target: Path, sentinel: Path, cwd: str
) -> str:
    command = shlex.join([*editor_argv, str(target)])
    return (
        "#!/bin/sh\n"
        f"cd {shlex.quote(cwd)}\n"
        f"{command}\n"
        f"echo $? > {shlex.quote(str(sentinel))}\n"
    )


def build_command(launcher: str, wrapper: Path, cwd: str) -> list[str]:
    run_wrapper = f"sh {wrapper}"
    if launcher == "agterm":
        return [
            "agtermctl", "session", "overlay", "open", run_wrapper,
            "--block", "--size-percent", OVERLAY_SIZE_PERCENT,
        ]
    if launcher == "kitty":
        return [
            "kitty", "@", "launch", "--type=overlay",
            "--wait-for-child-to-exit", "--cwd", cwd, "sh", str(wrapper),
        ]
    if launcher == "tmux":
        return [
            "tmux", "display-popup", "-E", "-w", "90%", "-h", "90%",
            "-d", cwd, run_wrapper,
        ]
    if launcher == "wezterm":
        return [
            "wezterm", "cli", "spawn", "--new-window", "--cwd", cwd,
            "--", "sh", str(wrapper),
        ]
    if launcher == "macos":
        return ["open", "-a", "Terminal", str(wrapper)]
    raise EditorUnavailable(f"unknown launcher {launcher!r}")


def _env(env: Optional[Mapping[str, str]]) -> Mapping[str, str]:
    return os.environ if env is None else env


def edit_file(
    target: Path,
    env: Optional[Mapping[str, str]] = None,
    timeout: float = 570.0,
    poll: float = 0.2,
    which: Callable[[str], Optional[str]] = shutil.which,
    platform: str = sys.platform,
    runner: Callable[..., object] = subprocess.run,
    sleep: Callable[[float], object] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    env = _env(env)
    editor_argv = resolve_editor(env, which=which)
    launcher = pick_launcher(env, which=which, platform=platform)
    if launcher is None:
        raise EditorUnavailable("no terminal overlay available on this platform")

    cwd = env.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    wrapper = target.with_suffix(".command")
    sentinel = target.with_suffix(".done")
    sentinel.unlink(missing_ok=True)
    wrapper.write_text(render_wrapper(editor_argv, target, sentinel, cwd), encoding="utf-8")
    wrapper.chmod(0o755)

    try:
        proc = runner(build_command(launcher, wrapper, cwd), capture_output=True, text=True)
        if getattr(proc, "returncode", 0) != 0 and not sentinel.exists():
            detail = (getattr(proc, "stderr", "") or "").strip()
            raise EditorUnavailable(f"{launcher} could not open an overlay: {detail}")

        deadline = clock() + timeout
        while not sentinel.exists():
            if clock() > deadline:
                raise TimeoutError(
                    f"editor did not finish within {timeout:.0f}s; "
                    f"your text is still at {target}"
                )
            sleep(poll)
        return int((sentinel.read_text(encoding="utf-8").strip() or "1"))
    finally:
        wrapper.unlink(missing_ok=True)
        sentinel.unlink(missing_ok=True)
