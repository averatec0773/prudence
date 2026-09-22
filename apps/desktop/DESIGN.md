# The desktop app's design system

What every surface of the Tauri app is built from, and the rules that keep it one app.

This file is written **along the way**, not at the end: a design document written at the
end describes what happened, one written while the work is done constrains it. It starts
in batch 1 with the rules and the decisions already made, and every batch that adds a
component, a chart or a screen adds its row. Where this document and a screen disagree,
the screen is wrong.

The Swift app's `DESIGN.md` (branch `mac`, `apps/mac/DESIGN.md` there) is the same document
for the app this one replaced and is still the fuller description of the tokens and the
seven chart shapes. Everything in it that is about SwiftUI is not about this app;
everything in it that is about the product is, and belongs here.

## The four rules

Unchanged from the Swift app. They are the product's rules, not a framework's.

1. **Liquid Glass is the control and navigation layer, never the content layer.** The
   panel, the sidebar, the toolbar strip and the buttons are frosted. Cards, tables,
   charts and chips are opaque. A figure read against a moving backdrop is a figure the
   reader cannot check, and principle 3 is about figures the reader can check.
2. **Colour never means good or bad.** No green-for-up, no red-for-down, anywhere. More
   sessions is not better and less rework is not a score, so a delta chip's ink is a
   constant and a test asserts it.
3. **A composed sentence is composed in each language, never translated.** An observation
   is seven columns in a shape, built from those columns in the language in force. The
   engine's English sentence stays on the row as the thing to check against.
4. **Every figure is tabular.** `font-variant-numeric: tabular-nums`, so a value that
   changes does not reflow the row it sits in.

## The tokens

`src/design/tokens.css`. It began as a copy of the mockups' stylesheet and **is no longer
one**: the mockup's own page chrome (the variant switcher, the compare strip), its fake
desktop, fake menu bar, fake status item and fake traffic lights are gone, about 190
lines that existed to drive a clickable prototype. `docs/design/mockups/` is the frozen
record; this file is the product's. The tables below are the values, and
`test/tokens.test.mjs` asserts the stylesheet against them, so a token table nobody checks
cannot drift from what is drawn.

### Purpose palette

One colour per purpose, identical in every chart on every screen, in this fixed stacking and
legend order. Keys are the engine's own labels (`design/purposes.js` reads them out of
`facts/purpose.py`); `unknown` is shown as "other", and a label this build has never heard
of folds into it rather than being dropped. The order is never sorted by size: a chart whose
colours move is a chart two screenshots a week apart cannot be compared across.

| Purpose | Light | Dark |
|---|---|---|
| `--p-development` | `#007AFF` | `#0A84FF` |
| `--p-research` | `#30B0C7` | `#40C8E0` |
| `--p-debugging` | `#FF9500` | `#FF9F0A` |
| `--p-conversation` | `#AF52DE` | `#BF5AF2` |
| `--p-mixed` | `#5856D6` | `#7D7AFF` |
| `--p-unknown` (other) | `#8E8E93` | `#98989D` |

### Outcome colours

`--o-alive` `#0A7D45` / `#3AC07A`, `--o-rework` `#8A5A00` / `#E0A33A`. Survival and rework
are two readings of the same lines, so they share a warm-cool pair everywhere and differ by
line style in a time chart. They are not meant as "good" and "bad", and the delivery-05
report flags that the pair still reads that way; the prototype settled it and it stays until
the founder says otherwise.

### Surfaces and ink

| Token | Light | Dark |
|---|---|---|
| `--canvas` | `#F2F2F4` | `#1C1C1E` |
| `--surface` | `#FFFFFF` | `#2C2C2E` |
| `--surface-2` | `#F7F7F9` | `#242426` |
| `--surface-sunken` (chart tracks, chips) | `#EBEBEF` | `#171719` |
| `--sidebar` | `#F6F6F8` | `#232325` |
| `--text` / `--text-2` / `--text-3` | `#1C1C1E` / `#636366` / `#8E8E93` | `#F2F2F7` / `#AEAEB2` / `#8E8E93` |
| `--accent` | `#007AFF` | `#0A84FF` |

Elevation is a hairline ring, not a shadow. Only the panel and the window frame cast a real
one, at the system's own weight.

