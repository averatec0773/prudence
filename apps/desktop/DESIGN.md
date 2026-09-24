# The desktop app's design system

What every surface of the Tauri app is built from, and the rules that keep it one app.

This file is written **along the way**, not at the end: a design document written at the
end describes what happened, one written while the work is done constrains it. It starts
in batch 1 with the rules and the decisions already made, and every batch that adds a
component, a chart or a screen adds its row. Where this document and a screen disagree,
the screen is wrong.

The Swift app's `DESIGN.md` (`apps/mac/DESIGN.md` at commit `133a074`, the last before the
Swift app was retired from master) is the same document
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

### Bucket palette

What each reply of the model did, from its tool calls alone (`store/buckets.py`, bucket
rule version 1): **change** wrote a file, **run** ran a command or a tool that acts,
**read** only looked, **talk** did none of those (it spoke, asked, or dispatched an agent).
In Chinese the four are 改动, 运行, 阅读, 对话. Every token chart and the panel's seven days
are drawn in these, and only these.

| Bucket | Light | Dark |
|---|---|---|
| `--b-change` | `#C4501B` | `#F06A36` |
| `--b-run` | `#0B7FA8` | `#2AA3CF` |
| `--b-read` | `#856C00` | `#C4A020` |
| `--b-talk` | `#8A4FC7` | `#AD86EC` |

**The order is fixed: change, run, read, talk.** It is the engine's precedence order (a reply
that did several things is in the first of them it did) and the order `prudence usage`
prints, so the chart stacks from the baseline up in it, the legend, the table's columns and
the panel's sentence read in it, and it is never sorted by size. `design/buckets.js` holds
the list and `test/buckets.test.mjs` pins it to the engine's.

**Why four new colours and not the purpose palette.** The purposes still carry meaning on
the Review screen (a stored review's activity table) and in observations split on a
purpose, so blue is still "development" there; drawn on the Overview, it would say
"change" is development. The four are chosen so that none is a purpose, project, outcome
or accent colour (a test asserts it), none is red or green (colour is identity, never a
verdict), and each reads as text at 4.5:1 or better on its appearance's surface, because
the panel colours the words themselves (a test asserts that too). The categorical checks
were run with the dataviz validator: the light set passes all five; the dark set passes
separation and contrast and sits above that validator's lightness band on purpose, since
text contrast on `#2C2C2E` is the constraint that decides it here. The nearest neighbour
on the same screen is `--proj-4` beside `--b-talk`, and a fifth project is the first time
the two meet.

**A bucket this build does not know** stays in every total and in no colour: the four
shares fall short of a hundred and the panel's bar leaves the rest of its track unfilled,
rather than one of the four absorbing it. The engine pin fails before that can ship.

**Two meanings of "bucket" in the code.** A day or a week on the Overview's time axis was
called a bucket before these existed (`store/overview.js`, "the bucket rule" below). In code
that slot keeps the name and these four are always `BUCKETS` and `byBucket`; the reader
sees neither word.

#### The captions a bucket chart carries

- **The per-slot totals are behind the disclosure, not under the chart.** The figure's
  caption stays for a screen reader and is hidden; the table in "How this is measured"
  has one row per day or week, one column per bucket and the slot's total. At thirty days
  the printed caption was a paragraph of thirty dates between the bars and the legend.
- **The legend names only the buckets present in the range**, in the fixed order.
- **Guessed tokens are said quietly, and only when there are any.** `heuristic_tokens` is
  the part whose bucket rests on a tool's name rather than on the rule's lists; above zero
  for the range, one `panel-note` line under the legend says how many and what share, and
  at zero there is no line at all.
- **The note says what the four are**, in the reader's words, on every range; the method
  names the view, the precedence and what is not counted.
- **The panel's sentence is the legend**: each bucket's word in its own colour, then its
  share ("改动 40%，运行 33%，阅读 20%，对话 7%"), and the bar under it in the same order.

### Purpose palette

Drawn only where the engine still speaks in purposes: a stored review's activity table and
its composition bar, and an observation split on a purpose. The token charts left it at
contract 4.

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
| `src/design/` | tokens, the DOM helpers, the brand mark, the bucket and purpose lists, the charts | anything |
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
`src/store/` or `src/ui/` knows what a Tauri is.

This is load bearing, not tidiness. If the webview under this frontend ever has to change,
the shell and that one file are rewritten and everything else moves unchanged. That is the
way out if Tauri fails on a later macOS, and it stays open only while the rule holds.

The surface is the commands `lib.rs` hands `generate_handler!`: read the store, ask the
shell about itself, log a line, fit the panel to its content, hide the panel, open and
close the window, remember the section, quit; the ones the engine needs (where it is, what
it is doing now, run an action, choose the executable, forget the choice, install or
update it, the repositories it records and a change to one, whether a review is ready,
the last records of its run log, and `prudence diagnose`); two for the model settings
(read them, set the prose language); five for the app's own settings (read them, and one
per setting); one that opens a link **by name**, because the shell owns the addresses and
a command that took a URL would open whatever it was handed; and one that reveals a folder
by name on the same rule (`logs`, or the bundle the last diagnosis wrote). `test/bridge.test.mjs` parses both `bridge.js` and `lib.rs` and asserts that the
names and the **argument names** match, because renaming a Rust parameter breaks the page
at runtime with no error on either side.

