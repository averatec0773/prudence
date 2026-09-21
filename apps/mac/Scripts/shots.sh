#!/usr/bin/env bash
# Render the shipping views off-screen, light and dark, to shots/:
#
#   menu-{light,dark}.png          the dropdown
#   window-{light,dark}.png        the main window at its 900x600 floor
#   overview-{light,dark}.png      the Overview screen, 1200x800
#   review-{light,dark}.png        the Review screen, 1200x800
#   observations-{light,dark}.png  the Observations screen, 1200x800
#   settings-{light,dark}.png      the Settings screen
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

swift run --package-path Render PrudenceRender

rm -rf "$TARGET"
ls -l "$PRUDENCE_SHOTS_DIR"
