/* The engine: where the `prudence` executable is, what it is, and how to get it.
 *
 * **This is a seam between two pieces of work.** The Settings screen places
 * `engineSection` on its Engine tab; this file fills it in. It is its own module so that
 * neither has to edit the other's file.
 *
 * It is configuration and nothing else: the path with its picker and whether it was found
 * or chosen, the version it says it is, and the Install or Update button with the area
 * under it that reports what uv did. The two actions that *run* the engine are in the
 * window's toolbar (`ui/activity.js`), on every screen, because a run is something a
 * reader starts from wherever they are and not something they go to Settings for.
 *
 * ## Why the shell does the work
 *
 * Nothing here looks at a filesystem or starts a process, because a page cannot.
 * `ui/wiring.js` points [`ENGINE`] at the bridge, `src-tauri/src/engine.rs` and
 * `installer.rs` answer, and this file draws the answer. That is also why it computes
 * nothing: the version is the string the CLI printed and the install report is uv's own
 * output.
 */

import { emptyState } from "../design/components.js";
import { el } from "../design/dom.js";
import { t } from "../text/strings.js";
import { ACTIVITY } from "./activity.js";

/**
 * What the block asks the shell.
 *
 * Injected rather than imported directly so that a test can drive the whole block
 * against a fake engine, which is the only way to exercise "not found" and "it failed"
 * without a machine in each of those states. `ui/wiring.js` sets it to the bridge.
 *
 * @typedef {{
 *   status: () => Promise<any>,
 *   choose: () => Promise<any>,
 *   forget: () => Promise<any>,
 *   install: (upgrade: boolean) => Promise<any>,
 *   onInstallProgress: (handler: (lines: string[]) => void) => Promise<() => void>,
 *   link: (name: string) => Promise<any>,
 * }} EnginePort
 *
 * @type {{ port: EnginePort | null }}
 */
export const ENGINE = { port: null };

/** True from the moment uv starts until it exits. */
let installing = false;

/* --- the block ----------------------------------------------------------------------- */

/**
 * @param {import("./screens.js").ScreenState} [state]
 * @returns {Element}
 */
export function engineSection(state) {
  const body = el("div", { class: "engine-body" });
  const root = el("div", { class: "engine-section" }, [
    el("h2", { class: "engine-title", text: t("settings.enginePath") }),
    body,
  ]);

  const port = ENGINE.port;
  if (!port) {
    // No shell: the page is open in a browser, which is a real thing to do while working
    // on layout. It says so rather than pretending to have looked, and draws no Choose
    // button, because there is nothing to pick with.
    body.appendChild(emptyState(t("menu.engineMissing"), t("engine.noShell.detail")));
    return root;
  }

  // The answer needs a login shell and a subprocess, so the block is drawn now and
  // filled when the shell answers. A blank area while it works would be the surface
  // saying nothing about the one question it is for.
  body.appendChild(el("p", { class: "engine-line", text: t("menu.engineChecking") }));
  port
    .status()
    .then((status) => fill(body, status, state))
    .catch((error) => {
      body.innerHTML = "";
      body.appendChild(emptyState(t("engine.failed.title"), message(error)));
    });
  return root;
}

/** The engine version the store carries: `app_status.engine_version`, as the engine
 *  wrote it. Never derived, and absent before the first read. */
function storeVersion(state) {
  const written = state?.data?.status?.engine_version;
  return written ? String(written) : null;
}

/** Which sentence says where this executable came from. */
function sourceLabel(source) {
  if (source?.kind === "settings") return t("settings.source.settings");
  if (source?.kind === "loginShell") return t("engine.source.loginShell");
  return t("settings.foundAutomatically");
}

/**
 * Why a file that *was* found is not being used.
 *
 * Shared by the block, which reports a search hit that would not answer `--version`, and
 * by the picker, which reports a file the reader chose and the shell refused.
 *
 * @param {{ errorKind?: string, error?: string }} refused
 */
function refusal(refused) {
  const kind = String(refused?.errorKind ?? "");
  // "not found" means two things. Here it means this file is not something that can be
  // run; the other meaning, nothing anywhere, is the empty state above.
  const said = kind === "notFound" ? t("engine.error.notExecutable") : t(`engine.error.${kind}`);
  // One key with two placeholders, so Chinese punctuation is not glued to English.
  return refused?.error ? t("engine.rejectedWithDetail", said, String(refused.error)) : said;
}