**`src/app.css` and `src/window.css` say where things go and never declare a token.** A
colour, a spacing or a radius written in an app stylesheet is a decision two surfaces will
eventually disagree about. A test asserts it for `app.css`; `window.css` is not covered
yet, and that gap is listed under Known compromises.

**Design rule 4 is enforced at the root**, not per element: `body` carries
`font-variant-numeric: tabular-nums`. There was a `.num` class for two batches and not one
element ever used it, so no figure the app drew was tabular. A rule that has to be
remembered at every call site is a rule that is not kept. Numbers inside a sentence are
figures too, which is why it is not scoped to figure elements.

Two places where the mockups are a round behind the shipping Swift app, and this app
follows the app:

- the panel's blocks carry their caption **above** them, not in a left column (the
  founder's clarification during batch 3 of M4: content in the centre, not titles left and
  values right);
- the plain button is quiet ink (`--text-2`) with the accent only under the pointer, where
  `tokens.css` colours it with the accent outright. A popover with two blue words in its
  footer reads as two links rather than as two quiet actions.

## The material

One decision per surface, made in `src-tauri/src/platform/`, and the page is told the
answer rather than guessing it (`data-material="glass"` or `"standard"` on the root).

| Surface | macOS 26 | Before 26 | Why |
|---|---|---|---|
| The panel | `NSGlassEffectView`, style Regular, radius 16, **with a filled backing** | `NSVisualEffectView` `.popover` | It is navigation layer all the way down. Pure glass takes the tone of whatever is behind it, so a "light" panel over a dark editor reads grey, and then its figures are being read against a moving backdrop |
| The window | `NSGlassEffectView`, style Regular, no radius, **clear** | `NSVisualEffectView` `.sidebar` | Its screens are the content layer and are already opaque in CSS. A filled backing would frost a solid colour and the sidebar would stop being glass at all. The system rounds a decorated window itself |

`PRUDENCE_GLASS_OPAQUE` overrides both, for photographing the other reading. It is a
screenshot hook, not a setting.

The **control** layer is CSS on both platforms: `tokens.css`'s `data-material="glass"`
rules give every button, pop-up and segmented control the same frost, and the app
stylesheets only take the *surface* tint away, because on a real window the surface
material is native. A `backdrop-filter` could not do the surface anyway: inside a webview
it samples the page, never the desktop.

## The layers

| Directory | What lives there | What may import it |
|---|---|---|
| `src/design/` | tokens, the DOM helpers, the brand mark, the purpose list, the charts | anything |
| `src/text/` | the two string tables, the string runtime, the formatters, the composed sentences | anything above `design` |
| `src/store/` | the shell's payload, turned into rows and the two windows the panel asks about | `ui`, `boot` |
| `src/ui/` | one file per surface: the panel, the window | `boot` only |
| `src/bridge.js` | every Tauri call in the frontend | anything |
| `src/boot.js` | start-up, for both pages | the two HTML entry points |

The frontend is **native ES modules**: `import` is the dependency order, so there is no
loader and no start-up file per page. There is still no bundler and no build step, which
is what keeps the Electron exit cheap and every module importable by `node --test`. That
last part is not a nicety: it is the only way a rule can be tested on both browser
engines, because a test that runs in Node runs the same on WebKit and on WebView2.

Before this the frontend was globals on `window` with a hand-written script injector, and
the two start-up files shared 106 identical lines and had already drifted.

## The bridge

**Every Tauri call in the frontend is in `src/bridge.js`.** Nothing under `src/design/`,
`src/panel.js` or `src/window.js` knows what a Tauri is.

This is load bearing, not tidiness. If the webview under this frontend ever has to change,
the shell and that one file are rewritten and everything else moves unchanged. That is the
way out if Tauri fails on a later macOS, and it stays open only while the rule holds.

The surface is thirteen commands: read the store, ask the shell about itself, log a line,
fit the panel to its content, hide the panel, open and close the window, remember the
section, quit, and the four the engine needs (where it is, run an action, choose the
executable, forget the choice). `test/bridge.test.mjs` parses both `bridge.js` and `lib.rs` and asserts
that the names and the **argument names** match, because renaming a Rust parameter breaks
the page at runtime with no error on either side.

**There is one channel in the other direction and it is not the bridge.** With the
`harness` feature built in, the shell drives `window.eval("window.Stress...")` against
`ui/window.js`. It is how a script switches screens and paints the compositor probe. It
is absent from a release build, and the page exposes `Stress` only when `shell_info` says
the build carries the harness.