**Five events go the other way**, and each is a string on both sides with nothing else to
catch a rename, so the same test asserts them too: `store-changed`, `settings-changed`,
`engine-install`, `engine-progress` and `engine-activity`. The first two carry no payload,
on purpose: there is one way to get the store's contents and one way to get the settings,
and both are a command. The other three carry theirs, because each is true for a moment:
uv's lines, a run's step, and whether a run is going (`src-tauri/src/activity.rs`, below).

**`src/ui/wiring.js` is the one file under `src/ui/` that calls the bridge.** A screen may
not, and several pieces of the window need to: the toolbar and the status row
(`ui/activity.js`), the engine block, the Repositories screen and the Settings screen's
controls. Each declares a port and `wiring.js` fills it in, which is also what lets each
be driven against a fake shell in a test.
The panel is the exception and says so in its own file: it talks to `bridge.js` directly,
because it has no wiring file of its own and its port exists only so a test can press its
two engine buttons.

**There is one channel in the other direction and it is not the bridge.** With the
`harness` feature built in, the shell drives `window.eval("window.Stress...")` against
`ui/window.js`. It is how a script switches screens and paints the compositor probe. It
is absent from a release build, and the page exposes `Stress` only when `shell_info` says
the build carries the harness.

**What the page costs is measured through the same door.** `src/measure.js` writes timings
to the shell's standard error through `page_log`, and `boot.js` turns it on only when
`shell_info.harness` is true, so a release build calls it and it does nothing.
`PRUDENCE_MEASURE=1` on a harness build makes the window walk itself once it has drawn
(every screen, every range, every project) and say what each move cost and how many DOM
nodes it built. That walk is started by the page at the end of its first draw, not by an
eval, for the reason `PRUDENCE_PRESS` is: an eval from the shell races the first draw and
would time a window that is not built yet.

## One copy of the store's answer

**The shell reads the store once per change, and a page redraws only when what it would
draw has changed.** `store::snapshot` in `src-tauri/src/store.rs` holds the one copy;
`watcher.rs` invalidates it on the line where it announces, which is the app's whole
notion of the store having moved; `src/store/drawn.js` compares the `revision` the
snapshot stamps against the one on screen. A setting is not the store, so that path
forces its redraw.

Before this, the panel and the window each read all seven views for themselves and each
rebuilt its whole DOM on every announcement. Measured against a copy of the founder's
851 MB store on 2026-09-22: 1,225 ms of reading twice at launch, and a further 440 ms
twice plus two whole-page rebuilds for figures that had not changed, because asking the
engine whether a review is ready checkpoints the write-ahead log and the checkpoint moves
the two files the watcher fingerprints.

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
whole store payload), `info` (`shell_info`), the scope (`project`, `range`, `bucket`),
whether an ingest is going anywhere (`ingesting`), and three callbacks (`onBucket`,
`onProject`, `redraw`). `onProject` sets the window's one project filter, which is how the
Repositories screen's rows do what the picker does. A screen does not import the bridge, does not read
the store, does not touch `document` outside the tree it is building, and keeps no state
between renders: it is called again from scratch whenever anything changes.

