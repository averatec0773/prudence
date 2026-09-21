#!/usr/bin/env bash
# Render the shipping views to shots/{menu,window,settings}-{light,dark}.png, off-screen.
#
# The harness compiles the app's own view files rather than copies of them: they are copied in
# here, built, and the copies are thrown away afterwards, so a PNG can never show a view that
# no longer exists. The three files below are the ones with no AppKit entry point in them;
# PrudenceApp, AppDelegate and StatusItem are the app's plumbing and are not rendered.
set -euo pipefail

cd "$(dirname "$0")/.."

VIEWS=(MenuContentView.swift MainWindow.swift SettingsView.swift)
TARGET="Render/Sources/PrudenceRender/Views"

rm -rf "$TARGET"
mkdir -p "$TARGET"
for view in "${VIEWS[@]}"; do
    cp "App/$view" "$TARGET/$view"
done

export PRUDENCE_SHOTS_FIXTURE="${PRUDENCE_SHOTS_FIXTURE:-$PWD/PrudenceKit/Tests/PrudenceKitTests/Fixtures/store.db}"
export PRUDENCE_SHOTS_DIR="${PRUDENCE_SHOTS_DIR:-$PWD/shots}"

swift run --package-path Render PrudenceRender

rm -rf "$TARGET"
ls -l "$PRUDENCE_SHOTS_DIR"