## No build step

Native ES modules, no bundler, no transpiler. The browser loads the files as they are
written, and `tsc -p jsconfig.json` type-checks them without emitting anything.

Three reasons, in order: the source stays readable as itself rather than as an input to a
pipeline; the Electron exit stays cheap, because a frontend with no build is a frontend
any shell can serve; and a batch is judged on a picture of the running app, so nothing is
gained by putting a compiler between the source and the picture.

**Static checking is `tsc --checkJs` over JSDoc types**, not eslint. The defects worth
catching here are shape defects: a JSON string where an array was expected, an optional
read as if it were present, a language argument accepted and then ignored. `tsc` sees
those; eslint does not. It runs in the batch checklist and in CI.

## The page contract

**A screen is one module, one stylesheet and one line in a table.** This exists so that
several screens can be written at the same time without two of them touching the same
file, and so that a screen can be read on its own by somebody who has not read the rest.

To add a screen:

1. `src/ui/<screen>.js`, exporting one function named after the screen.
2. `src/ui/<screen>.css`, and a `<link>` for it in `window.html`.
3. One line in `src/ui/screens.js`.

That is the whole surface. Nothing else in the app names a screen.

### What a screen may and may not do

**It is handed everything and reaches for nothing.** The one argument carries `data` (the
whole store payload), `info` (`shell_info`), the scope (`project`, `range`, `week`), and
two callbacks (`onWeek`, `redraw`). A screen does not import the bridge, does not read the
store, does not touch `document` outside the tree it is building, and keeps no state
between renders: it is called again from scratch whenever anything changes.

**It returns one element** and appends nothing to the page itself.

**It owns no numbers.** Everything a screen prints comes from a reader in `src/store/`,
which is where the rule about sums and ratios is kept and tested. A screen that needs a
figure no reader provides adds the reader, with a test, rather than computing it inline.
This is the rule the whole app rests on, and a screen is where it would first be broken.

**Its stylesheet declares no design token** and holds only what that screen alone needs.
A rule two screens want moves to `design/components.css` in the same change; it is never
copied. A test reads every stylesheet on disk and fails on a token declared outside
`design/tokens.css`.

**Its strings are keys.** No English in a screen module, and no sentence assembled from
fragments with punctuation in JavaScript: one key with numbered placeholders, so another
language can order it differently. New keys go into both `src/text/strings.*.json`
by hand, in the same place in each; the strings test holds the two tables to each other.

**The pickers are declared, not assumed.** `scope: true` in the route table puts the
project and range controls above the screen. A screen that does not read them sets it
`false`, because a control that changes nothing is worse than no control.

### What is shared

| Shared | Where | Who may change it |
|---|---|---|
| Chart primitives | `design/charts.js` | by agreement; every screen draws with these |
| The DOM helpers | `design/dom.js` | by agreement |
| Store readers | `store/*.js` | the screen that needs a new one adds it, with a test |
| Formatters and strings | `text/` | additive only, via `DESKTOP_ONLY` |
| Shared components | `design/components.css` | additive; move, never copy |
| The window shell | `window.css`, `ui/window.js` | not from a screen |

## Platform differences

**They live in `src-tauri/src/platform/`**, behind one interface with three
implementations (`macos`, `windows`, and a do-nothing fallback). The page never asks which
system it is on. A difference that cannot be held in that folder is a difference that will
end up in the page, which is what closes the door on Windows.

Today that interface is five functions: apply the material, find the tray anchor, set the
status item's highlight, show or hide the Dock icon, describe the platform.

Two things macOS 26 does that cost us a day, written down so they cost nobody else one.

**A status item is laid out in two steps, and the first one lies.** AppKit gives the
status item window its size before it gives it a position, so the first frame it reports
is a real 36 x 33 sitting at (0, -22) or (0, -33), off the bottom of the screen. Anything
that treats a non-empty frame as a laid-out one anchors the panel to a corner. The test is
where the frame is, not how big it is: a menu bar's top edge is its screen's top edge, and
no unplaced frame satisfies that. `platform::macos::in_the_menu_bar` is that rule, unit
tested against both observed bad frames.

