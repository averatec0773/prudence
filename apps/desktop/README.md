# The desktop app

One codebase for macOS and Windows: a Rust shell around the design system's own HTML.

**This is the spike, not the product.** It puts an icon in the menu bar, drops the
approved dropdown under it with real frost, and fills every number from a store it opens
read-only. Nothing else: no charts, no CLI call, no main window, no updater, no signing,
no language setting. What was proved and what was not is in
`docs/reports/desktop/00-spike.md` (a local file, not in git).

The Swift app in `apps/mac/` is frozen at `v0.4.0` as the comparison and the way back.
Do not change it.

## Build and run

```sh
cd apps/desktop
pnpm install                       # the Tauri CLI, nothing else
pnpm tauri dev                     # the panel in a window, for working on the page
pnpm tauri build --bundles app,dmg # Prudence.app and an unsigned DMG
pnpm test                          # the token table, in node
cd src-tauri && cargo test         # the store layer and the panel's placement
```

`cargo` lives at `/opt/homebrew/opt/rustup/bin` on the founder's machine and is not on the
default `PATH`; `export PATH="/opt/homebrew/opt/rustup/bin:$PATH"` before any of the above.

Run it against a **copy** of the store, never the real one. The shell honours the same
variables `src/prudence/paths.py` honours, so `prudence status` tells you where it will
look before you start it:

```sh
mkdir -p /tmp/prudence-copy
sqlite3 "$HOME/Library/Application Support/prudence/prudence.db" \
  ".backup '/tmp/prudence-copy/prudence.db'"
PRUDENCE_DATA_DIR=/tmp/prudence-copy PRUDENCE_CONFIG_DIR=/tmp/prudence-copy prudence status
PRUDENCE_DATA_DIR=/tmp/prudence-copy PRUDENCE_CONFIG_DIR=/tmp/prudence-copy \
  src-tauri/target/release/bundle/macos/Prudence.app/Contents/MacOS/prudence-desktop
```

### Hooks for looking at it

An agent cannot click a menu-bar icon, so the same kind of hooks the Swift app grew exist
here. None of them is reachable by anything a user does.

| Variable | Does |
| --- | --- |
| `PRUDENCE_PANEL_OPEN=1` | opens the panel 1.2 s after launch and leaves it open. The delay is not politeness: AppKit has not laid the status item out before then, and a panel shown earlier cannot be anchored under it |
| `PRUDENCE_PANEL_STRESS=n` | opens and closes the panel n times first, for wry issue 1848 |
| `PRUDENCE_FORCE_APPEARANCE=dark` | pins the window to dark (or `light`) |
| `PRUDENCE_FORCE_LANGUAGE=zh-Hans` | draws the page in Chinese (or `en`) |
| `PRUDENCE_GLASS_OPAQUE=0` | glass with nothing behind it, which takes the tone of whatever is on the screen. Default is on: a filled backing, which is how an `NSPopover` reads |
| `PRUDENCE_DB` | one database file, ahead of `PRUDENCE_DATA_DIR` |

The shell writes what it did on standard error: which material it got, where the panel
landed, how long the page took, and every tray event it received.

## Layout

```
apps/desktop/
  src/                 the frontend. No build step: the browser loads these files as they are
    index.html
    bridge.js          THE ONLY FILE THAT KNOWS ABOUT TAURI
    boot.js            ask the shell for the store, then draw
    panel.js           the dropdown, variant C with a caption on every block
    app.css            what differs between a mockup of the popover and the popover
    design/            copied unchanged from docs/design/mockups/:
                       tokens.css, i18n.js, brand.js, derive.js, charts.js
  src-tauri/
    tauri.conf.json    one window, transparent, frameless, hidden from the Dock
    capabilities/      what the page is allowed to ask the shell for
    icons/             the app icon set, and tray-template.png for the menu bar
    src/
      lib.rs           the shell: state, commands, the tray, the screenshot hooks
      panel.rs         show, hide, and where the panel goes
      store.rs         read-only SQLite over the app_* views, and the contract check
      platform/        everything true of one operating system and not the other
  test/                the token table, asserted against DESIGN.md
```

## Three rules this app is built on

**1. The app owns no numbers.** `store.rs` opens the store read-only, refuses a contract
version outside `SUPPORTED_CONTRACT`, and selects from `app_*` views only. The page may sum
view columns into a bucket and take the ratio of two columns of the same row; a median, a
threshold or an attribution is a new view in `src/prudence/store/app_views.py`.

**2. The frontend talks to the shell through `bridge.js` and nothing else.** Four verbs:
read the store, ask the shell about itself, report how tall the content is, close or quit.
If the webview under this frontend ever has to change, the shell and this one file are
rewritten and everything else moves unchanged. That is the way out if Tauri fails on a
later macOS, and it only stays open while the rule holds.

**3. Platform differences live in `src-tauri/src/platform/`.** The page never asks which
system it is on. A difference that cannot be held in that folder is a difference that will
end up in the page, which is what closes the door on Windows.

## Where the design lives

`src/design/tokens.css` is the design system, copied from `docs/design/mockups/` byte for
byte, and `apps/mac/DESIGN.md` still describes it. `src/app.css` says where things go and
never declares a token; `test/tokens.test.mjs` asserts both, and asserts the palette
against the table `DESIGN.md` prints.

Two places where the mockups are a round behind the shipping app, and this app follows the
app: the popover's blocks carry their caption **above** them rather than in a left column
(the founder's batch 3 change), and the plain button is quiet ink with the accent only
under the pointer. Both are commented where they are done.