/**
 * @param {any} body
 * @param {any} status the shell's answer
 * @param {any} state
 * @param {string} [notice] one line for the area under the actions, from whatever asked
 *   for this drawing: the block is rebuilt from the shell's new answer, so a line written
 *   into the old one would be written into nodes nobody sees
 */
function fill(body, status, state, notice) {
  body.innerHTML = "";
  // The buttons about to be replaced are gone; the new ones register themselves.
  buttons.clear();

  if (status?.found) {
    body.appendChild(el("p", { class: "engine-path", text: String(status.path) }));
    body.appendChild(
      el("p", {
        class: "engine-line",
        text: t("engine.versionAndSource", String(status.version), sourceLabel(status.source)),
      })
    );
  } else {
    body.appendChild(emptyState(t("menu.engineMissing"), t("engine.notFound.detail")));
    // Something was found and refused. The path and the engine's own words for why,
    // because "not found" on a machine where the file is plainly there is a dead end.
    if (status?.path) {
      body.appendChild(el("p", { class: "engine-path", text: String(status.path) }));
      body.appendChild(
        el("p", { class: "engine-line", text: t("engine.rejected", refusal(status)) })
      );
    }
  }

  body.appendChild(el("p", { class: "engine-note", text: t("settings.enginePath.note") }));

  // Two installations, two versions. Said calmly: the app reads more than one store
  // contract, so a mismatch is worth knowing and is not worth stopping for.
  const written = storeVersion(state);
  if (status?.found && written && written !== String(status.version)) {
    body.appendChild(
      el("p", {
        class: "engine-note",
        text: t("engine.versionMismatch", String(status.version), written),
      })
    );
  }

  const area = installArea();
  body.appendChild(actions(body, status, state, area));
  body.appendChild(area);
  if (notice) said(area, [line(notice)]);

  // A run going anywhere keeps Install and Update disabled: replacing the executable under
  // an ingest that is using it is not something to offer. The toolbar's answer arrives
  // here the same way it reaches the toolbar.
  ACTIVITY.mounts.set("engine", () => setDisabled());
}

function actions(body, status, state, area) {
  const row = el("div", { class: "engine-actions" });

  /** @param {string} [notice] */
  const redraw = (notice) => {
    const port = ENGINE.port;
    if (!port) return Promise.resolve();
    return port
      .status()
      .then((next) => fill(body, next, state, notice))
      .catch((error) => {
        body.innerHTML = "";
        body.appendChild(emptyState(t("engine.failed.title"), message(error)));
      });
  };

  if (status?.found) {
    // Secondary where the engine is already here: updating is a thing a reader chooses,
    // not the thing this block is for.
    row.appendChild(action(t("engine.install.update"), "", () => install(area, true, redraw)));
  } else {
    // The primary action of a machine with no engine is to get one. Everything else on
    // the block is a way of finding one that is already installed.
    row.appendChild(
      action(t("engine.install.install"), "primary", () => install(area, false, redraw))
    );
    // The search is cheap to repeat and the answer changes the moment the engine is
    // installed, so the way out of "not found" is not a relaunch.
    row.appendChild(action(t("common.tryAgain"), "", () => redraw(), { whileBusy: "keep" }));
  }

  // Offered whether or not something was found: an engine found in one place and wanted
  // from another is the same request as an engine not found at all.
  row.appendChild(
    action(t("common.choose"), "plain", () => {
      const port = ENGINE.port;
      if (!port) return;
      // Cancelling leaves the block as it is; a chosen file, taken or refused, is a new
      // answer, and the shell is asked again rather than the page guessing what changed.
      port
        .choose()
        .then((choice) => {
          if (choice?.cancelled) return undefined;
          // A file the reader chose and the shell would not keep. Said in the block the
          // reader was trying to change, with the file they picked named in the engine's
          // own words: saying nothing would leave them looking at the block as it was.
          return redraw(choice?.errorKind ? t("engine.rejected", refusal(choice)) : undefined);
        })
        .catch(() => redraw());
    }, { whileBusy: "keep" })
  );

  if (status?.remembered) {
    row.appendChild(
      action(t("common.clear"), "plain", () => {
        const port = ENGINE.port;
        if (!port) return;
        port
          .forget()
          .then(() => redraw())
          .catch(() => redraw());
      }, { whileBusy: "keep" })
    );
  }
  return row;
}

