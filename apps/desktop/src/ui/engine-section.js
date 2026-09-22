/* The engine: where the `prudence` executable is, and what it can be asked to do.
 *
 * **This is a seam between two pieces of work.** The Settings screen places
 * `engineSection`; this file fills it in. It is its own module so that neither has to
 * edit the other's file, and so the block can also be shown from somewhere else later
 * (the panel has the same two actions).
 *
 * ## Three surfaces, one runner
 *
 * - `engineSection` is the block on the Settings screen: the path, the two versions, the
 *   two actions, and the picker.
 * - `engineActivity` is one strip, put on the page once, that says what a run is doing
 *   and how it ended. It exists because a run can be started from the Review screen too,
 *   and an action that takes a minute and reports nowhere is an action that silently does
 *   nothing.
 * - `run` is the only thing that starts the engine, wherever the button was.
 *
 * ## Why the shell does the work
 *
 * Nothing here looks at a filesystem or starts a process, because a page cannot.
 * `bridge.js` asks, `src-tauri/src/engine.rs` answers, and this file draws the answer.
 * That is also why it computes nothing: the version is the string the CLI printed, the
 * session count is the figure the engine's own ingest summary carried, and a "not ready"
 * reason is the engine's own sentence.
 */

import { emptyState } from "../design/components.js";
import { el } from "../design/dom.js";
import { sessions as sessionPhrase } from "../text/fmt.js";
import { t } from "../text/strings.js";
import { REVIEW_NOW } from "./review.js";
import * as Bridge from "../bridge.js";

/**
 * What the block and the runner ask the shell.
 *
 * Injected rather than imported directly so that a test can drive the whole block
 * against a fake engine, which is the only way to exercise "not found", "not ready" and
 * "it failed" without a machine in each of those states. `wireEngine` sets it to the
 * bridge.
 *
 * @typedef {{
 *   status: () => Promise<any>,
 *   run: (action: string, force: boolean) => Promise<any>,
 *   choose: () => Promise<any>,
 *   forget: () => Promise<any>,
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
    body.appendChild(emptyState(t("menu.engineMissing"), t("engine.notFound.detail")));
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

/** The reason a file that *was* found is not being used. */
function refusal(status) {
  const kind = String(status?.errorKind ?? "");
  // "not found" means two things. Here it means the chosen file is not executable; the
  // other meaning, nothing anywhere, is the empty state above.
  const said = kind === "notFound" ? t("engine.error.notExecutable") : t(`engine.error.${kind}`);
  return status?.error ? `${said} ${status.error}` : said;
}

function fill(body, status, state) {
  body.innerHTML = "";

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

  body.appendChild(actions(body, status, state));
}

function actions(body, status, state) {
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
  } else {
    // The search is cheap to repeat and the answer changes the moment the engine is
    // installed, so the way out of "not found" is not a relaunch.
    row.appendChild(action(t("common.tryAgain"), "", redraw));
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
        .then((choice) => (choice?.cancelled ? undefined : redraw()))
        .catch(redraw);
    })
  );

  if (status?.remembered) {
    row.appendChild(
      action(t("common.clear"), "plain", () => {
        const port = ENGINE.port;
        if (!port) return;
        port.forget().then(redraw).catch(redraw);
      })
    );
  }
  return row;
}

function action(label, variant, onClick) {
  const button = el("button", { class: `btn ${variant}`.trim(), type: "button", text: label });
  if (running) /** @type {any} */ (button).disabled = true;
  button.addEventListener("click", onClick);
  return button;
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
    announce([line(t("engine.busy")), button(t("common.dismiss"), "plain", clear)]);
    return Promise.resolve();
  }
  running = true;
  announce([line(action === "ingest" ? t("menu.ingesting") : t("menu.writingReview"))]);
  return port
    .run(action, Boolean(options?.force))
    .then((outcome) => {
      running = false;
      report(outcome);
    })
    .catch((error) => {
      running = false;
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
    const said = kind === "busy" ? t("engine.busy") : t(`engine.error.${kind}`);
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

/* --- the wiring ---------------------------------------------------------------------- */

/**
 * Point this module at the shell, put the strip on the page, and set the Review screen's
 * seam.
 *
 * Called once per page, from `window.html`, before the first draw. The panel does not
 * call it: its own two buttons are a later batch, and the panel sizes itself by measuring
 * its content, so a strip appended to its body would be measured.
 */
export function wireEngine() {
  ENGINE.port = {
    status: () => Bridge.engineStatus(),
    run: (action, force) => Bridge.runEngine(action, force),
    choose: () => Bridge.chooseEngine(),
    forget: () => Bridge.forgetEngine(),
  };
  // The Review screen's button. `review.js` exports the seam and refuses to invent a run
  // of its own, because a screen may not call the bridge.
  REVIEW_NOW.run = () => {
    run("review");
  };
  document.body.appendChild(engineActivity());
}
