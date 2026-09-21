# Prudence.app

The native macOS menu bar app. It reads the same database `prudence` writes, shows the week at
a glance, and asks the CLI to do anything that changes the record.

A dropdown for today's numbers, and a window for the rest: charts of where the tokens went and
what became of the work, the latest written review, and the observations behind both.

## Build, run, test, render

```sh
cd apps/mac
./Scripts/bootstrap.sh                 # installs XcodeGen if needed, generates Prudence.xcodeproj
swift test --package-path PrudenceKit  # the fast loop: seconds, no Xcode project

xcodebuild -project Prudence.xcodeproj -scheme Prudence \
  -configuration Debug -derivedDataPath build/dd CODE_SIGNING_ALLOWED=NO build

./Scripts/shots.sh                     # the thirty-six PNGs listed under "Screenshots" below
swift Scripts/make_icons.swift         # re-render the icon set from assets/brand
```

`-derivedDataPath build/dd` keeps the output inside `apps/mac/` instead of Xcode's shared
DerivedData, so the built app is always at `build/dd/Build/Products/Debug/Prudence.app`. Run it
against your real store by launching it normally:

```sh
open -n build/dd/Build/Products/Debug/Prudence.app
```

Or against a copy, which is what an agent must always do:

```sh
mkdir -p /tmp/prudence-copy
sqlite3 "$HOME/Library/Application Support/prudence/prudence.db" \
  ".backup '/tmp/prudence-copy/prudence.db'"
cp "$HOME/Library/Application Support/prudence/config.toml" /tmp/prudence-copy/
PRUDENCE_DATA_DIR=/tmp/prudence-copy PRUDENCE_CONFIG_DIR=/tmp/prudence-copy \
  build/dd/Build/Products/Debug/Prudence.app/Contents/MacOS/Prudence
```

The app honours the same environment variables `src/prudence/paths.py` honours, and passes them
through to every CLI subprocess it starts, so an app pointed at a copy can never ingest into
the real store. `PRUDENCE_OPEN_WINDOW=1` opens the main window at launch, which is how an agent
with no way to click a menu bar item gets to see one. Quit from the dropdown, or kill the one
process you started; never `pkill -f Prudence.app`, which would also take down a build somebody
else is running.

`Prudence.xcodeproj`, `build/`, `DerivedData/` and `shots/` are generated and gitignored. Never
open Xcode's UI to add a file: add it to `App/` or `PrudenceKit/Sources/`, then run
`./Scripts/bootstrap.sh` again. A new file under `App/` that a screen renders also goes in the
`VIEWS` list in `Scripts/shots.sh`, or it is built but never photographed.

## The fixture

The Swift tests and the render harness read
`PrudenceKit/Tests/PrudenceKitTests/Fixtures/store.db`, a store the engine itself wrote and
nothing else: `tests/conftest.py`'s synthetic machine, ingested, given the few rows that small
a scenario cannot produce on its own, and `VACUUM INTO`'d into the test bundle. Regenerate it
from the repository root whenever `store/app_views.APP_VIEWS` or `meta.APP_CONTRACT_VERSION`
changes, and commit the `.db` with the Swift change that reads the new columns:

```sh
MAC_FIXTURE_TARGET=apps/mac/PrudenceKit/Tests/PrudenceKitTests/Fixtures/store.db \
    uv run pytest tests/mac_fixture.py -q
```

What is in it is `tests/mac_fixture.py`'s business, not this app's. **No Swift test hard-codes
a number out of it**: each one computes what it expects with a plain SQL query over the same
file (`Fixture.count` and friends in `Tests/PrudenceKitTests/StoreTests.swift`) and compares
that with what the code under test answered, so a regenerated store moves the tests with it
instead of breaking them. A test the fixture is too thin to mean anything for is gated with
`.enabled(if:)` and skips with a sentence naming what `mac_fixture.py` would have to record.

