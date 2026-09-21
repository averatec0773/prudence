# Prudence.app

The native macOS menu bar app. It reads the same database `prudence` writes, shows the week at
a glance, and asks the CLI to do anything that changes the record.

## Build, run, test, render

```sh
cd apps/mac
./Scripts/bootstrap.sh                 # installs XcodeGen if needed, generates Prudence.xcodeproj
swift test --package-path PrudenceKit  # the fast loop: seconds, no Xcode project

xcodebuild -project Prudence.xcodeproj -scheme Prudence \
  -configuration Debug -derivedDataPath build/dd CODE_SIGNING_ALLOWED=NO build

./Scripts/shots.sh                     # shots/{menu,window,settings}-{light,dark}.png
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
the real store. Quit it from the dropdown, or `pkill -f Prudence.app/Contents/MacOS`.

`Prudence.xcodeproj`, `build/`, `DerivedData/` and `shots/` are generated and gitignored. Never
open Xcode's UI to add a file: add it to `App/` or `PrudenceKit/Sources/`, then run
`./Scripts/bootstrap.sh` again.

The Swift tests read `PrudenceKit/Tests/PrudenceKitTests/Fixtures/store.db`, a real store the
engine itself wrote. Regenerate it from the repository root when the contract changes:

```sh
MAC_FIXTURE_TARGET=apps/mac/PrudenceKit/Tests/PrudenceKitTests/Fixtures/store.db \
  uv run pytest tests/mac_fixture.py -q
```

## Layout

```
apps/mac/
  project.yml          XcodeGen manifest; the only build settings file an agent edits
  App/                 SwiftUI views and AppKit glue. No decision logic.
  PrudenceKit/         the local Swift package: everything the app thinks with
    Sources/PrudenceStore/    GRDB, read-only, over the app_* views, with the contract check
    Sources/PrudenceEngine/   finds and runs the prudence CLI
    Sources/PrudenceModels/   view models and formatting
  Render/              off-screen PNG harness; compiles the app's own view files
  Scripts/             bootstrap.sh, shots.sh
```

## Three conventions

**1. `NSStatusItem`, not `MenuBarExtra`.** SwiftUI's menu bar scene still cannot close its own
popup from a button inside it (FB11984872, open since February 2023), cannot tell you the user
opened it, and does not hand over the status item or the popup's window. A dropdown of today's
numbers that cannot know when it was opened shows stale numbers. Decaf, whose shape this app
otherwise copies, ships a whole file whose only job is to hijack what `MenuBarExtra` created.
The reasoning is written out at the top of `App/StatusItem.swift`; read it before reaching for
the shorter API. The same goes for the windows: they are hand-built `NSWindow` plus
`NSHostingController`, not SwiftUI `Window` or `Settings` scenes.

**2. The app owns no numbers.** Every figure on a screen comes from an `app_*` view or a stored
row (M3 rule 8, ARCHITECTURE rule 14). Swift never joins base tables and never computes an
outcome, a share of survival or a token total. A screen that needs a number the engine does not
compute gets a new view in `src/prudence/store/app_views.py`; the list of numbers this batch
wanted and could not have is below.

**3. The contract is checked before anything is rendered.** `Store.init` reads
`meta.app_contract_version` and refuses anything but `1`, with an error carrying both versions
and a sentence saying which side to update. No screen ever renders half a schema it does not
understand.

## Contract requests

Three things this batch wanted from `app_*` and did not find. None is worked around with a join
in Swift; each shows a placeholder or is simply absent, and each is a small addition to
`store/app_views.py` when the engine side next moves.

1. **Edits per local day.** The dropdown's "today" line is `N sessions, N commits`. The rumps
   prototype also said `N edits`, counted straight off the `edit` table, which the app may not
   do. Either a column on `app_session_list` (`edits`) or a small `app_edits_by_day` view would
   restore the line. `TodayModel.edits` is already optional and joins the line the day it
   exists.
2. **Commits per day, counted once.** `app_session_list` gives commits per session, so summing
   it over a day double counts a commit credited to two sessions; `views.credited_by_commit`
   does not. The number the dropdown shows is therefore an upper bound on a day where two
   sessions share a commit. A day-grained view, or a `distinct` count per day, would fix it.
3. **The observation's own sentence.** `app_observation` carries the numbers but not the prose,
   so `PrudenceModels/ObservationSentence.swift` restates the phrase table from
   `store/observations.SPLITS`. That is the one piece of Python this app repeats. A `sentence`
   column on `app_observation` would delete that file. Until then a test pins every sentence
   against what the CLI printed for the same fixture rows.

One read is not an `app_*` view at all: the newest `review` row, read for its headline (id,
range, project, first section title). Contract 1 has no `app_review` view, and the review screen
of M3 task 8 needs one; the read is kept to a headline and marked in
`PrudenceStore/Rows.swift` until it exists.

## Bundle identifier

`dev.prudence.app` is a placeholder. The real identifier is decided with the Apple Developer
Program account (M3 plan, open question 4); the Developer ID name appears in Gatekeeper
dialogs. Changing it is one line in `project.yml` and nothing in the code reads it.
