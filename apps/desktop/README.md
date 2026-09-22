# The desktop app

One codebase for macOS and Windows: a Rust shell around the design system's own HTML.

**0.1.0.** A menu bar panel and a four-screen window, in English and Simplified Chinese,
on real Liquid Glass where the system has it:

- **Overview**: the three totals, tokens by purpose per week, what became of each week's
  work with its coverage, and where the hours went. Every weekly chart shares one axis,
  the range's complete week list, so a week is in the same place in each.
- **Review**: one stored review as the engine wrote it, keeping the period reviewed and
  the outcome window apart, with the engine's own figures and its notes behind a
  disclosure.
- **Observations**: one card per behaviour, paired bars on a single axis, each share over
  the number of sessions it is over, with the coverage and the commit mix beside it.
- **Settings**: what is recorded and at what capture level, what is never recorded, where
  the store is and what produced it, the engine and its two actions, and an about block.
  Read-only, and it says so rather than showing controls that do nothing.

It can also **find the `prudence` executable and run it**: ingest and review, with a
picker when the executable cannot be found, and the store watched so a run's new numbers
arrive on their own.

No updater and no signing yet. What each batch proved and what it did not is in
`docs/reports/desktop/` (local files, not in git).

The Swift app that preceded this one was retired from master in commit `7fd8f60`; its last
state is `apps/mac/` at `133a074`, in the history, not built or changed.

## Build and run

```sh
# rustup is installed through Homebrew on the founder's machine and its shims are not on
# the default PATH. Nothing below works without this line.
export PATH="/opt/homebrew/opt/rustup/bin:$PATH"

cd apps/desktop
pnpm install                       # the Tauri CLI, nothing else
pnpm tauri dev                     # the app, for working on the page
pnpm tauri build --bundles app,dmg # Prudence.app and an unsigned DMG
pnpm test                          # the frontend's tests, in node
pnpm check                         # tsc --checkJs over JSDoc types; no build, nothing emitted
cd src-tauri && cargo test         # the store layer, the panel's placement, the memory
```

`pnpm tauri build --features harness` is the build the two scripts under `Scripts/` need.
A plain release build has **no** automation in it: no stress runner, no backdrop window,
and no way for an environment variable to make the app evaluate JavaScript against its
own page.

### The checklist for every batch

All of it, before the report is written. The last two are easy to forget because the
scripts are the only Python in this folder, and **Python anywhere in this repository
answers to the root `pyproject.toml`'s ruff settings**, not to anything under
`apps/desktop/`. They are run from the repository root.

```sh
cd apps/desktop
pnpm test
pnpm check
cd src-tauri
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo clippy --all-targets --features harness -- -D warnings
cargo test
cd ../../..                                 # the repository root
uv run ruff check apps/desktop/Scripts
uv run ruff format --check apps/desktop/Scripts
```

Everything in that list is also in `.github/workflows/desktop-ci.yml`, so forgetting one
is caught rather than discovered later.

Plus, in every batch that adds a screen: `python3 Scripts/stress.py --rounds 400 ...`,
with its one-line result in the report.

Run it against a **copy** of the store, never the real one. The shell honours the same
variables `src/prudence/paths.py` honours, so `prudence status` tells you where it will
look before you start it:

```sh
mkdir -p /tmp/prudence-copy
sqlite3 "$HOME/Library/Application Support/prudence/prudence.db" \
  ".backup '/tmp/prudence-copy/prudence.db'"
PRUDENCE_DATA_DIR=/tmp/prudence-copy prudence status
PRUDENCE_DATA_DIR=/tmp/prudence-copy \
  src-tauri/target/release/bundle/macos/Prudence.app/Contents/MacOS/Prudence
```

The shell reads **`PRUDENCE_DATA_DIR`** and nothing else: the store's location is the
only path it resolves. `PRUDENCE_CONFIG_DIR` is the engine's and the shell does not read
it, so setting it isolates the CLI and not this app; what isolates this app's own state
is `PRUDENCE_UI_MEMORY=off`, and the two scripts set it.

### Hooks for looking at it

An agent cannot click a menu-bar icon, so the same kind of hooks the Swift app grew exist
here. None of them is reachable by anything a user does.

