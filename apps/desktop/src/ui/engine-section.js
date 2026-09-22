/* The engine: where the `prudence` executable is, and what it can be asked to do.
 *
 * **This is a seam between two pieces of work.** The Settings screen places
 * `engineSection`; this file fills it in. It is its own module so that neither has to
 * edit the other's file, and so the block can also be shown from somewhere else later
 * (the panel has the same two actions).
 *
 * ## Three surfaces, one runner
 *
 * - `engineSection` is the block on the Settings screen's Engine tab: the path, the two
 *   versions, the actions, the picker, and the Install or Update button with the area
 *   under it that reports what uv did.
 * - `engineActivity` is one strip, put on the page once, that says what a run is doing
 *   and how it ended. It exists because a run can be started from the Review screen too,
 *   and an action that takes a minute and reports nowhere is an action that silently does
 *   nothing.
 * - `run` is the only thing that starts the engine, wherever the button was.
 *
 * ## Why the shell does the work
 *
 * Nothing here looks at a filesystem or starts a process, because a page cannot.
 * `ui/wiring.js` points [`ENGINE`] at the bridge, `src-tauri/src/engine.rs` and
 * `installer.rs` answer, and this file draws the answer. That is also why it computes
 * nothing: the version is the string the CLI printed, the session count is the figure the
 * engine's own ingest summary carried, a "not ready" reason is the engine's own sentence,
 * and the install report is uv's own output.
 */

import { emptyState, runProgress } from "../design/components.js";
import { el } from "../design/dom.js";
import { sessions as sessionPhrase } from "../text/fmt.js";
import { t } from "../text/strings.js";

/**
 * What the block and the runner ask the shell.
 *
 * Injected rather than imported directly so that a test can drive the whole block
 * against a fake engine, which is the only way to exercise "not found", "not ready" and
 * "it failed" without a machine in each of those states. `ui/wiring.js` sets it to the
 * bridge.
 *
 * @typedef {{
 *   status: () => Promise<any>,
 *   run: (action: string, force: boolean) => Promise<any>,
 *   choose: () => Promise<any>,
 *   forget: () => Promise<any>,
 *   install: (upgrade: boolean) => Promise<any>,
 *   onInstallProgress: (handler: (lines: string[]) => void) => Promise<() => void>,
 *   onProgress?: (handler: (progress: any) => void) => Promise<() => void>,
 *   link: (name: string) => Promise<any>,
 * }} EnginePort
 *
 * @type {{ port: EnginePort | null }}
 */
export const ENGINE = { port: null };

/** The strip currently on the page, or nothing. One per page; see `engineActivity`. */
let strip = /** @type {any} */ (null);

/** True from the moment a run starts until the engine exits. Two surfaces can both ask,
 *  and the shell refuses the second one, so the page should not offer it either. */
let running = false;

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
    // on layout. It says so rather than pretending to have looked.
    //
    // `engine.notFound.detail` ends by telling the reader to choose the file themselves,
    // and this branch drew no Choose button, so the one sentence on screen named an
    // action that was not there. There is nothing to pick with either, so the sentence is
    // the one for a page with no shell behind it.
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
  // One key with two placeholders. This glued a localised sentence to the engine's raw
  // English with an ASCII space, which in Chinese put a space after a full-width full
  // stop and a newline inside one paragraph.
  return refused?.error ? t("engine.rejectedWithDetail", said, String(refused.error)) : said;
}

function fill(body, status, state) {
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
}

function actions(body, status, state, area) {
  const row = el("div", { class: "engine-actions" });

  const redraw = () => {
    const port = ENGINE.port;
    if (!port) return Promise.resolve();
    return port
      .status()
      .then((next) => fill(body, next, state))
      .catch((error) => {
        body.innerHTML = "";
        body.appendChild(emptyState(t("engine.failed.title"), message(error)));
      });
  };

  if (status?.found) {
    row.appendChild(action(t("menu.ingestNow"), "primary", () => run("ingest")));
    row.appendChild(action(t("menu.reviewNow"), "", () => run("review")));
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
    // Not disabled by a run: it starts none, and it is how a reader recovers.
    row.appendChild(action(t("common.tryAgain"), "", redraw, { whileRunning: "keep" }));
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
          // A file the reader chose and the shell would not keep. Saying nothing here
          // would leave them looking at the block they were trying to change, with no
          // word about the file they picked.
          if (choice?.errorKind) {
            announce([
              line(t("engine.rejected", refusal(choice))),
              button(t("common.dismiss"), "plain", clear),
            ]);
          }
          return redraw();
        })
        .catch(redraw);
    }, { whileRunning: "keep" })
  );

  if (status?.remembered) {
    row.appendChild(
      action(t("common.clear"), "plain", () => {
        const port = ENGINE.port;
        if (!port) return;
        port.forget().then(redraw).catch(redraw);
      }, { whileRunning: "keep" })
    );
  }
  return row;
}

