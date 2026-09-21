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

`src/design/tokens.css`, copied from `docs/design/mockups/` and now the product's own
copy: from phase 1 on, `src/design/` is the source of truth and `docs/design/mockups/` is
a frozen record. `apps/mac/DESIGN.md` prints the table (purpose palette, outcome pair,
project scale, surfaces and ink, spacing, type, radii, motion) and
`test/tokens.test.mjs` asserts the file against it, so a token table nobody checks cannot
drift from what is drawn.

**`src/app.css` and `src/window.css` say where things go and never declare a token.** A
colour, a spacing or a radius written in an app stylesheet is a decision two surfaces will
eventually disagree about; a test asserts that neither file declares a custom property.

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

## The bridge

**Every Tauri call in the frontend is in `src/bridge.js`.** Nothing under `src/design/`,
`src/panel.js` or `src/window.js` knows what a Tauri is.

This is load bearing, not tidiness. If the webview under this frontend ever has to change,
the shell and that one file are rewritten and everything else moves unchanged. That is the
way out if Tauri fails on a later macOS, and it stays open only while the rule holds.

The surface is small on purpose: read the store, ask the shell about itself, report how
tall the panel's content is, open and close the window, remember which section the window
is on, say something on the shell's standard error, quit.

## No build step

Plain script tags, no bundler, no transpiler. Native ES modules if a batch needs real
module boundaries; still no build step.

Three reasons, in order: `src/design/` stays readable as the design system rather than as
an input to a pipeline; the Electron exit stays cheap, because a frontend with no build is
a frontend any shell can serve; and a batch is judged on a picture of the running app, so
nothing is gained by putting a compiler between the source and the picture.

## Platform differences

**They live in `src-tauri/src/platform/`**, behind one interface with three
implementations (`macos`, `windows`, and a do-nothing fallback). The page never asks which
system it is on. A difference that cannot be held in that folder is a difference that will
end up in the page, which is what closes the door on Windows.

Today that interface is five functions: apply the material, find the tray anchor, set the
status item's highlight, show or hide the Dock icon, describe the platform.

## The app owns no numbers

`src-tauri/src/store.rs` opens the store read-only, refuses a contract version outside
`SUPPORTED_CONTRACT`, and selects from `app_*` views and nothing else. The page may **sum
view columns into a bucket** and take the **ratio of two columns of the same row**, and
nothing else. A median, a threshold or an attribution is a new view in
`src/prudence/store/app_views.py`, never a function here.

Any number on a screen that is not one of those three things is a bug, however reasonable
it looks.

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

## Components

Grown by each batch. Batch 1 adds the window shell only.

| Component | What it is | Where |
|---|---|---|
| The panel | 360 pt, variant C with a caption above every block, the action grid at the foot | `src/panel.js` |
| The window shell | Titlebar (the system's own, overlaid), sidebar with four entries, toolbar strip, one screen at a time | `src/window.js`, `src/window.css` |
| The backdrop | A plain full-screen window of the app's own, for screenshots only | `src/backdrop.html` |

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
