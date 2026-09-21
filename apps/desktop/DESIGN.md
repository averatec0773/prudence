# The desktop app's design system

What every surface of the Tauri app is built from, and the rules that keep it one app.

This file is written **along the way**, not at the end: a design document written at the
end describes what happened, one written while the work is done constrains it. It starts
in batch 1 with the rules and the decisions already made, and every batch that adds a
component, a chart or a screen adds its row. Where this document and a screen disagree,
the screen is wrong.

`apps/mac/DESIGN.md` is the same document for the frozen Swift app and is still the best
description of the tokens, the seven chart shapes and the localisation rule. Everything in
it that is about SwiftUI is not about this app; everything in it that is about the product
is, and moves here as each batch brings the code.

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
record; this file is the product's. `apps/mac/DESIGN.md` prints the table (purpose palette, outcome pair,
project scale, surfaces and ink, spacing, type, radii, motion) and
`test/tokens.test.mjs` asserts the file against it, so a token table nobody checks cannot
drift from what is drawn.

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

The surface is nine commands: read the store, ask the shell about itself, log a line,
fit the panel to its content, hide the panel, open and close the window, remember the
section, quit. `test/bridge.test.mjs` parses both `bridge.js` and `lib.rs` and asserts
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

Two files, `src/design/strings.en.json` and `strings.zh-Hans.json`, 227 keys each. They
were generated once from the Swift String Catalog by `Scripts/strings.py` and **are the
source of truth from then on**; the generator and its `--check` test exist only to stop
the two dictionaries drifting while `apps/mac/` is still in the repository, and both die
with it.

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
| Cmd-R | Review now (batch 7; it says so until then) |
| Esc | Closes the panel |