/**
 * A button in the block, remembered so that a run can disable it and a run's end can
 * bring it back.
 *
 * `if (running) button.disabled = true` was evaluated once, when the button was built, so
 * in the tree that *started* a run nothing was disabled, and a tree built *during* a run
 * had every button disabled for ever, because nothing redrew the block when the run
 * ended. A review the engine declines does not change the store, so there was no refresh
 * either: the screen's primary actions stayed dead with no explanation.
 *
 * `Choose` is deliberately not disabled. It starts no run, and it is the way out when the
 * remembered path is the problem.
 */
function action(label, variant, onClick, { whileRunning = "disable" } = {}) {
  const button = el("button", { class: `btn ${variant}`.trim(), type: "button", text: label });
  button.addEventListener("click", onClick);
  if (whileRunning === "disable") {
    buttons.add(button);
    /** @type {any} */ (button).disabled = running;
  }
  return button;
}

/** Every button a run disables, in whichever tree is on screen. */
const buttons = new Set();

/**
 * Disable or restore them, so the state of a run is visible wherever it is drawn.
 *
 * No pruning by `isConnected`: that made correctness depend on a real-DOM property, and
 * under the test shim every button was dropped from the set instead of disabled, so the
 * first version of this fix did nothing and a test caught it. The set is emptied when the
 * block is rebuilt, and setting `disabled` on a node that has since been replaced is
 * harmless.
 */
function setRunning(value) {
  running = value;
  for (const button of buttons) /** @type {any} */ (button).disabled = value;
}

/* --- the strip ----------------------------------------------------------------------- */

/**
 * The one place a run reports, wherever it was started from.
 *
 * Put on the page rather than inside a screen, on purpose: a run outlives the screen it
 * was started on, and the Review screen's own button cannot report from inside a tree
 * that is rebuilt whenever the store changes.
 *
 * @returns {Element}
 */
export function engineActivity() {
  strip = el("div", { class: "engine-activity" });
  strip.hidden = true;
  return strip;
}

/**
 * The sentence for a failure kind, with no way to reach a key that is not there.
 *
 * Every kind the shell can send is named here. A kind this build has never heard of gets
 * the general sentence rather than its own name, because a reader should never be shown
 * an identifier.
 */
function failureSentence(kind) {
  // `busy` and `notFound` have their own sentences elsewhere in the catalogue: "a run is
  // already going", and the general "the engine is not there", which is a different
  // statement from a file that will not say what it is.
  if (kind === "busy") return t("engine.busy");
  if (kind === "notFound") return t("menu.engineMissing");
  // The kinds with a key of their own. `EngineError::kind()` can return exactly
  // `notFound`, `launch`, `failed`, `noVersion` and `busy`; `notExecutable` is not a kind
  // but is the sentence for a file that was found and refused, used by `refusal`.
  const known = ["notExecutable", "noVersion", "launch", "failed"];
  return known.includes(kind) ? t(`engine.error.${kind}`) : t("engine.failed.detail");
}

/** Nothing on screen. What the reader's Dismiss and Cancel do. */
function clear() {
  if (!strip) return;
  strip.innerHTML = "";
  strip.hidden = true;
}

/** @param {Element[]} nodes */
function announce(nodes) {
  if (!strip) return;
  strip.innerHTML = "";
  for (const node of nodes) strip.appendChild(node);
  strip.hidden = false;
}

/** One more line on the strip, keeping what is already there. */
function add(node) {
  if (!strip) return;
  strip.appendChild(node);
  strip.hidden = false;
}

function line(text) {
  return el("p", { class: "engine-said", text });
}

function button(label, variant, onClick) {
  const node = el("button", { class: `btn ${variant}`.trim(), type: "button", text: label });
  node.addEventListener("click", onClick);
  return node;
}

/**
 * Start a run and report it.
 *
 * Nothing is plumbed into the screens: the shell watches the store and refreshes every
 * page when an ingest or a review lands, so the new figures arrive on their own.
 *
 * @param {"ingest"|"review"} action
 * @param {{ force?: boolean }} [options]
 * @returns {Promise<void>}
 */