/**
 * A button in the block, remembered so that an install or a run can disable it and its
 * end can bring it back.
 *
 * `Choose`, `Clear` and `Try again` are deliberately never disabled. They start nothing,
 * and they are the way out when the remembered path is the problem.
 */
function action(label, variant, onClick, { whileBusy = "disable" } = {}) {
  const button = el("button", { class: `btn ${variant}`.trim(), type: "button", text: label });
  button.addEventListener("click", onClick);
  if (whileBusy === "disable") {
    buttons.add(button);
    /** @type {any} */ (button).disabled = busy();
  }
  return button;
}

/** Every button an install or a run disables, in whichever tree is on screen. The set is
 *  emptied when the block is rebuilt, and setting `disabled` on a node that has since been
 *  replaced is harmless. */
const buttons = new Set();

function busy() {
  return installing || Boolean(ACTIVITY.now.running);
}

function setDisabled() {
  for (const button of buttons) /** @type {any} */ (button).disabled = busy();
}

function line(text) {
  return el("p", { class: "engine-said", text });
}

function message(error) {
  return error instanceof Error ? error.message : String(error);
}

/* --- installing it --------------------------------------------------------------------
 *
 * One button, and one area under it that says what happened. What the button runs is two
 * constants in `src-tauri/src/installer.rs`; the page sends a boolean and nothing else.
 *
 * The package is not on PyPI yet, so failing is today's ordinary outcome and is treated as
 * one: the same area then prints the manual route, which is the two commands a reader
 * types, selectable, with the README link beside them.
 */

/** The area under the actions. Rebuilt with the block, like everything else here. */
function installArea() {
  const area = el("div", { class: "engine-install" });
  area.hidden = true;
  return area;
}

/** Replace what the area says, keeping it one element so nothing accumulates. */
function said(area, nodes) {
  area.innerHTML = "";
  for (const node of nodes) area.appendChild(node);
  area.hidden = false;
}

/** uv's own output, as it printed it. Monospaced, because it is a terminal's words. */
function output(lines) {
  return el(
    "pre",
    { class: "engine-output" },
    lines.map((line) => el("div", { text: line }))
  );
}

/** The two commands a reader runs when the button could not. Selectable: their only use
 *  is in a terminal, and `window.css` turns selection off for the window. */
function manualRoute(commands, redraw) {
  const block = el("div", { class: "engine-manual" }, [
    el("p", { class: "engine-note", text: t("engine.install.manual") }),
    el(
      "pre",
      { class: "engine-output is-copyable" },
      commands.map((line) => el("div", { text: line }))
    ),
  ]);
  const row = el("div", { class: "engine-actions" });
  row.appendChild(action(t("engine.install.readme"), "plain", () => ENGINE.port?.link?.("install")));
  row.appendChild(action(t("common.tryAgain"), "plain", () => redraw(), { whileBusy: "keep" }));
  block.appendChild(row);
  return block;
}

/**
 * Press once: run uv, stream its lines, and say what it ended as.
 *
 * The button is disabled for the whole install through the same set a run disables, so an
 * install and an ingest cannot be started over one another from this block.
 */
function install(area, upgrade, redraw) {
  const port = ENGINE.port;
  if (!port) return;
  installing = true;
  setDisabled();
  said(area, [line(t("engine.install.running"))]);

  let stop = /** @type {(() => void) | null} */ (null);
  port
    .onInstallProgress((lines) => said(area, [line(t("engine.install.running")), output(lines)]))
    .then((off) => {
      stop = off;
    })
    .catch(() => {});

  const done = () => {
    installing = false;
    setDisabled();
    stop?.();
  };

  port
    .install(upgrade)
    .then((outcome) => {
      done();
      if (outcome?.ok) {
        said(area, [line(t("engine.install.done"))]);
        // The locator is asked again rather than the page assuming: the whole point of
        // the button is that the answer above it changes.
        redraw();
        return;
      }
      const nodes = [line(t(outcome?.errorKind === "noUv" ? "engine.install.noUv" : "engine.install.failed"))];
      if (outcome?.lines?.length) nodes.push(output(outcome.lines.map(String)));
      if (outcome?.manual?.length) nodes.push(manualRoute(outcome.manual.map(String), redraw));
      said(area, nodes);
    })
    .catch((error) => {
      done();
      said(area, [line(t("engine.install.failed")), line(message(error))]);
    });
}
