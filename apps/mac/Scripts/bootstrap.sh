#!/usr/bin/env bash
# Generate Prudence.xcodeproj from project.yml, installing XcodeGen if it is missing.
#
# Run it after cloning, and again whenever a file is added to App/ or project.yml changes.
# The project is not tracked, so this is never a merge conflict and never out of date for
# longer than one command.
set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v xcodegen >/dev/null 2>&1; then
    if ! command -v brew >/dev/null 2>&1; then
        echo "xcodegen is not installed and Homebrew is not available." >&2
        echo "Install it from https://github.com/yonaskolb/XcodeGen and run this again." >&2
        exit 1
    fi
    echo "Installing xcodegen..."
    brew install xcodegen
fi

xcodegen generate
echo "Generated $(pwd)/Prudence.xcodeproj"
