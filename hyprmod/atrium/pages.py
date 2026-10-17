"""The Atrium pages: Appearance, Notifications, Atrium plugins, Updates.

Each page reads its state from ``atrium … --json`` when it is shown and
changes things only through the CLI (see ``hyprmod.atrium``).
"""

from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango

from hyprmod import atrium
from hyprmod.ui import clear_children, make_page_layout

PALETTE_STYLES = [("auto", "Balanced"), ("vibrant", "Vibrant"), ("pastel", "Pastel"),
                  ("muted", "Muted"), ("faithful", "Faithful"), ("mono", "Mono")]


class _Page:
    """Shared plumbing: a page that (re)loads when it becomes visible."""

    def __init__(self, window):
        self._window = window
        self._content: Gtk.Box | None = None

    def build(self, header: Adw.HeaderBar) -> Adw.ToolbarView:
        toolbar, _page_box, content, _scrolled = make_page_layout(header=header)
        self._content = content
        toolbar.connect("map", lambda *_: self.reload())
        return toolbar

    def reload(self):
        raise NotImplementedError

    def toast(self, text: str):
        self._window.show_toast(text, timeout=3)

    def call(self, args, message: str | None = None, then=None):
        """Run a changing command; toast the result, reload afterwards."""

        def done(ok, _out, err):
            if ok:
                if message:
                    self.toast(message)
            else:
                self.toast(atrium.error_text(err))
            (then or self.reload)()

        atrium.run(args, done)


# ── Appearance ──────────────────────────────────────────────────────────────