`Fixtures/review-sections.json` is one real `review.sections` payload, copied off the founder's
own store, which the decoding tests read. It holds numbers, labels and the notes that explain
them, and no message text of any kind. It is the whole payload, the way the `review` table
stores it; `app_review.sections` is `json_extract(..., '$.sections')` out of the same thing, so
`ReviewPayload.decode` takes either shape.

## Screenshots

`./Scripts/shots.sh` writes thirty-six PNGs: every screen in light and dark and in English and
Simplified Chinese, and the two surfaces that have a material in Standard and Glass as well.

| shot | size | materials | what it is |
| --- | --- | --- | --- |
| `menu-{light,dark}-{en,zh}[-glass]` | fitted | both | the dropdown, variant C with captions |
| `window-{light,dark}-{en,zh}[-glass]` | 900x600 | both | the whole window at the floor `MainWindowController` sets |
| `overview-{light,dark}-{en,zh}` | 1200x1500 | standard | Overview A: cards, stacked bars, lines, heat strip |
| `review-{light,dark}-{en,zh}` | 1200x2600 | standard | Review B: every chart with its table open under it |
| `observations-{light,dark}-{en,zh}` | 1200x1500 | standard | Observations C: paired bars, grouped by behaviour |
| `settings-{light,dark}-{en,zh}` | 620x470 | standard | Settings B, the General tab |
| `settings-data-{light,dark}-{en,zh}` | 620x470 | standard | Settings B, the Data tab |

The `-glass` pair is the popover and the window because those are the control and navigation
layer; the screens inside the window are content and are opaque under either material, so
photographing them twice would produce two identical files. The harness draws a soft wallpaper
behind everything, so a frosted surface has something to be frosted about; Standard covers it
completely, which is the honest Standard look.

The three screen shots are taller than a window because each of them now carries several
charts, and a shot cut off at the window's height would hide the ones a reviewer is being asked
about; `window` stays at the 900x600 floor, which is where the layout is under the most
pressure. The names have not changed since batch 1, so `.github/workflows/mac-ci.yml` needs no
edit.

`PRUDENCE_SHOTS_DUMP=1` also prints the Overview's three cards and every week's token totals on
standard output, for holding beside `prudence usage --last 60d` over the same store.

`PRUDENCE_SHOTS_REVIEW` is the payload the `review` shot draws, and `shots.sh` points it at
`Fixtures/review-sections.json`. `tests/mac_fixture.py` writes a review with two sections and
one purpose row — enough for the decoding tests, far too thin to photograph, since the donut
would have one slice and the comparison, the observations and the suggestions would not appear
at all. That JSON is one real payload copied off the founder's own store, which the decoding
tests already read; the row's own columns are still the fixture's, and the screen is the
shipping screen either way. Set the variable to an empty string to photograph the fixture's own
payload instead. A `mac_fixture.py` that wrote a five-section review would make it unnecessary.

## Design

[DESIGN.md](DESIGN.md) is the design system: the tokens with their values, the component set
and where each piece is used, the material rule, the localisation rule, the icon pipeline and
what batch 2 still owes. All of it lives in `PrudenceKit/Sources/PrudenceUI/`, so the app, the
render harness and `swift test` share one copy.

## Layout

