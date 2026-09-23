# The desktop app

One codebase for macOS and Windows: a Rust shell around the design system's own HTML.

A menu bar panel and a five-screen window, in English and Simplified Chinese,
on real Liquid Glass where the system has it. The window's toolbar carries the panel's two
actions, `Review now` and `Ingest now`, on every screen, and the foot of its sidebar says
when the store was last ingested; while a run goes, wherever it was started (the toolbar,
the panel, the timer or a terminal), both show it instead.

- **Overview**: one sentence saying what the screen is over, the three totals as a strip,
  tokens by what each reply did (change, run, read, talk) per day or week, one card each
  for what was still there after thirty days and what was rewritten, and where the hours
  went. Seven ranges from one day to all, and a bar is a day up to sixty days and an ISO
  week beyond; the two outcome cards stay
  weekly under every range, because the engine measures an outcome per week. Each card's
  full table is behind its "how this is measured" drawer and is built when the drawer is
  first opened. While an ingest runs, its first sentence says the figures will update.
- **Repositories**: which repositories the engine found on this machine and which of them
  it records, with the capture level per repository: recording is opt-in, which is the
  answer to "why are only three repositories recorded?". Each row carries its sessions and
  source, its first and last day, its tokens by bucket as one bar and what was still there
  after thirty days, both over all time, and clicking a recorded row filters every screen
  to it.
- **Review**: one stored review as the engine wrote it, keeping the period reviewed and
  the outcome window apart, with the engine's own figures and its notes behind a
  disclosure.
- **Observations**: one card per behaviour, paired bars on a single axis, each share over
  the number of sessions it is over, with the coverage and the commit mix beside it.
- **Settings**: four tabs. **General** is the app's own four settings (language,
  appearance, open at login, timed ingest), each a segmented control that writes through
  the shell. **Engine** is where `prudence` is, its version, the Install or Update button,
  the engine's last ten runs from its run log (each opening onto its warnings, failed
  checks and error), a Diagnose action that runs `prudence diagnose` and reveals the
  folder it wrote, and where the store is kept with what produced it. **Model** is
  what `prudence config model` prints, with the one field this app may set; it never calls
  a model. **About** is what is running, on what, under what licence, with links to the
  project, the developer and what is recorded.

A run says what it is doing: `ingest --progress` writes one JSON line per step on its
standard error, the shell reads them as they arrive and announces them, and the panel and
the window's toolbar draw the same determinate bar until the engine's own outcome replaces
it. The shell also keeps whether a run is going at all (`src-tauri/src/activity.rs`), and
sees one started in a terminal by the engine's own lock on `ingest.lock`, which it asks
about without taking.

It can also **find the `prudence` executable and run it**: ingest and review, from the
window or from the panel, with a picker when the executable cannot be found, uv to install
it when it is not there at all, an interval at which the shell ingests on its own, and the
store watched so a run's new numbers arrive on their own.

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

The shell reads **`PRUDENCE_DATA_DIR`** and nothing else, and everything it touches there
is resolved from it:

| Under the data directory | What | Who writes it |
| --- | --- | --- |
| `prudence.db` | the store, read-only from here | the engine |
| `ingest.lock` | held while an ingest or a rebuild runs; asked about, never taken | the engine |
| `logs/runs.jsonl` | one record per engine run: versions, steps, warnings, checks, error. The Engine tab lists the last ten and the status row reads the last ingest's | the engine |
| `logs/app.log` | this app's own log, rotated at 4 MB with two old files kept (`app.log.1`, `app.log.2`) | this app (`src-tauri/src/applog.rs`) |
| `diagnose/<timestamp>/` | what `prudence diagnose` writes; the Engine tab's Diagnose runs it and reveals the folder | the engine |

`PRUDENCE_CONFIG_DIR` is the engine's and the shell does not read
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
| `PRUDENCE_PRESS=Engine` | presses the button with that exact label once the page has drawn, on whichever surface is open. It is how a Settings tab, an Overview range or a run started from the panel gets into a picture. `Scripts/shot.py --press` sets it. Several labels separated by `>` are pressed in order, each one waiting for its own button: `PRUDENCE_PRESS="Engine > Choose"` reaches a control inside a tab, and `PRUDENCE_PRESS="Ingest now"` starts a run from the window's toolbar. A button inside a pane that is not open is skipped, because the Settings tabs are all built and only one is shown, so one label can exist on several panes of a screen showing one of them. The panel takes one label, because everything it draws exists at its first draw |

There is no store override beyond `PRUDENCE_DATA_DIR` and `PRUDENCE_CONFIG_DIR`. The spike
had a `PRUDENCE_DB`; it is gone, because the engine does not honour that name and a guessed
variable of exactly that shape is how an agent once wrote to the founder's real store.

The shell writes what it did on standard error: which material each surface got, where the
panel landed, how long the page took, and every tray event it received. What an agent needs
later goes to `logs/app.log` as well, one line per event (`time level target message
key=value`): the app starting, every engine invocation with its exit code and seconds but
never its output, every store announcement with its revision, every contract check, every
settings write (never a value that is a path), and every failure in the words the reader was
shown.

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
    store/             payload.js: the shell's answer, as rows; one reader per screen,
                       and readiness.js: when the engine is asked whether a review is ready
    ui/                one file per surface, plus wiring.js: THE ONLY FILE UNDER ui/
                       THAT CALLS THE BRIDGE
  src-tauri/
    tauri.conf.json    one window, transparent, frameless, hidden from the Dock
    capabilities/      what the page is allowed to ask the shell for
    icons/             the app icon set, and tray-template.png for the menu bar
    src/
      lib.rs           the shell: state, commands, the tray, the screenshot hooks
      panel.rs         show, hide, and where the panel goes
      window.rs        the main window, and the screenshot backdrop
      store.rs         read-only SQLite over the app_* views, and the contract check
      engine.rs        finding `prudence` and running it
      installer.rs     installing or updating it with uv, and the manual route
      model.rs         what `prudence config model` prints, read
      timer.rs         the timed ingest: one thread, outliving every window
      activity.rs      whether a run is going and how the last one ended, whoever started it
      runlog.rs        the engine's run log, read from its end; `prudence diagnose`
      applog.rs        this app's own log, `logs/app.log`, rotated by size
      ui_state.rs      what the window remembers between launches
      harness.rs       the automation, behind `--features harness`, absent from a release
      platform/        everything true of one operating system and not the other
  Scripts/             shot.py, stress.py
  test/                the token table, asserted against DESIGN.md
  DESIGN.md            the design system: rules, material, bridge, components
```

## Three rules this app is built on

**1. The app owns no numbers.** `store.rs` opens the store read-only, refuses a contract
version outside `contract::SUPPORTED` (4, and only 4), and selects from `app_*` views only. The page may sum
view columns into a bucket and take the ratio of two columns of the same row; a median, a
threshold or an attribution is a new view in `src/prudence/store/app_views.py`.

**2. The frontend talks to the shell through `bridge.js` and nothing else.** Every
command and event, and `test/bridge.test.mjs` asserts both that nothing else in `src/` touches a
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