class AppearancePage(_Page):
    """Themes (preview, apply, revert), wallpaper + palette, fonts, app design,
    the shell's shape and motion."""

    def __init__(self, window):
        super().__init__(window)
        self._css = Gtk.CssProvider()
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(display, self._css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self._previewing: str | None = None
        self._loading = False

    def reload(self):
        atrium.run(["theme", "list", "--json"], lambda ok, themes, _e: ok and self._got_themes(themes), parse_json=True)

    def _got_themes(self, themes):
        atrium.run(["theme", "current"], lambda ok, cur, _e: ok and self._render(themes, cur), parse_json=True)

    def _render(self, themes: list[dict], cur: dict):
        self._loading = True
        content = self._content
        clear_children(content)

        # one CSS class per theme: its own background, text and accent
        css = []
        for t in themes:
            fg = "#1d1c22" if t["mode"] == "light" else "#ecebf0"
            css.append(f".atrium-theme-{t['slug']} {{ background: {t['background']}; color: {fg}; "
                       f"border-bottom: 5px solid {t['accent']}; border-radius: 12px; padding: 14px 16px; }}")
        self._css.load_from_string("\n".join(css))

        group = Adw.PreferencesGroup(
            title="Theme",
            description="Pick one to preview it on the whole desktop. Apply keeps it, Revert goes back.",
        )
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                           max_children_per_line=4, min_children_per_line=2,
                           column_spacing=10, row_spacing=10)
        for t in themes:
            btn = Gtk.Button()
            btn.add_css_class("flat")
            btn.add_css_class(f"atrium-theme-{t['slug']}")
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            name = Gtk.Label(label=t["name"], xalign=0, ellipsize=Pango.EllipsizeMode.END)
            name.add_css_class("heading")
            box.append(name)
            note = "current" if t["current"] else ("previewing" if t["slug"] == self._previewing else t["mode"])
            sub = Gtk.Label(label=note, xalign=0)
            sub.add_css_class("caption")
            box.append(sub)
            btn.set_child(box)
            btn.set_tooltip_text(t["slug"])
            btn.connect("clicked", lambda _b, slug=t["slug"]: self._preview(slug))
            flow.append(btn)
        group.add(flow)
        content.append(group)

        actions = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        apply_btn = Gtk.Button(label="Apply", sensitive=self._previewing is not None)
        apply_btn.add_css_class("suggested-action")
        apply_btn.connect("clicked", lambda *_: self._apply())
        revert_btn = Gtk.Button(label="Revert")
        revert_btn.connect("clicked", lambda *_: self._revert())
        actions.append(revert_btn)
        actions.append(apply_btn)
        content.append(actions)

        # wallpaper -> palette
        wall = Adw.PreferencesGroup(title="Wallpaper",
                                    description="A picture of your own, optionally with a colour theme made from it.")
        self._style_row = Adw.ComboRow(title="Colours from the picture",
                                       model=Gtk.StringList.new(["Keep the theme's colours"] + [n for _, n in PALETTE_STYLES]))
        wall.add(self._style_row)
        pick = Adw.ButtonRow(title="Choose a picture…")
        pick.connect("activated", lambda *_: self._pick_wallpaper())
        wall.add(pick)
        content.append(wall)

        # fonts
        fonts = Adw.PreferencesGroup(title="Fonts",
                                     description="One choice for the whole desktop: shell, GTK and Qt apps, title bars.")
        font = cur.get("font", {})
        for role, title in (("ui", "Interface"), ("mono", "Monospace")):
            row = Adw.ActionRow(title=title)
            dialog = Gtk.FontDialog(title=f"{title} font")
            button = Gtk.FontDialogButton(dialog=dialog, level=Gtk.FontLevel.FAMILY, valign=Gtk.Align.CENTER)
            button.set_font_desc(Pango.FontDescription.from_string(font.get(role, "Sans")))
            button.connect("notify::font-desc", lambda b, _p, r=role: self._font(r, b.get_font_desc()))
            row.add_suffix(button)
            row.set_activatable_widget(button)
            fonts.add(row)
        size = Adw.SpinRow(title="Size", adjustment=Gtk.Adjustment(lower=7, upper=24, step_increment=1, value=font.get("size", 11)))
        size.connect("notify::value", lambda r, _p: self._loading or self._knob(["theme", "font", "--size", str(int(r.get_value()))]))
        fonts.add(size)
        content.append(fonts)

        # app design + shell knobs
        look = Adw.PreferencesGroup(title="Look")
        design = Adw.SwitchRow(title="Theme colours in apps",
                               subtitle="Off: GTK and libadwaita apps keep their default look",
                               active=cur.get("gtk_style", "atrium") == "atrium")
        design.connect("notify::active", lambda r, _p: self._loading or self._knob(
            ["theme", "knob", f"gtk_style={'atrium' if r.get_active() else 'default'}"]))
        look.add(design)
        radius = Adw.SpinRow(title="Corner radius of the shell",
                             subtitle="Window corners and gaps are under Look & Feel",
                             adjustment=Gtk.Adjustment(lower=0, upper=32, step_increment=1, value=cur.get("radius", 14)))
        radius.connect("notify::value", lambda r, _p: self._loading or self._knob(["theme", "knob", f"radius={int(r.get_value())}"]))
        look.add(radius)
        motion = Adw.SpinRow(title="Animation speed", subtitle="1 = normal, 0 = no animations",
                             digits=2, adjustment=Gtk.Adjustment(lower=0, upper=2, step_increment=0.05,
                                                                 value=cur.get("motion_scale", 1.0)))
        motion.connect("notify::value", lambda r, _p: self._loading or self._knob(
            ["theme", "knob", f"motion_scale={r.get_value():.2f}"]))
        look.add(motion)
        content.append(look)
        GLib.idle_add(self._done_loading)

    def _done_loading(self):
        self._loading = False
        return GLib.SOURCE_REMOVE

    def _preview(self, slug: str):
        self._previewing = slug
        self.call(["theme", "preview", slug], f"Previewing {slug}")

    def _apply(self):
        slug, self._previewing = self._previewing, None
        if slug:
            self.call(["theme", "set", slug], f"{slug} applied")

    def _revert(self):
        self._previewing = None
        self.call(["theme", "revert"], "Reverted")

    def _font(self, role: str, desc):
        if self._loading or desc is None:
            return
        self._knob(["theme", "font", f"--{role}", desc.get_family()])

    def _knob(self, args):
        # no reload: the controls already show the new value
        self.call(args, None, then=lambda: None)

    def _pick_wallpaper(self):
        dialog = Gtk.FileDialog(title="Choose a wallpaper")
        filt = Gtk.FileFilter(name="Pictures")
        filt.add_mime_type("image/*")
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(filt)
        dialog.set_filters(store)

        def chosen(d, result):
            try:
                f = d.open_finish(result)
            except GLib.Error:
                return
            args = ["theme", "wallpaper", f.get_path()]
            idx = self._style_row.get_selected()
            if idx > 0:
                args += ["--palette", PALETTE_STYLES[idx - 1][0]]
            self.call(args, "Wallpaper set")

        dialog.open(self._window, None, chosen)


# ── Notifications ─────────────────────────────────────────────────────────────