```
apps/mac/
  project.yml          XcodeGen manifest; the only build settings file an agent edits
  App/                 SwiftUI views and AppKit glue. No decision logic.
    StatusItem, MenuContentView          the menu bar item and its dropdown
    MainWindow                           the window, its sidebar and the chrome every screen shares
    OverviewView, ReviewView,
    ObservationsView, SettingsView       one file per screen
  DESIGN.md            the design system: tokens, components, material, localisation, icons
  PrudenceKit/         the local Swift package: everything the app thinks with
    Sources/PrudenceStore/    GRDB, read-only, over the app_* views, with the contract check
    Sources/PrudenceEngine/   finds and runs the prudence CLI
    Sources/PrudenceModels/   view models and formatting
      Overview.swift               weekly buckets, outcome series, the three cards
      ReviewPayload.swift          the sections JSON as typed Swift
      ReviewCharts.swift           a stored review's sections, as the shapes the charts draw
      WindowModel.swift            what the window read, and the one thing it can do
    Sources/PrudenceUI/       the design system; see DESIGN.md
      Theme.swift                  every token, light and dark, plus the project colour scale
      Glass.swift                  glassEffect on macOS 26, NSVisualEffectView before it
      Components.swift, Controls.swift, MiniStack.swift, FlowLayout.swift
      Charts/                      the seven chart types, one file each:
                                   StackedBarsChart, DonutChart, PairedBarsChart,
                                   ShareWithCoverageBar, LinesWithGaps, HeatStrip, CompareCard
      Localization.swift, Fmt.swift   the String Catalog's keys, and Locale-aware numbers
      ObservationText.swift, ReviewText.swift   sentences composed per language
      Brand.swift                  the mark, from the package's copy of assets/brand
      Resources/Localizable.xcstrings   en and zh-Hans
  Render/              off-screen PNG harness; compiles the app's own view files
  Scripts/             bootstrap.sh, shots.sh, make_icons.swift
```

## The window

A `NavigationSplitView` with four entries, and one screen at a time. The window remembers its
size (`setFrameAutosaveName`) and will not go below 900x600. The Dock icon appears while it is
open and goes away when it closes (M3 plan, open question 1).

**Overview** (variant A: one column, cards first). Three cards, then three charts, for the
chosen project and range (8 weeks by default, or 90 days, or all). The cards are sessions in
range from `app_session_list`, active hours from `app_usage_by_purpose_day`, and commits in
range from `app_commits_by_day` with its fact and inferred split, which is the view that counts
a commit once. Then stacked bars, one per ISO week, of tokens by purpose, with a colour per
purpose fixed in a table so two screenshots a week apart are comparable: pointing at a bar
prints that week's totals and its breakdown under the chart, and **clicking one filters the
three cards to that week**, says so above them, and offers one button to put the range back.
Then, per project, the share still alive at 30 days and the share reworked later, with that
week's mean coverage as a pale wide line behind them. **A week whose 30-day mark has not
arrived is a gap, never a zero**: each project's line is cut into runs of measured weeks so
Swift Charts cannot join across the hole. Every share carries the number it is over. Last, a
heat strip of active hours, one cell per local day, seven rows.

**Review** (variant B: charts with their tables open under them). The newest stored review from
`app_review`, or any earlier one from the picker. The header carries the headline, both ranges,
the coverage stored on the row, and the day it was written in the reader's own language. Then
each section from the sections JSON: "what you did" as four figure cards, a donut of the tokens
by purpose and the purpose table under it; "what became of earlier work" as a share bar per
figure over its own pale coverage underlay, with the table under them; the observations as
paired bars with the sentence above and the coverage and method line below; the comparison as
one card per figure with the previous value, a neutral delta chip and two mini bars; the
suggestions as rows; and the model segment last under "What this means", with the model that
wrote it and the language it is in. Five section kinds are laid out by hand and **anything else
is drawn as the table it brought with it**, so a section the engine grows later appears here
rather than crashing the screen or being silently dropped. "Review now" runs
`prudence review --json`, with `--language` when this machine's engine takes it; a not-ready
answer shows the engine's own reason with a "Write anyway" button that adds `--force`.

**Observations** (variant C: grouped by behaviour). One card per behaviour fact, biggest gap
first, carrying the threshold that made the split and then one paired-bars row per outcome:
the two medians, **`n` on each bar**, the gap in points under them, and the coverage and method
line beside. Survival and rework of the same split share a card, because they are two readings
of the same two groups of sessions. Under "All projects" only the pooled rows appear, labelled
"across your projects": a row about one project under a heading that says every project would
read as a statement about all of them.

**Settings.** The same screen the menu bar opens, hosted in the sidebar.

Every screen has an empty state that says what it looked at, and every screen behind a store
that will not open shows one contract-mismatch page instead, carrying the sentence
`StoreError` writes, which already names both versions and says which side to update.

## Four conventions