| Variable | Does |
| --- | --- |
| `PRUDENCE_PANEL_OPEN=1` | opens the panel 1.2 s after launch and leaves it open. The delay is not politeness: AppKit has not laid the status item out before then, and a panel shown earlier cannot be anchored under it |
| `PRUDENCE_WINDOW_OPEN=1` | opens the main window at launch |
| `PRUDENCE_STRESS=screens:400` | switches screens, scrolls and toggles the panel 400 times, then runs a paint probe. `panel:30` does the panel alone |
| `PRUDENCE_STRESS_IDLE=600` | after the stress run, do nothing for 600 s and probe again |
| `PRUDENCE_BACKDROP=1` | a plain full-screen window of the app's own, behind everything, so a frosted surface is photographed over something reproducible |
| `PRUDENCE_UI_MEMORY=off` | start with nothing remembered and write nothing, so a shot is of the state the caller asked for |
| `PRUDENCE_FORCE_APPEARANCE=dark` | pins the windows to dark (or `light`) |
| `PRUDENCE_FORCE_LANGUAGE=zh-Hans` | draws the pages in Chinese (or `en`) |
| `PRUDENCE_GLASS_OPAQUE=0` | glass with nothing behind it. The panel defaults to a filled backing and the window to clear; this overrides both |

There is no store override beyond `PRUDENCE_DATA_DIR` and `PRUDENCE_CONFIG_DIR`. The spike
had a `PRUDENCE_DB`; it is gone, because the engine does not honour that name and a guessed
variable of exactly that shape is how an agent once wrote to the founder's real store.

The shell writes what it did on standard error: which material each surface got, where the
panel landed, how long the page took, and every tray event it received.

### Pictures

```sh
python3 Scripts/shot.py --name window-light --window main --appearance light \
    --store /tmp/prudence-copy --out shots
python3 Scripts/stress.py --rounds 400 --store /tmp/prudence-copy --out shots
```

Both scripts **keep the PID they launched and kill that PID**, and both **refuse to
capture unless the app's own window is the frontmost thing over that rectangle**. Neither
rule is caution for its own sake: on 2026-09-21 a `pkill` by path quit the founder's own
Prudence, and the first run of `shot.py` photographed their browser.

`stress.py` ends by reading a colour out of a screenshot rather than asking the page how
it is, because wry issue 1848's failure mode is a page that is fine and a screen that is
stale. It converts the capture through its embedded display profile first: `screencapture`
writes the display's own colour space, so on a P3 display a CSS `rgb(214,45,130)` lands in
the file as `(197,62,128)`, and comparing the raw numbers reports a healthy compositor as
broken.

## Layout

```
apps/desktop/
  src/                 the frontend. No build step: the browser loads these files as they are
    index.html         the panel
    window.html        the main window
    backdrop.html      a plain full-screen window, for screenshots only
    bridge.js          THE ONLY FILE THAT KNOWS ABOUT TAURI
    boot.js            start-up, for both pages
    app.css            the panel's own layout, and what both pages share
    window.css         the window's own layout
    design/            tokens.css, dom.js, brand.js, purposes.js, charts.js
    text/              strings.{en,zh-Hans}.json, strings.js, fmt.js, sentences.js
    store/             payload.js: the shell's answer, as rows
    ui/                panel.js, window.js: one file per surface
  src-tauri/
    tauri.conf.json    one window, transparent, frameless, hidden from the Dock
    capabilities/      what the page is allowed to ask the shell for
    icons/             the app icon set, and tray-template.png for the menu bar
    src/
      lib.rs           the shell: state, commands, the tray, the screenshot hooks
      panel.rs         show, hide, and where the panel goes
      window.rs        the main window, and the screenshot backdrop
      store.rs         read-only SQLite over the app_* views, and the contract check
      ui_state.rs      what the window remembers between launches
      harness.rs       the automation, behind `--features harness`, absent from a release
      platform/        everything true of one operating system and not the other
  Scripts/             shot.py, stress.py
  test/                the token table, asserted against DESIGN.md
  DESIGN.md            the design system: rules, material, bridge, components
```

## Three rules this app is built on

**1. The app owns no numbers.** `store.rs` opens the store read-only, refuses a contract
version outside `SUPPORTED_CONTRACT`, and selects from `app_*` views only. The page may sum
view columns into a bucket and take the ratio of two columns of the same row; a median, a
threshold or an attribution is a new view in `src/prudence/store/app_views.py`.

**2. The frontend talks to the shell through `bridge.js` and nothing else.** Nine
commands, and `test/bridge.test.mjs` asserts both that nothing else in `src/` touches a
Tauri API and that every command's **argument names** match `lib.rs`. If the webview under
this frontend ever has to change, the shell and that one file are rewritten and everything
else moves unchanged. That is the way out if Tauri fails on a later macOS, and it only
stays open while the rule holds.

**3. Platform differences live in `src-tauri/src/platform/`.** The page never asks which
system it is on. A difference that cannot be held in that folder is a difference that will
end up in the page, which is what closes the door on Windows.

## Where the design lives

[DESIGN.md](DESIGN.md), written along the way rather than at the end. It carries the four
rules, the material decision per surface, the bridge rule, the no-build-step reason, the
component list and the two process rules for working on the founder's machine.
The Swift app's `DESIGN.md` (`apps/mac/DESIGN.md` at `133a074`) is the earlier, fuller description of the
tokens and the seven chart shapes, where this file is still shorter.
