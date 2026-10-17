# This fork: Settings for the Atrium desktop

`th3Boer/hyprmod`, branch `atrium`, is HyprMod (GPL-3.0, by Ivo Šmerek,
https://github.com/BlueManCZ/hyprmod) as the settings app of the Atrium desktop:

- branded **Settings** (app id `io.github.th3boer.AtriumSettings`, own icon);
  HyprMod and its author stay credited in About
- a **Desktop** sidebar category (`hyprmod/atrium/`): Appearance (themes with
  preview/apply/revert, wallpaper -> palette, fonts, app design, shell shape and
  motion), Notifications (do not disturb, Allow/Silent/Block per app), Desktop
  Plugins, Updates. Shown only when the `atrium` CLI exists; every change goes
  through that CLI
- `hyprmod --atrium-page PAGE` opens a page (`atrium settings appearance`)
- the start page is opened after the window is presented (focus used to select
  Profiles)

Keep upstream mergeable: Atrium code lives in `hyprmod/atrium/`; the hooks into
upstream files are small (window.py page registration + open_page, sidebar
category + focus_row, main.py start page, branding strings).

    git fetch upstream && git merge upstream/main