export function run(action, options) {
  const port = ENGINE.port;
  if (!port) {
    announce([line(t("menu.engineMissing")), line(t("engine.notFound.detail"))]);
    return Promise.resolve();
  }
  if (running) {
    // Added to the strip, not in place of it. `announce` clears first, so refusing a
    // second action used to replace the only line saying a run was going, and dismissing
    // that left nothing on screen about it at all.
    add(line(t("engine.busy")));
    return Promise.resolve();
  }
  setRunning(true);
  announce([line(action === "ingest" ? t("menu.ingesting") : t("menu.writingReview"))]);

  /* What the engine is doing, on the strip, in place of the sentence that says a run
     started. The same component the panel draws and the same events: a run can be watched
     from either surface, and the shell announces to both.

     The strip is the whole width of the screen's content column, so the bar is wide here
     and narrow there with no second rule anywhere. */
  let stop = /** @type {(() => void) | null} */ (null);
  const listening = port.onProgress?.((progress) => {
    if (running) announce([runProgress(progress)]);
  });
  if (listening) {
    listening
      .then((off) => {
        stop = off;
      })
      .catch(() => {});
  }

  return port
    .run(action, Boolean(options?.force))
    .then((outcome) => {
      setRunning(false);
      stop?.();
      report(outcome);
    })
    .catch((error) => {
      setRunning(false);
      stop?.();
      // The shell itself did not answer. Not the engine's failure, and it still has to be
      // said: a swallowed rejection here is a strip that reads "Ingesting..." for ever.
      announce([
        line(t("engine.failed.title")),
        line(message(error)),
        button(t("common.dismiss"), "plain", clear),
      ]);
    });
}

/** What the engine said, said in the reader's language. */
function report(outcome) {
  if (outcome?.errorKind) {
    const kind = String(outcome.errorKind);
    // `notFound` from a *run* means the search found nothing at press time, which is a
    // different sentence from a file that will not say what it is. There is no
    // `engine.error.notFound` key, so this printed the literal string
    // "engine.error.notFound" on screen: the block was drawn while `prudence` was on
    // disk and the path moved before the button was pressed.
    const said = failureSentence(kind);
    const nodes = [line(t("engine.failed.title")), line(said)];
    // The engine's own words, as `store.rs`'s errors are shown as they come.
    if (outcome.error) nodes.push(line(String(outcome.error)));
    nodes.push(button(t("common.dismiss"), "plain", clear));
    announce(nodes);
    return;
  }

  if (outcome?.notReady) {
    // The engine declined, and the reason is the whole point of the button in that case.
    // `--force` is the only way past its readiness rule, and that is the reader's
    // decision to make, not the app's.
    announce([
      line(t("review.notReady.title")),
      // The engine's own sentence, printed as it came: it names the counts and the
      // thresholds, and rewording it would make the app and the CLI disagree.
      line(String(outcome.reason ?? t("menu.reviewNotReady"))),
      button(t("review.writeAnyway"), "primary", () => run("review", { force: true })),
      button(t("common.cancel"), "plain", clear),
    ]);
    return;
  }

  if (outcome?.action === "review") {
    announce([
      line(
        outcome.reviewId === null || outcome.reviewId === undefined
          ? t("menu.reviewWritten")
          : t("menu.reviewWrittenId", String(outcome.reviewId))
      ),
      button(t("common.dismiss"), "plain", clear),
    ]);
    return;
  }

  announce([
    line(
      outcome?.sessions === null || outcome?.sessions === undefined
        ? t("menu.ingestFinished")
        : t("engine.ingestFinished.sessions", sessionPhrase(Number(outcome.sessions)))
    ),
    button(t("common.dismiss"), "plain", clear),
  ]);
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

/** The area under the Install button. Rebuilt with the block, like everything else here. */
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
  row.appendChild(action(t("common.tryAgain"), "plain", redraw, { whileRunning: "keep" }));
  block.appendChild(row);
  return block;
}

/**
 * Press once: run uv, stream its lines, and say what it ended as.
 *
 * The button is disabled for the whole run through the same set every other action uses,
 * so an install and an ingest cannot be started over one another.
 */
function install(area, upgrade, redraw) {
  const port = ENGINE.port;
  if (!port) return;
  setRunning(true);
  said(area, [line(t("engine.install.running"))]);

  let stop = /** @type {(() => void) | null} */ (null);
  port
    .onInstallProgress((lines) => said(area, [line(t("engine.install.running")), output(lines)]))
    .then((off) => {
      stop = off;
    })
    .catch(() => {});

  port
    .install(upgrade)
    .then((outcome) => {
      setRunning(false);
      stop?.();
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
      setRunning(false);
      stop?.();
      said(area, [line(t("engine.install.failed")), line(message(error))]);
    });
}