**One exception, and only one: a screen may remember its own navigation.** The Settings
screen keeps which of its five tabs is open in a module-level variable. Which tab is open
is navigation, not data, and a screen rebuilt because an ingest landed must not throw the
reader back to the first tab while they are half way through changing a setting. Nothing
about the data may be kept this way, and the five panes are built together and shown by a
flag, so choosing a tab redraws nothing at all. (A batch of level changes on the
Repositories screen outlives the screen it was started on, and is kept in `BATCH` for the
reason `store/asked.js` keeps the engine's answers: it is a process in flight, not data.)

An answer from the engine is **data**, so a screen does not keep one either. The model,
source and repository answers live in `store/asked.js`, which is also where the rule about how
often the engine may be asked is kept.

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

Today that interface is eight functions: apply the material, find the tray anchor, set the
status item's highlight, show or hide the Dock icon, hide the app, the line that installs
uv, describe the platform, and whether another process holds the engine's ingest lock
(`lock_held`, which on macOS asks `F_GETLK` and never takes the lock; see Known
compromises).

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

## The range picker and the bucket rule

Seven ranges: **1 day, 7 days, 30 days, 60 days, 90 days, 365 days, all.** The labels are
one plural entry (`unit.rangeDays`) and one word for "All", so English says "1 day" and
"7 days" and Chinese says "1 天" either way, and seven near-identical catalogue keys
cannot drift apart.

**A bucket is a local day up to sixty days, and an ISO week from ninety days out.** It is
written once, in `RANGES` in `src/store/overview.js`, and everything else reads it from
there.

The boundary is set by the plot, not by the data. The charts draw into a box 760 units
wide and thin their labels past fourteen slots and again past twenty-eight
(`design/charts.js`, `labelEvery`). Sixty daily slots is about twelve units each, which is
the narrowest bar that is still a bar; ninety would be eight and a year would be two. Past
sixty days the honest picture is weeks.

Three consequences, each with a test:

- **One day is one bucket, never an empty chart.** A range of a day is a real question,
  usually asked of the three cards, and the chart under them draws its single bar rather
  than saying there is not enough to draw.
- **The outcomes chart is weekly under every range.** `app_outcomes_by_week` has one row
  per project per week and there is no daily view; re-bucketing a weekly row into a day
  would be the app inventing a figure. Under a daily range the card's note carries the
  extra sentence saying so, as a whole key in each language rather than two glued
  together.
- **The two charts no longer share one axis under a daily range.** They did while both
  were weekly. The tokens chart follows the range's own grain and the outcomes chart stays
  weekly, so the note is what tells the reader which is which.

The heat strip is one cell per local day, seven rows Monday first, whatever the range.

### The heat strip's geometry

It had no axis at all until this sheet: seven rows and N columns of squares, with the day
only inside each cell's `title`, which a pointer reaches and a screenshot does not, so the
reader could not tell which row was Monday. The strings were already in the catalogue
(`weekday.mon` to `weekday.sun`) and nothing drew them.

In the SVG's own units, all of it in `design/charts.js`:

| | |
|---|---|
| A cell | 13 square, 3 between them, so a row and a column are both 16 |
| The weekday gutter | 24 wide, the label right-aligned 6 before the first column and on the cell's own middle |
| The month band | 14 tall under the grid, a name drawn at the **left edge** of the first column whose Monday falls in that month |
| The whole strip | `24 + 16N - 3` wide, `109 + 14` tall |

Two rules that are not geometry:

- **The chart holds no text.** `weekdays` is the seven names in the reader's language and
  `monthOf` answers a column with its month name. Both come from the screen, as every
  other label in this module does.
- **A month is named once.** The first column carries its own month too, because a strip
  that starts mid-month would otherwise leave its opening weeks unnamed. A week that
  straddles a month end belongs to the month its Monday is in, which is what the card's
  method sentence says.

## The app owns no numbers

`src-tauri/src/store.rs` opens the store read-only, refuses a contract version outside
`contract::SUPPORTED` (4, and only 4: contract 3 had the purpose view this build no longer
reads, and the refusal tells the reader to run `prudence rebuild` or Ingest now when the
store is the older side and to update the app when it is the newer), and selects from `app_*` views and nothing else. The page may **sum
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
- **When it breaks:** the first half of that assumption does not hold on a large store and
  the cost is higher than this entry used to claim. Measured on 2026-09-22 against an
  851 MB copy with the window open: **one `prudence ingest` from a terminal announced
  eleven times, and the next announced fifteen.** The view rebuild writes in bursts
  further than 750 ms apart, and every quiet gap that then reads cleanly is an
  announcement, so both pages re-read the whole payload eleven times for one ingest. The
  figures are always right and the window is busy while they arrive. With nobody writing
  at all it announces **zero** times in thirty seconds, so it is not chasing its own reads.
- **Removed when:** the engine signals the end of an ingest directly, which is the honest
  fix and belongs on the engine side. Lengthening `QUIET` would trade one guess for
  another; the engine knows when it has finished and nothing here does.

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
- **When it breaks:** the toolbar and the status row show the run for as long as the app
  is open and both actions stay refused, because the shell holds the one-run-at-a-time
  flag. Nothing is lost and nothing is wrong with the store; a relaunch clears it.
- **Removed when:** the run can be cancelled from the toolbar, which is the honest fix and
  is a design question (what a half-finished ingest leaves behind) rather than a timeout.

### A run started outside the app is seen by its lock, and its end is looked for every two seconds

`src-tauri/src/activity.rs` and `watcher.rs`, `LOCK_POLL`. The toolbar and the status row
show a run from a terminal (or the plugin) as well as one this app started. The engine holds
an advisory `flock` on `ingest.lock` beside the store for as long as an ingest or a rebuild
runs, so the watcher asks who holds it (`platform::lock_held`, `fcntl(F_GETLK)`, which never
takes it) whenever the store's files move. The end of such a run makes no file event of its
own, so while the lock is held it is asked again every two seconds.

- **Assumes:** the engine keeps taking that lock under that name for exactly the length of
  a run (`src/prudence/store/db.py`, `ingest_lock`), and macOS keeps reporting a `flock`
  through `F_GETLK`, which is a property of the BSD lock manager: measured on 2026-09-23 and
  pinned by `platform::macos::lock_tests`.
- **When it breaks:** a run from outside shows as idle, and the window catches up only when
  the watcher announces the store, which is what happened before this. On Windows and Linux
  it is always that: neither can ask without taking. A `prudence rebuild` reads as an
  ingest, because the two hold the same lock. The toolbar says "started outside the app" and
  draws no bar, because the engine writes progress lines only to the process that asked.
- **Removed when:** the engine announces a run's start and end itself, which is also the
  removal condition of the watcher's own entry above.

### The Repositories screen's survival carries its lines, not its coverage

`ui/repositories.js`, `aliveCell`. Every share on this app's screens carries the number it
is over, and here that is the lines measured at thirty days (`measured_30d`, summed). The
attribution coverage `prudence outcomes` prints beside it is a mean over commits, and
`app_outcomes_by_week.coverage` is already a mean per week: averaging those means is a
different number from the engine's, and a weighted one would need a count the view does
not carry.

- **Assumes:** the lines measured are the context a reader needs to trust a share of them.
- **When it breaks:** a repository whose sessions wrote little of what was committed shows a
  survival share with no hint of that.
- **Removed when:** the engine publishes a per-repository coverage in a view; the column
  then carries it under the share, the way the Overview's card draws its band.

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

### `prudence config model` is read, not decoded

`model.rs`. Every other call the app makes to the engine appends `--json` and decodes the
answer. `config model` has no `--json`, so its seven lines are matched against their seven
labels and split there. The labels are the parse and not the whitespace: the CLI pads each
one to a column, so six are followed by a run of spaces and `key variable` by exactly one,
because that label is already as wide as the column.

- **Assumes:** those seven labels keep their spelling, and a line that is not one of them
  is prose rather than a setting.
- **When it breaks:** a renamed label reads as missing, and the Model tab leaves that row
  out rather than showing something wrong. A whole new line is ignored.
- **Removed when:** `prudence config model` grows `--json`, which is an engine change and
  is the honest fix.

### The timed ingest looks at the clock every thirty seconds

`timer.rs`, `TICK`. The interval is compared against a monotonic clock, and the comparison
is made when the next one is due or one tick from now, whichever comes first. The wait is
on a condition variable rather than a sleep, so changing the setting takes effect at once
rather than at the end of whatever wait was under way.

- **Assumes:** a timed ingest that starts up to thirty seconds late is a timed ingest that
  ran. The shortest interval offered is fifteen minutes.
- **When it breaks:** nothing a reader can see. A machine asleep through a due time runs
  the ingest when it wakes, once, not once per interval missed.
- **Removed when:** an interval shorter than a minute is offered, at which point the tick
  has to be the interval and this stops being a simplification.

### Open at login is asked for every time rather than remembered

`lib.rs`, `app_settings`. It is the one setting this app does not store: the system stores
it, and macOS can refuse to register a login item for a copy that is not where it expects
one. So it is read from `tauri-plugin-autostart` on every `shell_info`, and the control is
ticked from that answer rather than from what was asked for.

- **Assumes:** asking the plugin is cheap enough to do on every page load. It reads one
  file.
- **When it breaks:** a slow answer would slow the first draw of both pages.
- **Removed when:** it is measured and found to cost anything, at which point it is cached
  for the launch and invalidated by the setter.

### Whether a review is ready costs two runs of `prudence status`

`lib.rs`, `engine_readiness`. The numbers come from `status --json`, and both lines, ready
and not, are composed from them in the reader's language (`text/sentences.js`). The
engine's own `review:` line comes from `status`, because the JSON carries none, and is kept
as the line's `title` on the panel and on the Review screen, so the composed sentence can
be checked against the engine's words. The text status is asked for only when a review is
ready, so a store that is not ready costs one run.

- **Assumes:** the two runs, a moment apart, agree about the same store.
- **When it breaks:** an ingest landing between them would put a ready sentence beside
  numbers from before it, which is a line one draw out of date.
- **Removed when:** `status --json`'s `readiness` block carries the sentence the `review:`
  line prints. That is an engine change and is the honest fix.

### Every answer the engine gives about itself is remembered against the store's stamps

`store/asked.js`, and `store/readiness.js` on top of it. Three questions go through it:
whether a review is ready (`status --json`), what model the engine would use
(`config model`), and which repositories it records (`init --scan --json`). Each is asked
again only when `app_status.last_ingest_at` or the newest review's id has moved.

This is not a cache for speed: asking on every draw closes a loop with the store watcher,
because the engine opens the store read-write and SQLite's checkpoint on close changes
exactly the two files `watcher.rs` fingerprints. Measured on 2026-09-22 against a copy of
the founder's store: 270 runs of `prudence status` in three minutes with nothing else
happening, and separately, with the window left on Settings during one 230-second ingest,
fourteen extra processes, because an ingest announces itself about eight times as it works
and all five Settings panes (the repositories were one of them then) were built whichever
tab was open.

- **Assumes:** nothing changes any of the three answers except an ingest, a review, or a
  command this app itself ran. The third is why the memo takes a `keep`:
  `prudence init --enable` writes `config.toml`, which no stamp sees.
- **When it breaks:** a line is one store behind. `prudence config model --backend` or an
  edit to `config.toml` from a terminal, under a running app, is the case that would show:
  the Model tab keeps the answer from before it until the next ingest.
- **Removed when:** the shell can answer these without a subprocess, or the engine
  announces that it has finished a run. The second one is already the removal condition of
  the watcher's own entry above.

### The panel's two late rows are reserved at two lines and one

`ui/panel.js` and `app.css`, `.pop-reserve`. The readiness answer arrives from a subprocess
after the panel has been shown and anchored, and a popover is only as tall as its content,
so the window was re-measured and re-anchored under the reader: 635 px at render and 677 px
a second later. The slots are now in the layout from the first paint, and the answer is
written into one of them.

- **Assumes:** a run's report is one line, and the readiness sentence is two at 360 pt. Both
  sentences this app composes, ready and not, are two lines in both languages today.
- **When it breaks:** a longer sentence still grows the panel, because `refit` still runs
  after the answer: the alternative is a sentence cut off inside a fixed slot, and a window
  that moves is better than a figure that cannot be read.
- **Removed when:** the shell can size the panel for its final content before showing it,
  or the readiness answer is known before the first paint.

### The panel's seven days are local days, and the CLI's are 168 hours

`store/payload.js`, `lastSevenDays`. The panel sums `app_usage_by_bucket_day` over today and
the six local days before it. `prudence usage --last 7d` counts back 168 hours from the
moment it runs, in UTC. A view of local days cannot cut one in half, so the two windows
differ by the replies of part of one day, and the figures differ by them.

- **Assumes:** a reader of "Last 7 days" means seven calendar days of their own.
- **When it breaks:** the panel's tokens and shares disagree with `prudence usage --last 7d`
  run at the same moment, by whatever was spent between local midnight six days ago and
  the same clock time that day. `prudence usage --last <that midnight in UTC>` agrees with
  the panel exactly, which is how the batch check is made.
- **Removed when:** the CLI's window is the local day, or the engine publishes a view the
  two share. Either is an engine decision.

### `window.css` is not covered by the no-tokens test

`test/tokens.test.mjs` asserts that `app.css` declares no custom property; `window.css`
is not checked, so a token could be declared there.

- **When it breaks:** two stylesheets disagree about a colour and nothing says so.
- **Removed when:** the test takes a list of stylesheets rather than one. Batch 5, which
  is the next batch to touch `window.css`.

### An agent's display name is a constant, not a catalogue key

`ui/repositories.js`, `SOURCE_NAMES`. "Claude Code" is the same in both languages, and
`test/strings.test.mjs` refuses a key whose two values are identical, for the same reason
`LANGUAGE_NAMES` is a constant here.

- **Assumes:** no agent Prudence reads renames itself per language.
- **When it breaks:** a key the app has not learned is drawn as the engine wrote it, which
  is a lower-case identifier on a screen of names.
- **Removed when:** a source needs a name that differs between the two languages, which is
  the point at which it is a translation and belongs in the tables.

### A batch is one run of the engine per repository

`ui/repositories.js`, `startBatch`. `prudence init --enable` takes one repository, so setting
twelve of them is twelve subprocesses, sequentially because they all write `config.toml`.

- **Assumes:** a run is fast enough that a counter is enough of a report, which held for
  three at a time on the founder's machine.
- **When it breaks:** a selection of twenty is twenty process launches, and a refusal
  half way through leaves the list half changed. That is why the bar counts, why the
  sentence says what stayed changed, and why the list is re-read from the engine rather
  than from the clicks.
- **Removed when:** `prudence init --enable` takes more than one repository.

### What the engine says it is, is remembered against the file rather than asked again

`engine.rs`, `version_of`. "Found means verified" was implemented as verify on every call,
and every question the app asks the engine goes through one, so a single launch spawned
`prudence --version` ten times: twice for the Settings screen, twice for the readiness ask
from each of the two pages, and once for each located path. The answer is now kept against
the file's own identity, which is its path, its length and its modification time.

- **Assumes:** an executable replaced under a running app changes at least one of its
  length and its modification time. A reinstall, an upgrade and a `uv tool install` all do.
- **When it breaks:** a file swapped for another of exactly the same length inside the
  same second of modification time would be handed an action on the old verdict. The
  property being kept is that a remembered path which has become something else is never
  handed an action, and that case is the one hole in it.
- **Removed when:** nothing. It is bounded by what the page can make the app ask; the
  alternative is a process per question and it was measured at ten per launch.

### The store's snapshot is invalidated only by the watcher

`store.rs`, `snapshot`. One read per change, shared by both pages. The invalidation is
`watcher.rs`'s announcement and there is no other.

- **Assumes:** nothing changes the store without the watcher seeing it. The app already
  rests on that entirely: no page redraws except on that announcement.
- **When it breaks:** a change the watcher misses leaves every page on the old figures
  until it sees the next one, which is what happened before this too.
- **Removed when:** it does not need to be. A second invalidation path (after a run, say)
  would hide a watcher defect rather than fix one.

### An open run record is "interrupted" when the shell sees no run

`store/runs.js`, `statusNote`, and `ui/engine-runs.js`, `entry`. The engine writes a
record when a command starts and completes it when it ends, so a record with `ended_at`
null is either running or was cut off, and the app tells the two apart by what
`activity.rs` knows: a run of its own, or an ingest or rebuild holding `ingest.lock`.

- **Assumes:** the engine completes the record before it releases the lock, and every
  command whose record is still open while it runs is one the shell can see.
- **When it breaks:** a `review` or an `init` started in a terminal holds no lock, so while
  it runs its row in Recent runs says "interrupted" (the status row is unaffected: it reads
  ingests only). And an engine that completes the record a moment after releasing the lock
  shows "Last ingest was interrupted" until the store's next announcement re-reads the log,
  which the end of that same ingest makes within a second.
- **Removed when:** the engine writes its process id into the open record, so the shell
  can ask whether that process is still alive instead of inferring it.

### The status row looks for the last ingest in the last fifty records

`ui/activity.js`, `LOOKBACK`. Reviews, scans and the Repositories screen's level changes
write records too, so the newest record is often not an ingest.

- **Assumes:** fewer than fifty non-ingest records land between two ingests.
- **When it breaks:** the row says nothing about an ingest's warnings that the Engine tab
  would still list.
- **Removed when:** the shell answers "the last record of this command" itself, which is a
  second question for `runlog.rs` and not needed at today's volumes.

### Only the live run log is read, never its rotated files

`runlog.rs`, `read`. The engine rotates `runs.jsonl` by size.

- **Assumes:** the live file holds at least the last ten runs.
- **When it breaks:** straight after a rotation, Recent runs lists fewer than ten runs and
  the status row may find no ingest to speak about.
- **Removed when:** the engine's rotation keeps a floor of records in the live file, or the
  reader walks on into `runs.jsonl.1`.

### The diagnosis's folder is the one that was not there before

`runlog.rs`, `made`. `prudence diagnose` writes `<data dir>/diagnose/<timestamp>/`, and the
shell lists that directory before and after the run rather than reading the path out of
what the command printed, whose wording is the engine's to change.

- **Assumes:** nothing else writes a bundle while this one runs.
- **When it breaks:** two diagnoses at once (one from a terminal) show the newer of the two
  folders, which is still a complete bundle.
- **Removed when:** `prudence diagnose --json` prints the folder, and the shell decodes it.

### The watcher's log line carries the revision the pages are replacing

`watcher.rs`. The store is read when a page asks, after the announcement, so at the moment
the watcher announces there is no new revision yet. Its line says which revision the pages
held, and the `store read` line that follows says the one they got.

- **Assumes:** a reader of `app.log` pairs the two lines, which are adjacent in practice.
- **Removed when:** the watcher reads the snapshot itself before announcing, which would
  also let it skip an announcement whose revision did not move.

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
that app was retired from master (commit `7fd8f60`; its history stays).

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
bucket and purpose names. **Two things deliberately do not go through the locale** and are marked
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
| The panel's range choice | Plain labels on the range block's caption row, right-aligned: Today, 7 days, 30 days, 90 days, the app's own quiet `.btn.plain`, the chosen one in ink and the rest quiet. One click swaps the sentence, the bar and the numbers under it for the day count it names; the row itself is drawn whole at first paint, so switching moves nothing else. Remembered in the app's UI state and restored on the next open, on the same rule as the window's section | `src/ui/panel.js`, `store/payload.js`, `src-tauri/src/ui_state.rs` |
| The window shell | The system's titlebar overlaid as the toolbar, a sidebar with five entries and the status row at its foot, the heading and the screen's pickers on one fixed row, one screen at a time | `src/ui/window.js`, `src/window.css` |
| The toolbar's actions | `Review now` (flat) and `Ingest now` (accent), the panel's words, on the right of the titlebar row. While any run goes, wherever it was started, the run takes their place in its compact form; then how it ended for four seconds; then the buttons. **One declared box** (248 by 26 pt) in every state, so nothing beside it moves and nothing under it grows | `src/ui/activity.js`, `ui/activity.css` |
| The status row | The foot of the sidebar card: "Last ingest 13h ago" (the narrow relative form, the full stamp on the pointer, said again every minute), the same run in its compact form without its count, or the same outcome line. Reserved height (34 pt, two caption lines), never grows. Idle, what the engine's run log says about the **last ingest** is a quiet caption on a second line under the age, "3 warnings" (warnings plus failed checks, `store/runs.js`), or replaces the age, "Last ingest was interrupted" (wrapping onto the second line, since in English it is wider than the row), when that record never ended and no run is going. A second line and not "· 3 warnings" after the age: the row has 148 pt of text and "Last ingest 13h ago" takes about 118 of them, so the first build showed "Last ing..." and the count. The caption is a chromeless button in the idle line's ink, the accent under the pointer, and opens Settings on the Engine tab. An engine with no run log adds nothing and says nothing | same files, `store/runs.js` |
| Recent runs | The Engine tab's card of the engine's last ten runs, newest first, from `logs/runs.jsonl`: a hairline-separated `details` per run whose line is the time, the command (monospaced, the one value that yields), and how long it took or "interrupted" in ink, with the files parsed and skipped and the warning and failed-check counts under it. Open, it shows every warning (kind, count, sample as the engine wrote it), every failed check with the numbers it compared, and the error. Which rows are open survives a rebuild. Not drawn at all when the engine keeps no run log | `src/ui/engine-runs.js`, `ui/engine-runs.css`, `store/runs.js`, `src-tauri/src/runlog.rs` |
| Diagnosis | The card under it: one plain label, Diagnose, that runs `prudence diagnose` through the shell, then the folder it wrote with a Reveal; a failure in the engine's own words; and where the logs are, with its own Reveal. The answer outlives a rebuild of the screen, because the diagnosis itself moves the store's files | same files |
| The run report | A card at the foot of the window for the two outcomes a line cannot carry: a failure in the engine's own words, and a review the engine declined, with Write anyway. Content, so opaque, and it waits for the reader. Only runs this window started report here | same files |
| `miniStack` | One row of a stacked bar: the composition of a whole, in a single line. It takes its parts in the caller's fixed order with their colours (the purposes on the Review screen, the buckets on the panel), and a `total` when the whole holds something none of the parts names | `src/design/charts.js` |
| The backdrop | A plain full-screen window of the app's own, for screenshots only | `src/backdrop.html` |
| The engine block | Configuration: where `prudence` is and whether it was found or chosen, with the picker, its version against the store's, and the Install or Update button with uv's own output under it. Install and Update are disabled while any run goes | `src/ui/engine-section.js`, `ui/engine-section.css` |
| The tab strip | The Settings screen's five tabs. Control layer, so it takes the same frost and the same selected pill the segmented control takes | `src/ui/settings.css`, `design/tokens.css` |
| A setting row | A name, a segmented control, and one sentence under both. General and Model use it for fixed choices; Sources uses text fields for named homes | `src/ui/settings.js`, `ui/settings.css` |
| Source locations | The Settings Sources tab lists the engine's named homes, shows capture state and missing paths, and offers pause, resume, edit and typed add. A change redraws from the CLI answer and refreshes the repository scan | `src/ui/sources.js`, `ui/sources.css` |
| `shareBars` | Shares, as horizontal bars on one axis: what each row is, how far it reaches, and the figure printed beside it. Drawn by the Review screen and the Observations screen, which had one each until this sheet | `src/design/charts.js` |
| `runProgress` | What a run is doing: the step in the reader's language, the engine's two figures in monospaced digits, and a determinate bar that fills for the step it is on. Drawn on the panel, in the toolbar and the status row (`is-compact`, no step line), and in the batch bar | `src/design/components.js` |
| `segmented`, `subhead` | The one row of choices every setting and every repository's level is, and the caption-and-note heading of a block inside a card. Moved out of `ui/settings.js` when the Repositories screen wanted both | `src/design/components.js`, `design/components.css` |
| The repositories list | The Repositories screen: which repositories the engine found and which of them it records, split into the two, one row each with the name and the end of its path, sessions and source, first and last day, tokens by bucket as one bar, alive at thirty days over its lines, and the level. Content, so it is opaque. **Every column is declared**: `table-layout: fixed` and a `<colgroup>` adding to 504 pt, which fits the window's narrowest; the path and a long name are the only values allowed an ellipsis. A recorded row is the project picker: clicking it sets the window's filter, a quiet fill marks it, and clicking again clears it | `src/ui/repositories.js`, `ui/repositories.css`, `store/repositories.js` |
| Recent sessions | A disclosure below the repository list, drawn from `app_session_list`. Source home and model menus filter its rows only; they do not change the repository figures or saved review scope | `src/ui/repository-sessions.js`, `ui/repository-sessions.css` |
| The batch bar | What to do with the ticked rows: how many they are, the three levels, and what the engine refused. At the foot of the card, sticky, and only while something is ticked. **Control layer**, so it takes the frost while the list above it stays opaque | same file |
| `disclosure` | A drawer with the line that says what is in it. The card builds one out of its `method` string; a caller with more to fold away builds its own, and `deferred` is content built the first time it is opened | `src/design/components.js` |
| The figure strip | The Overview's three figures on one row, each carrying its own unit, with the words the engine lends the screen glossed in the strip's own drawer. It was three cards taking a full row above charts starved of width | `src/ui/overview.js`, `ui/overview.css` |
| The summary line | One sentence at the top of a screen saying what everything under it is over: the scope, the window, and the figures. Composed per language, and it replaces the head's grey subtitle rather than joining it. While an ingest goes anywhere, one key wraps it with "Ingesting; the figures will update when it finishes." | same file, and `design/components.css` for `.screen-summary`, which the Repositories screen opens with too |
| The heat strip | One cell per local day, seven rows Monday first, **with its axis**: the weekday down the left and the month under the first column it starts in. The geometry is below | `src/design/charts.js` |

**The engine block is placed, not owned, by a screen.** The Settings screen puts it where
it goes and the block says what is in it, so the two can be written at the same time. Its
port is filled by `ui/wiring.js`, like every other piece that reaches the shell, and
`ui/review.js` exports a `REVIEW_NOW` seam for its readiness line on the same rule.

**What a run is doing is the shell's answer, not a page's.** A run can start in the
toolbar, the panel, the timer or a terminal, so `src-tauri/src/activity.rs` keeps one
answer (is a run going, which, started outside or not, its last progress line, how the last
one ended), announces every change over `engine-activity`, and answers `engine_activity`
for a window drawn mid-run. The engine tells `activity::run` it has started only once it
holds its one-run-at-a-time flag, so a click turned away as busy never overwrites the
running one's record. The toolbar and the status row draw from that answer and nothing
else; the report card is the only piece that waits on a button's own promise, because the
two outcomes it carries need the reader. An ingest starting or ending redraws the current
screen, because `ingesting` is part of what a screen is handed; a progress line redraws
only the two places that show it.

**The report is on the page, not in a screen.** A run outlives the screen it was started
on: the Review screen is rebuilt whenever the store changes, and the store changing is
exactly what a successful run causes. So it is appended to the body once, by the wiring.

**There is one chart.** The mockups' module had seven builders and 598 lines; six drew
screens that do not exist yet and none had been read to a product standard. They are not
in the app. `docs/design/mockups/charts.js` keeps them as the visual reference, and the
batch that builds each screen writes that screen's chart against the rules at the top of
`design/charts.js`.

**A chart a second screen wants moves whole.** `shareBars` was written twice, once out of
`<div>`s on the Review screen and once out of SVG on the Observations screen, with two
class families and two readings of what a null value means. Both files' own comments said
it should move to `design/charts.js` when a second screen wanted one; it has. A screen may
still draw something only it has, and the moment a second screen wants that too, it moves
rather than being copied.

## What the window remembers

`src-tauri/src/ui_state.rs`, one small JSON file in the app's own configuration directory.
Not beside the store: nothing this app remembers is the engine's business, and the
engine's directory is somewhere an agent may be pointing at a copy.

Six things: the window's frame, the section it was on, where the user said `prudence` is,
and the three the General tab sets (the language, the appearance, and how often the shell
runs an ingest on its own). Open at login is **not** here, for the reason registered under
Known compromises: the system owns it.

**The appearance is two halves and both are needed.** `window.set_theme` changes the
titlebar, the scrollbars and the native material; the page's own `data-theme` changes
everything inside them. Setting only the theme leaves a light page in a dark frame, and
setting only `data-theme` leaves a dark page in a light frame. `system` is
`set_theme(None)` plus the media query, and the page's listener reads the setting rather
than the query alone, so a window pinned to light does not move at sunset.

**A remembered value this build no longer understands is ignored rather than forced**, and
a frame below this build's own floor or carrying a non-finite number is dropped rather
than clamped, because a window in the wrong place is worse than a window in the default
place. `PRUDENCE_UI_MEMORY=off` starts with nothing remembered and writes nothing, which
is what every screenshot run uses.

## The keyboard

| Key | Does |
|---|---|
| Cmd-1 / 2 / 3 / 4 / 5 | Overview, Repositories, Review, Observations, Settings: the route table's order, which the shell's own list of sections (`ui_state.rs`) is held to by a test |
| Cmd-, | Settings. It opens the screen, not a particular tab: the screen remembers which one was last open |
| Cmd-R | Goes to the Review screen. Review now is the toolbar's; the shortcut still only navigates |
| Esc | Closes the panel |