**A status item is hosted by Control Center, not by us.** Our process owns no window in
the menu bar, so no outside script can find our item in `CGWindowListCopyWindowInfo`; it
is attributed to Control Center along with everyone else's. `Scripts/menubar.py` cannot
locate the item on its own and has the app report its own anchor instead, over a
harness-only line that is not in a release build. Related: the menu bar takes its tint
from the desktop picture rather than from the appearance setting, so there is no light
menu bar to photograph without changing the wallpaper.

## The app owns no numbers

`src-tauri/src/store.rs` opens the store read-only, refuses a contract version outside
`SUPPORTED_CONTRACT`, and selects from `app_*` views and nothing else. The page may **sum
view columns into a bucket** and take the **ratio of two columns of the same row**, and
nothing else. A median, a threshold or an attribution is a new view in
`src/prudence/store/app_views.py`, never a function here.

Any number on a screen that is not one of those three things is a bug, however reasonable
it looks.

## Known compromises

Registered per `memory/rules.md`, 2026-09-21: what it assumes, what the user sees when the
assumption breaks, and the condition under which it is removed. A sleep, a retry, a
special case or a widened tolerance that is not in this table is a patch and does not go
in.

### The watcher waits 750 ms and retries a read eight times

`watcher.rs`, `QUIET` and `RETRIES`. An ingest writes in bursts and a file event arrives
mid-write, so the watcher waits for quiet and then tests the store by reading it. A store
caught mid-write answers with an error rather than a payload, and announcing then would
make every page draw the failure.

- **Assumes:** an ingest's writes are never more than 750 ms apart, and one that is still
  going after eight tries (about 6 seconds) will produce another file event when it ends.
- **When it breaks:** a very slow ingest announces twice, so the pages re-read twice; or
  the watcher gives up and the pages stay one ingest behind until the next write. Both are
  logged by the shell.
- **Removed when:** the engine signals the end of an ingest directly, which is the honest
  fix and belongs on the engine side.

### `in_the_menu_bar` allows a point of slack

`platform/macos.rs`. The rule is that a status item's top edge is its screen's top edge,
and it is tested with `abs(...) <= 1.0` rather than for equality. Every frame observed has
been exactly equal; the tolerance is there because a menu bar is not measured to the
micron and a future display scale could land a half point off.

- **Assumes:** no unplaced frame ever lands within a point of a screen's top edge. The two
  observed bad frames sit 971 and 982 points away.
- **When it breaks:** the anchor is accepted a moment too early and the panel opens away
  from its icon, which is the defect this rule was written to fix.
- **Removed when:** the tolerance is shown to be unnecessary on every scale factor, or
  AppKit gives us a placement signal we can ask instead of measuring.

### A refresh that fails leaves the old figures on screen and says nothing

`boot.js`, the `catch` inside `onStoreChanged`. The store was readable a moment ago and
will be again; replacing a correct screen with an error because one re-read lost a race
would be worse than being briefly stale. The shell's log carries the reason.

- **Assumes:** the failure is transient.
- **When it breaks:** the figures are stale and nothing on screen says so. A store that
  becomes permanently unreadable while the app is open looks fine until it is relaunched.
- **Removed when:** the page can show a quiet "these numbers are from HH:MM" line, which
  is the right answer and is a design question, not a bug fix.

### The status item's button is found by class name

`platform/macos.rs`, `status_bar_button`. Neither Tauri nor `tray-icon` exposes the
`NSStatusItem` it created (`TrayIcon.inner` is private), and `tray-icon` clears the
highlight on mouse-up, so the capsule would last only while the button is held. The
window list is walked for the one window whose class name contains `StatusBar`, and the
first `NSButton` inside it is the status item's.

- **Assumes:** AppKit keeps calling that window class `NSStatusBarWindow`, and this
  process owns exactly one status item.
- **When it breaks:** the icon stops highlighting while the panel is open, and the panel
  opens in a screen corner instead of under the icon, because `tray_anchor` is the same
  lookup. Both are silent to the user today; `shell_info.tray_highlight` carries the
  answer and the shell logs it.
- **Removed when:** either Tauri exposes the status item, or the tray is built with
  `tray_icon` directly (its `ns_status_item()` is public) instead of through
  `TrayIconBuilder`. Worth pricing before the Windows work, because `tray_anchor` is one
  of the five functions the platform boundary rests on.

### The WKWebView is found by class name

