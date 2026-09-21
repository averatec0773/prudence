#!/usr/bin/env bash
# Render the shipping views off-screen into shots/.
#
# Every screen comes in light and dark and in English and Simplified Chinese, and the two
# surfaces that have a material come in Standard and Glass as well:
#
#   menu-{light,dark}-{en,zh}[-glass].png          the dropdown, variant C with captions
#   window-{light,dark}-{en,zh}[-glass].png        the whole window at its 900x600 floor
#   overview-{light,dark}-{en,zh}.png              Overview A: cards, stacked bars, lines, heat
#   review-{light,dark}-{en,zh}.png                Review B: every chart with its table open
#   observations-{light,dark}-{en,zh}.png          Observations C: paired bars, grouped
#   settings-{light,dark}-{en,zh}.png              Settings B, the General tab
#   settings-data-{light,dark}-{en,zh}.png         Settings B, the Data tab
#
# Thirty-six PNGs. The `-glass` pair is the popover and the window because those are the
# control and navigation layer; the screens inside the window are content and are opaque under
# either material, so photographing them twice would produce two identical files.
#
# Batch 3's `-primaryA` / `-primaryB` suffixes are gone: the founder chose A, so there is one
# primary style and the popover is photographed once per material again.
# `.github/workflows/mac-ci.yml` needs no edit, because it uploads the whole directory rather
# than a list of files.
#
# Every run ends with the label audit: each button style, under each material, rendered with
# its label and without it, failing if the two pictures are identical — which is what a label
# covered by its own material looks like (`PrudenceUI/LabelAudit.swift`, batch 3).
# PRUDENCE_SHOTS_ONSCREEN=1 makes it take those pictures through the window server, where macOS
# 26's glass is composited rather than drawn as a no-op, and adds a real NSPopover case. It
# needs a window server and the screen-recording permission, so it is off by default.
#
# The audit is a net and not a reproduction: LabelAudit.swift records that none of its three
# forms caught the batch 3 popover bug when the broken code was put back, and that the check
# for anything about the material is a picture of the running app (apps/mac/README.md).
#
# The three screen shots are taller than a window on purpose (batch 2): each of them now
# carries several charts, and a shot cut off at 800 px would hide the ones a reviewer is being
# asked about. `window` stays at the 900x600 floor, which is where the layout is under the most
# pressure.
#
# The harness compiles the app's own view files rather than copies of them: they are copied in
# here, built, and the copies are thrown away afterwards, so a PNG can never show a view that
# no longer exists. The files below are the ones with no AppKit entry point in them;
# PrudenceApp, AppDelegate and StatusItem are the app's plumbing and are not rendered.
#
# PRUDENCE_SHOTS_DUMP=1 also prints the Overview's cards and weekly totals, for putting beside
# `prudence usage` over the same store.
set -euo pipefail

cd "$(dirname "$0")/.."

VIEWS=(
    MenuContentView.swift
    MainWindow.swift
    OverviewView.swift
    ReviewView.swift
    ObservationsView.swift
    SettingsView.swift
)
TARGET="Render/Sources/PrudenceRender/Views"

rm -rf "$TARGET"
mkdir -p "$TARGET"
for view in "${VIEWS[@]}"; do
    cp "App/$view" "$TARGET/$view"
done

export PRUDENCE_SHOTS_FIXTURE="${PRUDENCE_SHOTS_FIXTURE:-$PWD/PrudenceKit/Tests/PrudenceKitTests/Fixtures/store.db}"
export PRUDENCE_SHOTS_DIR="${PRUDENCE_SHOTS_DIR:-$PWD/shots}"
# The body of the review the `review` shot draws. `tests/mac_fixture.py` writes a review with
# two sections and one purpose row, which is enough for the decoding tests and too thin to
# photograph; this is one real payload copied off the founder's own store, which the decoding
# tests already read. Everything else about that review row is still the fixture's. Set it to
# an empty string to photograph the fixture's own payload instead.
export PRUDENCE_SHOTS_REVIEW="${PRUDENCE_SHOTS_REVIEW:-$PWD/PrudenceKit/Tests/PrudenceKitTests/Fixtures/review-sections.json}"

swift run --package-path Render PrudenceRender

rm -rf "$TARGET"
ls -l "$PRUDENCE_SHOTS_DIR"
