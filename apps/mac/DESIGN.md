# The app's design system

What every screen of Prudence.app is built from, and the four rules that keep it one app
rather than six. Derived from the M4 mockups (`docs/design/mockups/NOTES.md`) and the
prototype record the founder settled on; where this document and a screen disagree, the screen
is wrong.

Everything below lives in `PrudenceKit/Sources/PrudenceUI/`, a target of its own so that the
app, the render harness and `swift test` all reach the same tokens, the same components and
the same String Catalog. The app target holds layout and AppKit glue and nothing else.

## The four rules

1. **Liquid Glass is the control and navigation layer, never the content layer.** The popover,
   the sidebar, the toolbar strip and the buttons are frosted. Cards, tables, charts and chips
   are opaque. A figure read against a moving backdrop is a figure the reader cannot check,
   and principle 3 is about figures the reader can check.
2. **Colour never means good or bad.** There is no green-for-up and no red-for-down anywhere.
   More sessions is not better and less rework is not a score, so a delta chip's ink is a
   constant (`DeltaChip.tint`) and a test asserts it.
3. **A composed sentence is composed in each language, never translated.** An observation is
   seven columns in a shape; `ObservationText` builds it from those columns in the language in
   force. The engine's English sentence stays on the row as the thing to check against.
4. **Every figure is `.monospacedDigit()`.** `Type.figure(_:weight:)` is the only way a number
   reaches a screen, so a value that changes does not reflow the row it sits in.

## Tokens

`PrudenceUI/Theme.swift`. Every value is the one in `docs/design/mockups/tokens.css`, and
`TokenTests.thePaletteDrawsTheValuesTheDocumentPrints` resolves the `Color`s and compares them
with the table below, so a token table nobody checks cannot drift from what is drawn.

### Purpose palette

One colour per purpose, identical in every chart on every screen, in this fixed stacking and
legend order. Keys are the engine's own labels from `facts/purpose.py`; `unknown` is shown as
"other". A key this build has never heard of is drawn in the grey `unknown` uses, never
dropped.

| Purpose | Light | Dark |
|---|---|---|
| `development` | `#007AFF` | `#0A84FF` |
| `research` | `#30B0C7` | `#40C8E0` |
| `debugging` | `#FF9500` | `#FF9F0A` |
| `conversation` | `#AF52DE` | `#BF5AF2` |
| `mixed` | `#5856D6` | `#7D7AFF` |
| `unknown` (other) | `#8E8E93` | `#98989D` |

The order is fixed and never sorted by size: a chart whose colours move is a chart two
screenshots taken a week apart cannot be compared across.

### Outcome colours

`Outcome.alive` `#0A7D45` / `#3AC07A`, `Outcome.rework` `#8A5A00` / `#E0A33A`. Survival and
rework are two readings of the same lines, so they share a warm-cool pair everywhere and
differ by line style in a time chart. They are not "good" and "bad".

### The project colour scale

`ProjectPalette`, for the one chart that draws more than one project at a time. A project's
colour is its place in the **sorted** list of project names, so it does not move when the range
picker changes which projects have a row and two screenshots of different ranges agree about
which line is which.

| Index | Light | Dark |
|---|---|---|
| 0 | `#3E6AE1` | `#6E9BFF` |
| 1 | `#A2845E` | `#C8A579` |
| 2 | `#B3358C` | `#E36FC4` |
| 3 | `#00786F` | `#2FB3A6` |
| 4 | `#7A5AF8` | `#A68BFF` |
| 5 | `#6E6E73` | `#98989D` |

None of the six is a purpose colour or one of the outcome pair, and a test asserts it: a
project drawn in the colour of `development` would read as a purpose in a window where every
other chart is coloured by purpose, and red or green would read as a verdict on a project.
Past the sixth the colours repeat, which is honest about a chart that has stopped being one
anybody can read. Batch 1 indexed into a slice of the purpose palette as a stand-in; this
replaced it.