`platform/macos.rs`, `webview_view`. The glass view takes the webview as its content view
so the material owns its content rather than sitting behind it; the webview is found as
the first subview whose class name contains `WebView`.

- **Assumes:** wry's view is the outermost `*WebView*` in the window's tree.
- **When it breaks:** the glass is applied behind the webview instead of owning it, so
  the frost does not refract properly. The failure is detected and recorded in
  `MaterialReport.attempts`, which `shell_info` carries.
- **Removed when:** Tauri exposes the webview's `NSView` synchronously. `with_webview`
  exists but its closure must be `Send` and cannot carry an AppKit object out.

### The relative time counts in fixed seconds, not in calendar units

`text/fmt.js`, `relative`. `Intl.RelativeTimeFormat` needs a unit and a count, so the
unit is chosen from a table of fixed second counts.

- **Assumes:** a month is thirty days and a year is 365.
- **When it breaks:** a timestamp several months old can read one unit off. The only
  timestamp the app prints this way is the last ingest, which is hours or days old.
- **Removed when:** something needs a correct long-range relative time, at which point
  the unit is chosen with `Intl.DateTimeFormat`'s calendar arithmetic instead.

### The login-shell probe is killed after ten seconds

`engine.rs`, `SHELL_TIMEOUT`. The last step of finding `prudence` is
`zsh -ilc 'command -v prudence'`, because an app launched from Finder inherits
`launchd`'s environment and never reads `.zshrc`. A shell start-up is arbitrary code: an
rc file that waits on a network share would hang the answer for as long as the share
takes, so the child is killed at the deadline and the answer becomes "not found".

- **Assumes:** a login shell that is going to answer answers within ten seconds.
- **When it breaks:** a machine whose shell start-up is slower than that reports "engine
  not found" although the engine is installed. The way out is on screen: the Choose
  button sets the path directly and the search never has to run again. The shell log
  carries the line that says the probe was killed.
- **Removed when:** something cheaper than a shell can be asked. There is nothing today:
  the PATH that has `prudence` on it exists only inside that shell.

### A run has no deadline at all

`engine.rs`, `Engine::run`. An ingest over a large archive takes minutes and a review
takes seconds, and any number chosen as a limit would be a guess that fails on the
founder's 830 MB store or on somebody's laptop. So the app waits for the process to exit,
which is the actual event.

- **Assumes:** `prudence` always exits.
- **When it breaks:** the strip reads "Ingesting..." for as long as the app is open and
  both actions stay refused, because the shell holds the one-run-at-a-time flag. Nothing
  is lost and nothing is wrong with the store; a relaunch clears it.
- **Removed when:** the run can be cancelled from the strip, which is the honest fix and
  is a design question (what a half-finished ingest leaves behind) rather than a timeout.

### The engine's own error text is English on a Chinese interface

`engine.rs` sends a *word* for each kind of failure, which the page turns into a sentence
in the reader's language, and under it the engine's own message as it came. That message
is English, because the CLI is. `store.rs` already does the same with its errors and
`boot.js` prints them as they come.

- **Assumes:** a reader would rather have the engine's exact words than a paraphrase.
- **When it breaks:** a Chinese reader sees one English line under a Chinese one.
- **Removed when:** the engine can be asked for a localised message, which is an engine
  decision. Translating it here would make the app and the CLI say different things about
  the same failure, which is worse.

### `window.css` is not covered by the no-tokens test

`test/tokens.test.mjs` asserts that `app.css` declares no custom property; `window.css`
is not checked, so a token could be declared there.

- **When it breaks:** two stylesheets disagree about a colour and nothing says so.
- **Removed when:** the test takes a list of stylesheets rather than one. Batch 5, which
  is the next batch to touch `window.css`.

## Working on the founder's machine

Two rules that exist because each was broken once.

- **Keep the PID you launched and kill that PID.** Never `pkill` by name or path: the
  founder's own `Prudence.app` is also called Prudence, and on 2026-09-21 a `pkill` by
  path quit it out from under them. `Scripts/shot.py` and `Scripts/stress.py` both hold
  the PID they started.
- **Never photograph a region you do not own.** A screenshot of a frosted surface carries
  whatever was behind it. Every picture is taken over the app's own backdrop window, and
  the scripts refuse to fire unless the app's own window is the frontmost thing over that
  rectangle. The first run of `shot.py` photographed the founder's browser; the check
  exists because of it.

