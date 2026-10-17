"""Prefilled GitHub issue URLs for the "Report a bug" affordances.

Used by the Help menu (open with an empty body) and :meth:`HyprModWindow.
show_bug_toast` (open with the triggering error embedded). Kept in core
so the URL builder stays GTK-free and unit-testable.
"""

import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from urllib.parse import urlencode

from hyprland_schema import HYPRLAND_VERSION

from hyprmod.core import config

REPO_URL = "https://github.com/th3Boer/hyprmod"
UPSTREAM_URL = "https://github.com/BlueManCZ/hyprmod"
ISSUE_URL = f"{REPO_URL}/issues"

# A whole error message pasted into the issue title balloons it; cap the
# title and let the full text live in the body instead.
_TITLE_MAX_LEN = 120


def hyprmod_version() -> str:
    """Installed hyprmod version, or ``'unknown'`` outside an installed env."""
    try:
        return version("hyprmod")
    except PackageNotFoundError:
        return "unknown"


def running_package_dir() -> Path:
    """Directory of the hyprmod package imported in *this* process.

    Resolved from this module's own location, so it points at the copy
    actually running even when several hyprmods are installed side by side.
    """
    return Path(__file__).resolve().parents[1]


def _classify_install(pkg_dir: str, *, in_venv: bool) -> str:
    """Map a package directory to an install-method label.

    Pure so it can be unit-tested against synthetic paths. ``uv``/``pipx``
    win first via their fixed layouts; an editable/source checkout lands
    outside ``site-packages``; a base-interpreter ``site-packages`` (no
    venv) is a distro package; anything else is left unlabeled.
    """
    if "/pipx/" in pkg_dir:
        return "pipx"
    if "/uv/tools/" in pkg_dir:
        return "uv tool"
    if "/site-packages/" not in pkg_dir:
        return "source checkout"
    if not in_venv:
        return "system package"
    return "unknown"


def detect_install_source() -> str:
    """Best-effort label for how the running hyprmod was installed.

    A guess: the raw path from :func:`running_package_dir` is reported
    alongside it so a wrong label is still debuggable.
    """
    return _classify_install(str(running_package_dir()), in_venv=sys.prefix != sys.base_prefix)


def _scrub_user(path_str: str, user: str) -> str:
    """Replace *user* with ``<user>`` where it appears as a whole path segment.

    Segment-wise (not substring) so a username like `` ivo`` doesn't mangle
    an unrelated ``ivory`` directory.
    """
    if not user or user not in path_str:
        return path_str
    return "/".join("<user>" if seg == user else seg for seg in path_str.split("/"))


def _install_path() -> str:
    """Install path for the report, with the username kept out of it.

    :func:`config.display_path` collapses the ``$HOME`` prefix to ``~`` for
    the common case. The segment scrub is the fallback for installs outside
    ``$HOME`` (custom prefix, or a symlinked home whose resolved path no
    longer matches ``Path.home()``) whose path still embeds the username,
    so an unrecognized install never leaks it.
    """
    return _scrub_user(config.display_path(running_package_dir()), Path.home().name)


def build_bug_report_url(
    *,
    title: str = "",
    body_extra: str = "",
    running_hyprland_version: str | None = None,
) -> str:
    """GitHub `new issue` URL with environment info prefilled.

    *body_extra* renders above the environment block so a triggering
    error sits at the top of the issue. *running_hyprland_version* is
    the live compositor's version (``None`` when offline).
    """
    schema_version = HYPRLAND_VERSION.removeprefix("v")
    running = running_hyprland_version.removeprefix("v") if running_hyprland_version else None
    mode = "Lua" if config.is_lua_mode() else "Hyprlang"

    body_lines: list[str] = []
    if body_extra:
        body_lines += [body_extra, "", "---", ""]
    body_lines += [
        "**Environment**",
        "",
        f"- HyprMod: {hyprmod_version()} ({detect_install_source()})",
        f"- Install path: `{_install_path()}`",
        f"- Hyprland (running): {running or 'not detected'}",
        f"- Hyprland schema (bundled): {schema_version}",
        f"- Config language: {mode}",
        f"- Config path: `{config.display_path(config.managed_path())}`",
        "",
        "**Steps to reproduce**",
        "",
        "1. ",
    ]
    body = "\n".join(body_lines)

    issue_title = title.split("\n", 1)[0]
    if issue_title:
        issue_title = f"[Bug] {issue_title}"
    if len(issue_title) > _TITLE_MAX_LEN:
        issue_title = issue_title[: _TITLE_MAX_LEN - 1].rstrip() + "…"

    params = urlencode({"title": issue_title, "body": body})
    return f"{ISSUE_URL}/new?{params}"
