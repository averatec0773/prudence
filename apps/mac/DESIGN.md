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
  24, popover padding 14 with 10 between blocks.
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
| `StatRow` | A caption in a fixed column and a value beside it | the popover's five blocks |
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

`PrudenceButtonStyle` in three emphases, which is the whole of the custom control drawing:

- `.prudencePrimary` — the one prominent action per surface: the accent at 92 %, a white
  label, no gradient.
- `.prudence` — the frosted default: 8 pt rounded rect, one hairline edge, a top inner
  highlight that is barely there, no drop shadow.
- `.prudencePlain` — Quit and Dismiss: a hover wash and nothing else.

Hover brightens the tint by a few per cent; press darkens it and **nothing moves**.

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

**`assets/` is untracked in git.** `BrandMark` therefore loads the package's own copies rather
than the originals, which is what lets the app build from a clean checkout; the script refreshes
those copies.

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

| Screen | Variant | State after batch 2 |
|---|---|---|
| Menu bar popover | **C with captions** | today back at caption weight (it read heavy as a headline), the week as a `MiniStack` with its top-three legend, the observation composed in the interface language, the two stamps, C's button layout |
| Settings | **B** | General and Data tabs, grouped boxes, the language setting; the store's location now in the reader's language |
| Overview | **A** | one column, cards first: the three totals, `StackedBarsChart` with hover and week selection, `LinesWithGaps` with coverage, `HeatStrip` |
| Review | **B** | charts with their tables open under them: `DonutChart` + the purpose table, `ShareWithCoverageBar` rows, `PairedBarsChart` rows, `CompareCard`s, the model segment last with its model and its language |
| Observations | **C** | grouped by behaviour: one card per fact, the threshold, one `PairedBarsChart` per outcome with `n` on each bar, the coverage and method line |

## Contract requests

Four figures a screen wants and the `app_*` views do not carry. None of them is computed in
Swift; each one is shown as a placeholder, a reading, or not at all, and each is a small
addition on the Python side.

1. **`with_n` and `without_n` on a review's observation numbers.** `reviews/build._observations`
   stores the sentence, the caveat and the two medians; the counts live on `app_observation`
   and not in the payload, so the Review screen's paired bars carry no `n`. The sentence above
   them carries both in words. Reading them off the live observation rows instead would put
   this range's prose beside another range's counts.
2. **A `value` on the `compared.*` numbers.** They are stored as text alone, so `CompareCard`
   reads the leading figure out of the printed cell to size its mini bars (above).
3. **`app_review.segment_language`.** `--language` reaches the prompt and the answer is stored
   as prose, so the only record of which language was asked for is the text.
   `ReviewText.segmentLanguage` reads it off the words, which is exact for the two languages
   this app ships and is still a reading rather than a read.
4. **A structured threshold on `app_observation`.** `threshold_text` is the engine's English
   ("more than 0", "at least 3"), so an Observations card in Chinese shows one English clause.
   A rule and a value beside the text would let the interface word it.

## Still open

- **Observations at scale** (the founder's reservation, M4 plan). The screen sorts by the
  largest absolute gap and shows everything above the engine's floors, which is honest at two
  projects and will not be at twenty: at that size the list becomes a ranking, and a ranking is
  a score by another name. The reservation is written into `App/ObservationsView.swift` as a
  comment so that nobody adds a filter or a "top N" here without deciding the question first.
- **The dropdown's icon** carrying a live number, deferred from M3 and still deferred.
- **Empty and error states, window memory and keyboard**, which are batch 3.