## Charts

`PrudenceUI/Charts/`, one file per data shape in the M4 plan's table. Every one of them is
Swift Charts, reads **one** view or one stored row, carries an `.accessibilityLabel` with the
same numbers the picture has, prints every number through `Type.figure` (`.monospacedDigit()`),
and keeps every share next to the denominator it is over.

| Chart | Data shape | Reads | Marks | Interaction | Accessibility |
|---|---|---|---|---|---|
| `StackedBarsChart` | composition of a whole, over time | `app_usage_by_purpose_day`, summed into ISO weeks by `WeeklyUsageModel` | `BarMark` stacked, fixed purpose order and palette, width capped at 46 pt | hover prints the week's totals and its per-purpose breakdown under the chart; click selects that week and click again clears it | every bar with its total and its slices |
| `DonutChart` | composition of a whole, one period | one review's `did` section (`did.tokens.<purpose>`) | `SectorMark`, inner radius 0.62, the count in the middle | none | the middle figure, then every slice's share and value |
| `PairedBarsChart` | two groups compared — **the core Prudence chart** | one `app_observation` row, or one review's `observation.<key>.with`/`.without` | two horizontal `BarMark`s over a sunken track, scale stepped to 25/50/75/100 % | none | both labels, both medians, both `n`, and the gap |
| `ShareWithCoverageBar` | a share with its coverage | one row of a review's `became` section | two `BarMark`s in one horizontal chart, the coverage 24 pt and pale underneath, the share 14 pt over it | none | the label, the share with its denominator, and the coverage |
| `LinesWithGaps` | over time, with holes | `app_outcomes_by_week` through `OutcomeChartModel` | `LineMark` plus `PointMark`, one `series:` per run so a hole cannot be joined across; a 6 pt translucent line for coverage | hover prints every project's shares at that week with the lines behind them | every measured point, with its denominator |
| `HeatStrip` | where the hours went | `app_usage_by_purpose_day.active_minutes`, bucketed by `ActiveHoursHeat` | `RectangleMark`, seven rows Monday first, one cell per day, single-hue scale `Surface.sunken` → `Ink.accent` | none | every day that measured anything, with its hours |
| `CompareCard` | this period against the last | one row of a review's `compared` section | `StatCard` shape, previous value, neutral `DeltaChip`, two vertical `BarMark`s | none | the figure, the previous figure and the change |

Three rules hold across all seven:

- **`n` and the denominator are printed, never hovered.** A screenshot has no pointer, and the
  founder judges screenshots.
- **A hole is a hole.** `LinesWithGaps` takes an *optional* value and cuts the line at every
  nil. Swift Charts has no `Optional: Plottable` conformance (checked against the macOS 27 SDK,
  not against memory), so the break is made with one `series:` value per run, which Charts will
  not join across.
- **Colour is identity, never judgement.** Purpose, project and outcome are the three scales; a
  delta chip's ink is a constant and a test pins it.

### What the app parses and why

`CompareCard.numeric` reads the leading figure out of a cell the engine printed (`4.3`,
`71% (1180)`, `43k`) to set the length of its two mini bars. It is the one place the app looks
inside a stored string, and it is a rendering rather than a computation: the figure on the card
is still the engine's own text, and a cell that will not parse gets **no** bars rather than
bars of zero. It exists because `reviews/build._compared` writes `Number(key, label, text)`
with no `value`; the moment it writes one, `ReviewChartTests.theComparisonIsFourStringsAndNoStoredValue`
fails and says so.

### Surfaces and ink