class NotificationsPage(_Page):
    """Do not disturb and, per app: Allow / Silent / Block."""

    RULES = [("allow", "Allow"), ("silent", "Silent"), ("block", "Block")]

    def reload(self):
        atrium.run(["notifications", "list", "--json"], lambda ok, d, _e: ok and self._render(d), parse_json=True)

    def _render(self, data: dict):
        content = self._content
        clear_children(content)
        top = Adw.PreferencesGroup()
        dnd = Adw.SwitchRow(title="Do not disturb", subtitle="No popups; critical notifications still come through",
                            active=data.get("dnd", False))
        dnd.connect("notify::active", lambda r, _p: self.call(
            ["notifications", "dnd", "on" if r.get_active() else "off"], None, then=lambda: None))
        top.add(dnd)
        content.append(top)

        apps = Adw.PreferencesGroup(
            title="Apps",
            description="Allow: popup and notification centre · Silent: centre only · Block: never shown",
        )
        if not data.get("apps"):
            apps.add(Adw.ActionRow(title="No app has sent a notification yet"))
        for app in data.get("apps", []):
            row = Adw.ComboRow(title=app["name"], subtitle=f"{app['count']} notifications",
                               model=Gtk.StringList.new([label for _, label in self.RULES]))
            keys = [k for k, _ in self.RULES]
            row.set_selected(keys.index(app["rule"]) if app["rule"] in keys else 0)
            row.connect("notify::selected", lambda r, _p, key=app["key"]: self.call(
                ["notifications", "rule", key, keys[r.get_selected()]], None, then=lambda: None))
            apps.add(row)
        content.append(apps)


# ── Atrium plugins ─────────────────────────────────────────────────────────────


class PluginsPage(_Page):
    """Atrium's own plugins: on = in place, off = gone without a trace."""

    def reload(self):
        atrium.run(["plugin", "list", "--json"], lambda ok, d, _e: ok and self._render(d or []), parse_json=True)

    def _render(self, plugins: list[dict]):
        content = self._content
        clear_children(content)
        group = Adw.PreferencesGroup(title="Desktop plugins",
                                     description="Features of the Atrium desktop. Switched off, a plugin leaves nothing behind.")
        if not plugins:
            group.add(Adw.ActionRow(title="No plugins installed"))
        for p in plugins:
            row = Adw.SwitchRow(title=p["name"], subtitle=p["id"], active=p["enabled"])
            row.connect("notify::active", lambda r, _p, pid=p["id"]: self.call(
                ["plugin", "enable" if r.get_active() else "disable", pid],
                f"{pid} {'on' if r.get_active() else 'off'}"))
            group.add(row)
        content.append(group)


# ── Updates ──────────────────────────────────────────────────────────────────


class UpdatesPage(_Page):
    """Pending updates, reboot status, and the update itself (in a terminal:
    it asks for the sudo password)."""

    def reload(self):
        clear_children(self._content)
        spinner = Adw.Spinner()
        self._content.append(spinner)
        atrium.run(["update", "--reboot-check"], lambda _ok, r, _e: self._got_reboot(r), parse_json=True)

    def _got_reboot(self, reboot):
        atrium.run(["update", "--check"], lambda ok, p, _e: self._render(p if ok else None, reboot), parse_json=True)

    def _render(self, pending: dict | None, reboot: dict | None):
        content = self._content
        clear_children(content)
        if reboot and reboot.get("reboot"):
            banner = Adw.Banner(title="Restart needed: " + "; ".join(reboot["reboot"]), revealed=True)
            content.append(banner)

        repo = (pending or {}).get("repo", [])
        aur = (pending or {}).get("aur", [])
        status = Adw.PreferencesGroup(title="System updates")
        if pending is None:
            status.add(Adw.ActionRow(title="Could not check for updates"))
        elif not repo and not aur:
            status.add(Adw.ActionRow(title="Everything is up to date", icon_name="object-select-symbolic"))
        else:
            status.add(Adw.ActionRow(title=f"{len(repo)} package updates, {len(aur)} from the AUR"))
        run = Adw.ButtonRow(title="Update now", start_icon_name="software-update-available-symbolic")
        run.add_css_class("suggested-action")
        run.connect("activated", lambda *_: self._update())
        status.add(run)
        again = Adw.ButtonRow(title="Check again")
        again.connect("activated", lambda *_: self.reload())
        status.add(again)
        content.append(status)

        if repo or aur:
            group = Adw.PreferencesGroup(title="Packages")
            for pkg in repo + aur:
                row = Adw.ActionRow(title=pkg["name"], subtitle=f"{pkg['from']} → {pkg['to']}")
                if pkg in aur:
                    row.add_suffix(Gtk.Label(label="AUR", css_classes=["caption", "dim-label"]))
                group.add(row)
            content.append(group)

    def _update(self):
        path = atrium.cli()
        try:
            Gio.Subprocess.new(["kitty", "--title", "System update", "--hold", path, "update"],
                               Gio.SubprocessFlags.NONE)
        except GLib.Error as e:
            self.toast(f"Could not open a terminal: {e.message}")