**1. `NSStatusItem`, not `MenuBarExtra`.** SwiftUI's menu bar scene still cannot close its own
popup from a button inside it (FB11984872, open since February 2023), cannot tell you the user
opened it, and does not hand over the status item or the popup's window. A dropdown of today's
numbers that cannot know when it was opened shows stale numbers. Decaf, whose shape this app
otherwise copies, ships a whole file whose only job is to hijack what `MenuBarExtra` created.
The reasoning is written out at the top of `App/StatusItem.swift`; read it before reaching for
the shorter API. The same goes for the windows: they are hand-built `NSWindow` plus
`NSHostingController`, not SwiftUI `Window` or `Settings` scenes.

**2. The app owns no numbers.** Every figure on a screen comes from an `app_*` view (M3 rule 8,
ARCHITECTURE rule 14). Swift never joins base tables and never computes an outcome, a share of
survival or a token total. The line is narrow and deliberate: a screen may **sum** view columns
into a bucket and take the **ratio of two columns of the same row**, and nothing else. So the
weekly bars are sums of `total_tokens`, the survival line is `alive_30d / measured_30d` and the
rework line is `reworked / lines`; a median, a threshold or an attribution would be a new view
in `src/prudence/store/app_views.py`, never a function in Swift.

**3. Design decisions live in `PrudenceUI`, not in a screen.** A colour, a spacing, a card
shape or a user-facing string written inline in `App/` is a decision two screens will
eventually disagree about. `DESIGN.md` says what exists; a screen composes it. The three rules
that outrank layout are there too: glass never touches content, colour never means good or
bad, and a composed sentence is composed per language rather than translated.

**4. The contract is checked before anything is rendered.** `Store.init` reads
`meta.app_contract_version` and refuses anything but `2`, with an error carrying both versions
and a sentence saying which side to update. No screen ever renders half a schema it does not
understand.

## The contract, and what moved to 2

Contract 2 answers all three requests contract 1 left open, and adds the one the review screen
needed:

1. **`app_session_list.edits`.** The dropdown's "today" line can say edits again without the
   app counting the `edit` table itself, which is exactly what it may not do.
2. **`app_commits_by_day`.** A commit counted once per local day, at its best confidence.
   Summing `app_session_list` over a day double counts a commit credited to two sessions, so
   the dropdown's old figure was an upper bound; this view is the real one, and both the
   dropdown and the Overview card read it.
3. **`app_observation.sentence`** (and `observation_id`). The prose the CLI prints, stored.
   `PrudenceModels/ObservationSentence.swift` used to restate the phrase table from
   `store/observations.SPLITS` — the one piece of Python this app repeated — and is deleted.
4. **`app_review`.** The stored reviews as a view: the ranges, the scope, the headline, the
   coverage, the model segment, and `sections` and `numbers` as the JSON `reviews/build.py`
   wrote. The app used to read the raw `review` table for a headline and nothing else; it now
   reads this and nothing else.

`PrudenceStore/Contract.swift` is the compiled form of that list, and a test asserts every
view still answers with exactly those columns in that order, so a Python change that forgets to
bump the version fails in `swift test` rather than in front of the user.

**Open against contract 2:** the Overview has no figure it wanted and could not have. The one
thing the app still assembles itself is an observation's caveat line, `(coverage: 90%, method:
4 fact, 3 inferred)`, which is three columns of the same row in a fixed shape rather than a
restated rule; a `caveat` column beside `sentence` would remove even that. Batch 2's four
requests, all of them about a stored review rather than about a view, are listed under
"Contract requests" in [DESIGN.md](DESIGN.md): `with_n` and `without_n` on a review's
observation numbers, a `value` on its `compared.*` numbers, a `segment_language` column, and a
structured threshold beside `app_observation.threshold_text`.

## Bundle identifier

`dev.prudence.app` is a placeholder. The real identifier is decided with the Apple Developer
Program account (M3 plan, open question 4); the Developer ID name appears in Gatekeeper
dialogs. Changing it is one line in `project.yml` and nothing in the code reads it.