| Token | Light | Dark |
|---|---|---|
| `Surface.canvas` | `#F2F2F4` | `#1C1C1E` |
| `Surface.plain` | `#FFFFFF` | `#2C2C2E` |
| `Surface.secondary` | `#F7F7F9` | `#242426` |
| `Surface.sunken` (chart tracks, chips) | `#EBEBEF` | `#171719` |
| `Surface.sidebar` | `#F6F6F8` | `#232325` |
| `Surface.control` / `.controlHover` / `.controlPressed` (the secondary button's flat fill) | `rgba(0,0,0,0.05)` / `0.08` / `0.03` | `rgba(255,255,255,0.08)` / `0.12` / `0.05` |
| `Surface.separator` | `rgba(0,0,0,0.08)` | `rgba(255,255,255,0.10)` |
| `Surface.hairline` | `rgba(0,0,0,0.13)` | `rgba(255,255,255,0.16)` |
| `Surface.coverage` | `rgba(0,0,0,0.16)` | `rgba(255,255,255,0.24)` |
| `Ink.primary` / `.secondary` / `.tertiary` | `#1C1C1E` / `#636366` / `#8E8E93` | `#F2F2F7` / `#AEAEB2` / `#8E8E93` |
| `Ink.accent` | `#007AFF` | `#0A84FF` |
| `Ink.brand` (the mark) | `#111111` | `#FFFFFF` |

Elevation is a 0.5 pt hairline ring, not a shadow. Only the popover and the window frame cast
a real one, at the system's own weight.

Every token is an `NSColor(name:dynamicProvider:)`, so it follows the appearance of the *view*
it is drawn in rather than of the process. A popover hanging over a dark wallpaper gets the
right ink without anybody checking `colorScheme`.

### Spacing, type, radii, motion

- **`Space`**, base 4: 4, 8, 12, 16, 20, 24, 32, 40. Card padding 20, card gap 16, section gap
  24. The popover is `tokens.css`'s own: 360 pt wide, 16 pt of side padding, 12 pt between
  blocks, one column. Batch 1 read those as 14 and 10 from memory; batch 3 put the file's
  numbers back when the popover was rebuilt as variant C, and dropped the caption column when
  the founder said again that C is content in the centre, not captions left and values right.
- **`Type`**, SF Pro through the system font (`PingFang SC` picked up for Chinese): 11
  (caption 2), 12 (caption), 13 (footnote, the working size), 15 (body), 17 (headline), 20
  (title 3), 24 (title 2), 28 (title 1). `Type.figure(size, weight:)` for every number.
- **`Radius`**: control 6, card 10, panel and popover 12, chip 999. Glass takes one step
  larger: `glassControl` 8, `glassPanel` 16.
- **`Motion`**: 150 / 200 / 240 ms on `cubic-bezier(0.22, 0.61, 0.36, 1)`. Hover, selection and
  state changes only. Nothing animates on load.

## Components

`PrudenceUI/Components.swift`, `Controls.swift`, `MiniStack.swift`, `FlowLayout.swift`.

| Component | What it is | Where it is used |
|---|---|---|
| `Card` | The one card shape: opaque fill, hairline ring, no shadow | every screen; the base of `Panel`, `StatCard`, `ObservationRow` |
| `Panel` | A heading, an optional note, and content | Overview's two charts, every review section |
| `StatBlock` | A caption on its own line, the content full width under it | the popover's five blocks |
| `StatCard` | A caption, a figure, a detail | Overview's three cards, Review's figure cards |
| `CoverageChip` | The coverage and method line, as a capsule | the popover's observation, Observations |
| `DeltaChip` | A neutral difference. **Never coloured by sign** | Observations' gap, Review's change column |
| `MethodLine` | How a figure was established, smallest type on the screen | Observations, Settings' store line |
| `EmptyState` | Nothing to draw, and why | every screen |
| `ContractMismatchState` | The store said no, in `StoreError`'s own words | the window, behind every screen |
| `MiniStack` | A one-row stacked bar, Swift Charts, 8 pt | the popover's week line |
| `Charts/` | The seven chart types; see **Charts** above | Overview, Review, Observations |
| `PurposeLegend` | Swatch and label per purpose, in the fixed order, wrapping | the popover, Overview, the stacked bars |
| `FlowLayout` | A row that wraps | `PurposeLegend`, and anything else that lines chips up |
| `ControlStrip` | A frosted cluster of controls | the window's toolbar, Settings' tabs, the popover's footer |

### Controls

**Exactly three button styles, and no fourth.** `PrudenceButtonStyle` in three emphases is the
whole of the custom control drawing. All three are the same 8 pt rounded rect, the same 28 pt
height and the same semibold 13 pt label, and none of them is beveled, gradient-filled or
shadowed:

| Style | Fill | Edge | Label | Where |
|---|---|---|---|---|
| `.prudencePrimary` | the accent at 92 % behind the same frost | 0.5 pt `Surface.hairline` | white (`Ink.onAccent`) | Open Prudence, Review now in the Review header |
| `.prudence` | flat and quiet: `Surface.control` (black 5 % / white 8 %), or the frost the popover uses at control strength under Glass | 0.5 pt `Surface.separator` | `Ink.primary` | Review now, Ingest now, Choose..., Clear, Write anyway, Relaunch, Try again, Show all weeks |
| `.prudencePlain` | none | none | `Ink.secondary`, the accent under the pointer | Settings..., Quit, Dismiss |

`.prudenceWide` and `.prudencePrimaryWide` are the first two styles with `fills: true`, which
makes the **drawn shape** take the width it is offered. A `.frame(maxWidth: .infinity)` at the
call site widens the button and not the shape a `ButtonStyle` draws, which is why the popover's
rows each came out a different width before batch 3.

**States.** Hover raises the secondary fill by a few per cent (`Surface.controlHover`) and press
lowers it (`Surface.controlPressed`); under Glass and on the primary, where the fill is a
material or a slab, the same movement is a wash above it. A plain button has no fill to move, so
the pointer changes its ink to the accent and nothing else — no underline, because a link is not
a control. **Nothing moves** in any of the three.

#### One primary, after batch 3's two

The founder read the old prominent button as "a flat blue pill from an older era", so batch 3
built and photographed both readings of NOTES.md's one sentence about it. **The founder chose A**
— the accent at 92 % behind the frost, a white semibold label, 8 pt radius, one hairline edge,
no gradient — so B, the `Theme.primary` flag that selected between them and the
`-primaryA` / `-primaryB` shot suffixes are all gone; the popover's shots are
`menu-{light,dark}-{en,zh}[-glass].png` again.

The same round removed the **top inner highlight** from every style. It was a bevel by another
name, and it was what made the rest of the popover's controls read as retro beside the chosen
primary.

#### The button grid

The popover's actions sit on one grid, sharing the content column above them — the caption
column's left edge to the value column's right edge, which is what `Space.popoverPadding`
sets on both sides:

```
| Open Prudence                                        |   full width
| Review now              |  8 pt  | Ingest now        |   two equal cells
| Settings...                                     Quit |   one baseline, both outer edges
```

The window's Review header follows the same discipline: the stored-review pop-up and
`Review now` are both `ReviewPicker.controlHeight` (28 pt) and centred in one `ControlStrip`,
so they share a top and a bottom edge instead of sitting a couple of points out.

#### The bug behind all of this

On macOS 26, in the real app, the three `.prudence` buttons in the popover drew as **blank
frosted rectangles with no text**; `.prudencePrimary` and `.prudencePlain` kept their labels.

**Cause.** The frosted emphasis drew its material as
`.background(Color.clear.prudenceGlass(.control))` — a `glassEffect` on an *empty* view, handed
to the background slot. Inside a `GlassEffectContainer` the container gathers its descendants'
glass shapes and composites them in one pass of its own, and a shape whose only content is
`Color.clear` carries no label into that pass, so the merged glass landed over the text. The two
emphases that never call `glassEffect` were untouched, which is exactly the pattern the founder
photographed.

**Fix.** Apply the material to the **labelled** view, which is `glassEffect(_:in:)`'s documented
use: it puts the glass behind the view it is applied to. One call, the same on the
`NSVisualEffectView` path and the opaque one.

**Why nothing caught it.** The render harness draws through `cacheDisplay(in:to:)`, which has no
backdrop to sample and draws `glassEffect` as a no-op, so the labels were readable in every PNG.
The accessibility tree is no help either: `NSHostingView.accessibilityChildren()` is empty for a
SwiftUI view no assistive client has asked about, and `AXUIElementCreateApplication(getpid())`
answers with nothing, so there is no label in it to assert on before the fix or after it.

**The guard, and its honest limit.** `PrudenceUI/LabelAudit.swift` asks the property directly:
render the control twice, once with its label and once with nothing in it, and require the two
pictures to differ. A label covered by anything renders identically either way.
`UITests.ButtonLabelTests` runs it over every style × material × appearance in `swift test`,
and `Scripts/shots.sh` runs it at the end of every render.

**It does not reproduce this bug, and that was measured rather than assumed.** The broken code
was put back and the audit run against it three ways — off screen through `cacheDisplay`, on
screen in an ordinary window through the window server, and on screen in a real `NSPopover`
through the window server — and all three drew readable labels. The case needs the shipping
app, a menu bar and an active application. What the audit does catch, checked the same way, is
the class it belongs to: an opaque overlay over a label fails all three forms.

So **the check for anything about the material is a picture of the real app**:
`PRUDENCE_OPEN_POPOVER=1 PRUDENCE_FORCE_APPEARANCE=dark`, then `screencapture` (README). The
audit is the cheap net underneath that, not a replacement for it; `PRUDENCE_SHOTS_ONSCREEN=1`
makes it take its pictures through the window server, where glass is composited rather than
drawn as a no-op, which is more than the default can see and still less than the real app.

**Everything else shaped like a control is a system control and is not redrawn.** Segmented
controls are `Picker(.segmented)` (the range, the Settings tabs), menu pickers are
`Picker(.menu)` (the project, the stored review, the language), switches are `Toggle` with
`.toggleStyle(.switch)`, path rows are `TextField` plus a `Button` opening `NSOpenPanel`. On
macOS 26 those already draw themselves in the system material; asking for `.buttonStyle(.glass)`
on top would be a second material over the first.

## The material layer

`PrudenceUI/Glass.swift`. One modifier, `.prudenceGlass(_ surface:)`, and one cluster wrapper,
`.prudenceGlassCluster(spacing:)`.

| Path | API | Used when |
|---|---|---|
| macOS 26 and later | `View.glassEffect(.regular, in:)` and `GlassEffectContainer(spacing:content:)`, both from `SwiftUICore` and both `@available(macOS 26.0, *)` | `Theme.wantsTranslucency` and the OS is new enough |
| macOS 14 and 15 | `NSVisualEffectView` through `VisualEffectSurface`, with `.popover`, `.sidebar` and `.hudWindow`, `blendingMode = .behindWindow`, `state = .followsWindowActiveState` | the same, on an older OS |
| either, opaque | `Surface.plain` / `.sidebar` / `.secondary` with a hairline ring | `NSWorkspace.shared.accessibilityDisplayShouldReduceTransparency`, or `Theme.material == .standard` |

The API names were checked against the macOS 27 SDK that Xcode 27 ships, not against memory.

`Theme` is an environment value carrying the material and the reduced-transparency flag, read
once per window from `Theme.system`. Both paths consult the same flag, so the fallback cannot
drift from the thing it falls back from.

**The material goes behind the labelled view, never in a sibling layer.** That is the whole of
the batch 3 bug, and it is written out under *Controls* above.

**Glass**: the popover's content, the window's sidebar, the toolbar strip above each screen,
the Settings tab strip, and the default and primary buttons.
**Never glass**: cards, panels, tables, charts and their tracks, chips, stat values.

## Localisation

`PrudenceUI/Localization.swift`, `Fmt.swift`, `ObservationText.swift`, `ReviewText.swift`, and
`Resources/Localizable.xcstrings`.

- **One String Catalog**, English and Simplified Chinese, in the package's own resource bundle.
  SwiftPM compiles it into `en.lproj` and `zh-Hans.lproj`; the app, the tests and the render
  harness all read it through `Bundle.module`. The Chinese came from the mockups' `i18n.js`
  dictionary, which is the wording the founder already judged.
- **`Str` is a `CaseIterable` enum of keys.** `Str.menuToday.text` resolves it;
  `Str.menuStamped(a, b)` fills its `%n$@` placeholders; `Str.unitSessions.plural(3)` fills a
  plural entry with the count the rule chooses on. A test asserts every case resolves to
  something other than its own key in both languages, and that no two read the same.
- **Plurals are plural entries**, `%lld` with `one` and `other` in English and `other` alone in
  Chinese, so the popover says "1 edit" and "3 edits" rather than "1 edits".
- **Numbers and dates go through `Locale`** (`Fmt`). The two deliberate exceptions are marked
  in the source: the `%.0f%%` share and the ungrouped integer inside an observation sentence,
  which have to match the CLI character for character.
- **`Text(_ key: Str)` resolves eagerly**, through `Text(verbatim: key.text)`. SwiftUI resolves
  a `LocalizedStringResource` against the *environment's* locale at render time and ignores the
  one the resource carries; this app's authority is `Localization.locale`, which the render
  harness forces per shot.

### The language setting

System (default), English, 简体中文, in Settings > General. Choosing one writes it under
`language` **and** writes `AppleLanguages` into the app's own `UserDefaults`, which is the
macOS convention: Cocoa reads that key at launch, and System Settings > General > Language &
Region shows and can change the same per-app language. It therefore takes effect on the next
launch, and the screen says so and offers a Relaunch button. "System" *removes* the override
rather than freezing today's system language into it, so a user who later changes their Mac is
followed. `Info.plist` declares `CFBundleLocalizations` so the app appears in that list.

`Localization.override` forces a language on the current thread, for the render harness and the
tests. It is thread-local rather than global because the test suite runs in parallel and AppKit
lays out on the thread that asked it to.

### Composed sentences

`ObservationText` is the rule, and it is a restatement of `store/observations.py`:

- **Where.** Pooled (`repo_key = '*'`) is "Across your projects"; anything else is
  "In &lt;project&gt;", falling back to the repo key when the view has no name.
- **The with-side phrase.** `purpose:<label>` is "labelled &lt;label&gt;"; one of the twelve
  facts in `SPLITS` uses that split's own text; anything else is "with &lt;fact&gt;".
- **The without-side phrase.** "that did not" for a fact, "labelled otherwise" for a purpose,
  "without it" for an unknown fact.
- **The outcome clause.** `rework` reads "reworked X of their lines (median)"; every other
  outcome reads "still have X of their lines at head (median)", which is the else-branch of
  `_outcome_words` rather than a second special case.
- **The figures.** `%.0f%%` and plain ungrouped integers.
- English keeps the engine's raw purpose label (`labelled unknown`) where the interface
  elsewhere says "other", because the sentence has to match; Chinese, having no English to
  match, uses the reader's word.

`ObservationTextTests.englishEqualsTheEnginesOwnSentenceForEveryRow` compares the composer's
English with `app_observation.sentence` for every row of the fixture, word for word.

`ReviewText` does the same for a review's headline, without the word-for-word test: a headline
is a label for a document rather than a claim about the reader's work.

## The icon pipeline

`Scripts/make_icons.swift`, run with `swift Scripts/make_icons.swift` from `apps/mac`. One
vector file in, a set of bitmaps out; nothing draws the mark by hand.

```
assets/brand/logo.svg  ──►  1024 px master  ──►  AppIcon.appiconset, 16 to 512 at 1x and 2x
assets/brand/logo-glyph-template.svg  ──►  StatusGlyph.imageset, 16 / 32 / 48 px, template
assets/brand/*.svg  ──►  PrudenceKit/Sources/PrudenceUI/Resources/, for BrandMark at runtime
```

The master is the macOS icon grid: a 1024 px canvas with the shape inset 100 px on every side,
so the artwork lives in an 824 px square. The shape is a superellipse of exponent 5, which is
the continuous-corner family Apple's own outline and SwiftUI's `.continuous` belong to, and it
avoids the four corner seams a circular round rect shows at this size. The face is an all but
white gradient with a white wash over the upper half and one hairline edge; the mark sits on it
in `#111111` at 62 % of the canvas width, measured across the mark's own visible box
(`assets/brand/README.md`) rather than across the SVG frame, which carries empty margin.

`swift Scripts/make_icons.swift --check` compares the committed text files with freshly
rendered ones, for a CI job that wants to know whether the set is stale. PNG bytes are not
compared: a re-encode on a different macOS build differs in bytes without differing in pixels.

**`assets/brand/` is tracked, but outside the Swift package.** `BrandMark` loads the package's
own copies rather than the originals, because a package resource has to live inside the package;
the script refreshes those copies and CI checks them against the originals.

The product is named in exactly two places: `CFBundleDisplayName` in `App/Info.plist` and
`Product.name` in `PrudenceUI`. The name research is still open (M4 plan), so renaming is two
edits.

## The language the CLI writes in

The model segment and an `ask` answer are prose, and prose follows the reader. The app passes
`--language <code>` to every command that writes some, with the code taken straight from the
language setting: `system`, `en` or `zh-Hans`, the three values the picker offers and the three
`prudence review --language` accepts. `system` is passed on rather than resolved, because it is
the CLI's own word for "use `model.language` from the config": a user who has not chosen a
language in the app keeps whatever they configured for the terminal.

The flag is **probed, not assumed** (`PrudenceEngine.Engine.supportsLanguage`). The app ships
separately from the engine, so a user can have a `prudence` that predates the flag, and an
unknown option would turn "write me a review" into an error about a word they never typed.
`prudence review --help` is run once, its text is searched for `--language`, and the answer is
cached for the life of the process — so upgrading the CLI under a running app needs a relaunch
before the flag is used, which is the same thing an `AppleLanguages` change needs. A probe that
cannot run at all answers false, and the review is written in the engine's configured language.

## Screens

| Screen | Variant | State after batch 3 |
|---|---|---|
| Menu bar popover | **C with captions, one column** | rebuilt as C in batch 3, which had been shipping as A's five equal rows carrying C's content: 360 pt wide, every caption a line of its own above its block and the content full width under it (a caption column was tried and rejected: C is content in the centre, not titles left and values right), the day's counts as the one headline with the date under it, the week as a share line + `MiniStack` + totals + legend, the observation at body size, two quiet footer lines, and the action grid on `Surface.secondary` under a hairline. Batch 2's note that a headline read heavy is kept where it applies: **counts get the headline, "no session recorded today" stays a caption** |
| Settings | **B** | General and Data tabs, grouped boxes, the language setting; the store's location now in the reader's language |
| Overview | **A** | one column, cards first: the three totals, `StackedBarsChart` with hover and week selection, `LinesWithGaps` with coverage, `HeatStrip` |
| Review | **B** | charts with their tables open under them: `DonutChart` + the purpose table, `ShareWithCoverageBar` rows, `PairedBarsChart` rows, `CompareCard`s, the model segment last with its model and its language |
| Observations | **C** | grouped by behaviour: one card per fact, the threshold, one `PairedBarsChart` per outcome with `n` on each bar, the coverage and method line. Under "All projects", the pooled rows come first under "Across your projects" and then one heading per project, so the screen is never empty while project rows exist; a project picked in the picker still shows only its own |

## Contract requests: all four answered at contract 3

The app renders contract **2 and 3** from one code path (`PrudenceStore/Contract.swift`,
`Contract.supported`), because every one of contract 3's additions is optional and is used only
where it is present. A store at either is a store this app draws completely, so the app and the
engine can be upgraded in either order.

| Batch 2 asked for | Contract 3 stores | Where it shows |
|---|---|---|
| `with_n` / `without_n` on a review's observation numbers | `with_n`, `without_n` on `observation.*.with` and `.without` | Review's paired bars carry `n`, as Observations' do |
| a `value` on the `compared.*` numbers | `value` and `previous_value` | `CompareCard`'s twin bars are drawn from figures, not from a reading of the printed cell |
| `app_review.segment_language` | that column | the segment's language chip is a read |
| a structured threshold on `app_observation` | `threshold_value` and `threshold_op` (`">="`, `">"`, `"=="`, NULL) | `ObservationText.threshold` words the clause in the reader's language |

Each of the four keeps its old behaviour as the fallback, and a null stays a null:
`CompareCard.numeric` still reads a printed cell where the engine stored no value,
`ReviewText.segmentLanguage(stored:of:)` still reads the prose where there is no column,
`ObservationText.threshold` still prints `threshold_text` where there is no operator, and a
compared row whose page shows a dash gets **no** bars rather than bars of zero.

## Window memory and the keyboard

The window remembers where it was and what was on it.

- **Size and position**: `setFrameAutosaveName("PrudenceMainWindow")`, then
  `setFrameUsingName` **after the content view is installed** — the hosting controller's own
  sizing pass throws a restored frame away otherwise, which is why batch 1's autosave name
  alone never restored anything.
- **The sidebar item and the pickers**: `WindowModel.Memory`, in `UserDefaults` beside the
  settings (`window.section`, `window.project`, `window.range`, `window.review`). A remembered
  value this build no longer understands is ignored rather than forced. The render harness
  builds its models with `restoringMemory: false`, so a shot is of the state the caller asked
  for and not of whatever the machine last left behind.

| Key | Does |
|---|---|
| Cmd-1 / 2 / 3 / 4 | Overview, Review, Observations, Settings |
| Cmd-R | Review now |
| Cmd-, | Settings |
| Esc | closes the menu bar popover |

The four sidebar keys and the two actions are hidden zero-size `Button`s carrying
`.keyboardShortcut`, because this app has no SwiftUI `App` and therefore no `.commands` scene
to hang them on (README, convention 1). Esc belongs to the popover and lives in
`App/StatusItem.swift`.

### Closing the popover

`NSPopover.behavior = .transient` closes on the next event **its own window sees**, and an
`LSUIElement` app is `.accessory`, so the app is often not active when the dropdown opens and a
click in another application is delivered to that application and never to us. The dropdown
stayed up and the only way out was to click the status item again. Four things close it now:

- `NSApp.activate(ignoringOtherApps:)` **before** `show`, which makes the popover a window the
  click can land in and fixes the common case;
- a **global** mouse-down monitor, which sees clicks that go to other applications and never
  our own, so it cannot close the popover out from under its own buttons;
- a **local** key-down monitor for Esc, swallowed so the key does not also reach what is behind;
- `didResignActiveNotification`, for Cmd-Tab and Mission Control, where no click of ours happens.

All three monitors are torn down the moment the popover closes: a global event monitor that
outlives what it was watching keeps waking the process.

## Still open

- **Observations at scale** (the founder's reservation, M4 plan). The screen sorts by the
  largest absolute gap and shows everything above the engine's floors, which is honest at two
  projects and will not be at twenty: at that size the list becomes a ranking, and a ranking is
  a score by another name. Batch 3 made it worse-before-better by showing the per-project groups
  under "All projects" as well, which is more rows, not fewer. The reservation is written into
  `App/ObservationsView.swift` as a comment so that nobody adds a filter or a "top N" here
  without deciding the question first.
- **The dropdown's icon** carrying a live number, deferred from M3 and still deferred.
- **Empty and error states** beyond the ones each screen already has.
