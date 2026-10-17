"""Atrium integration: extra pages when HyprMod runs on an Atrium desktop.

Atrium (https://github.com/th3Boer/atrium, private) is a desktop shell on
Hyprland. Everything Atrium owns (themes, fonts, notification rules, its
plugins, system updates) is changed through its one CLI, ``atrium``; these
pages are a GUI for that CLI and never touch Atrium's files directly. Without
the CLI, HyprMod looks and behaves exactly like upstream.
"""

import json
import os
import shutil
from collections.abc import Callable
from pathlib import Path

from gi.repository import Gio, GLib

PAGES = ("atrium_appearance", "atrium_notifications", "atrium_plugins", "atrium_updates")


def cli() -> str | None:
    """Path of the ``atrium`` command, or None when this is no Atrium desktop."""
    env = os.environ.get("ATRIUM_CLI")
    if env and Path(env).is_file():
        return env
    found = shutil.which("atrium")
    if found:
        return found
    for candidate in (Path.home() / "atrium/host/bin/atrium", Path.home() / "Work/atrium/host/bin/atrium"):
        if candidate.is_file():
            return str(candidate)
    return None


def available() -> bool:
    return cli() is not None


def run(
    args: list[str],
    done: Callable[[bool, str, str], None] | None = None,
    *,
    parse_json: bool = False,
) -> None:
    """Run ``atrium ARGS`` without blocking the UI; ``done(ok, stdout, stderr)``
    is called on the main loop (stdout parsed to an object when parse_json)."""
    path = cli()
    if path is None:
        if done:
            done(False, "", "atrium is not installed")
        return
    proc = Gio.Subprocess.new(
        [path, *args],
        Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE,
    )

    def finished(p, result):
        try:
            _ok, out, err = p.communicate_utf8_finish(result)
        except GLib.Error as e:
            if done:
                done(False, "", str(e))
            return
        ok = p.get_successful()
        if done:
            if parse_json:
                try:
                    out = json.loads(out or "null")
                except ValueError:
                    ok, out = False, None
            done(ok, out, (err or "").strip())

    proc.communicate_utf8_async(None, None, finished)


def error_text(err: str) -> str:
    """The CLI's error line without its 'atrium: ' prefix."""
    return err.strip().splitlines()[-1].removeprefix("atrium: ") if err.strip() else "failed"