## Localisation

Two files, `src/text/strings.en.json` and `strings.zh-Hans.json`, one key set. **They are
the source of truth**, edited by hand; `test/strings.test.mjs` holds them to each other
(same keys, placeholders in each language's own order, plurals, no accidental duplicate
text). They were first generated from the Swift app's String Catalog on 2026-09-21, before
that app was retired to the `mac` branch.

- **A missing key is a bug, not a fallback.** `Str.t` returns the key itself so a screen
  still draws, and the suite fails on it.
- **Placeholders are numbered and filled in each language's own order.** That is the whole
  reason they are `%1$@` and not `%@`.
- **Plurals are a plural entry, not a suffix.** The form comes from `Intl.PluralRules` in
  the language in force, so English says "1 session" and "3 sessions" and Chinese says
  "1 个会话" either way. The count inside it is formatted in the reader's locale first.
- **Both tables are loaded at start-up**, because the language setting switches between
  them without a relaunch.

`src/design/fmt.js` is the port of `PrudenceUI/Fmt.swift`: counts, token abbreviations,
hours, stamps, relative times, days, the four count phrases, the list separator, the
purpose names. **Two things deliberately do not go through the locale** and are marked
where they are: the `%.0f%%` share and the plain ungrouped integer inside an observation
sentence, which have to match `store/observations.py` character for character or the
word-for-word test against `app_observation.sentence` fails.

The product's name is not a catalog key. It is `Str.productName`, because it is not
translated and because the name research is still open: renaming is two edits, that
constant and the bundle's display name.

## Components

Grown by each batch. Batch 1 adds the window shell only.

| Component | What it is | Where |
|---|---|---|
| The panel | 360 pt, one column, a caption above every block, the action grid at the foot | `src/ui/panel.js` |
| The window shell | The system's titlebar overlaid, a sidebar with four entries, the heading and the screen's controls on one fixed row, one screen at a time | `src/ui/window.js`, `src/window.css` |
| `miniStack` | One row of a stacked bar: the composition of a whole, in a single line | `src/design/charts.js` |
| The backdrop | A plain full-screen window of the app's own, for screenshots only | `src/backdrop.html` |
| The engine block | Where `prudence` is, its version against the store's, the two actions, the picker | `src/ui/engine-section.js`, `ui/engine-section.css` |
| The activity strip | One report at the foot of the window: what a run is doing, and how it ended | same file |

**The engine block is placed, not owned, by a screen.** The Settings screen puts it where
it goes and the block says what is in it, so the two can be written at the same time. It
is also the one thing under `src/ui/` that talks to `bridge.js`: it is not a screen, and a
screen may not, which is why `ui/review.js` exports a `REVIEW_NOW` seam and the wiring in
`window.html` fills it in rather than the screen calling the shell itself.

**The strip is on the page, not in a screen.** A run outlives the screen it was started
on: the Review screen is rebuilt whenever the store changes, and the store changing is
exactly what a successful run causes. So it is appended to the body once, by the same
wiring, and it is the only place a run reports whichever button began it.

**There is one chart.** The mockups' module had seven builders and 598 lines; six drew
screens that do not exist yet and none had been read to a product standard. They are not
in the app. `docs/design/mockups/charts.js` keeps them as the visual reference, and the
batch that builds each screen writes that screen's chart against the rules at the top of
`design/charts.js`.

## What the window remembers

`src-tauri/src/ui_state.rs`, one small JSON file in the app's own configuration directory.
Not beside the store: nothing this app remembers is the engine's business, and the
engine's directory is somewhere an agent may be pointing at a copy.

**A remembered value this build no longer understands is ignored rather than forced**, and
a frame below this build's own floor or carrying a non-finite number is dropped rather
than clamped, because a window in the wrong place is worse than a window in the default
place. `PRUDENCE_UI_MEMORY=off` starts with nothing remembered and writes nothing, which
is what every screenshot run uses.

## The keyboard

| Key | Does |
|---|---|
| Cmd-1 / 2 / 3 / 4 | Overview, Review, Observations, Settings |
| Cmd-, | Settings |
| Cmd-R | Goes to the Review screen. Its button now runs the engine; the shortcut still only navigates |
| Esc | Closes the panel |
