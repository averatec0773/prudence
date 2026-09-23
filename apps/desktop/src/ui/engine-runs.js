/* What the engine recorded about its last runs, and the diagnosis: the Engine tab's two
 * cards under the engine block.
 *
 * ## Recent runs
 *
 * The last ten records of `<data dir>/logs/runs.jsonl`, newest first, whichever surface or
 * terminal started them: when, the command, how long it took or that it never finished,
 * the files it parsed and skipped, and its warnings and failed checks. Each row opens onto
 * what the engine wrote: every warning with its kind, count and sample, every failed check
 * with the numbers it compared, and the error. `src-tauri/src/runlog.rs` reads the file and
 * `store/runs.js` does the little arithmetic a row needs; every value is the engine's own.
 *
 * An engine older than the run log writes no file. The card is then not drawn at all, and
 * nothing says why: there is nothing the reader could do about it and nothing is wrong.
 *
 * ## Diagnosis
 *
 * `prudence diagnose` writes a folder an agent can read. The Diagnose label runs it through
 * the shell (the command is a constant in `runlog.rs`; the page never builds one), and the
 * folder it wrote is shown with a Reveal beside it. The folder is asked for by name, like
 * the About tab's links: no path crosses the bridge towards the shell.
 *
 * ## What this keeps between renders
 *
 * Which rows are open, and the diagnosis in hand: `prudence diagnose` asks the engine for
 * its status, the engine's read of the store moves the store's files, the watcher announces
 * a change, and this screen is rebuilt while the diagnosis is still running. The answer is
 * the shell's about a process, the same kind of thing `ui/activity.js` keeps, and a
 * rebuilt screen that forgot it would lose the folder the reader just asked for.
 */

import { panel } from "../design/components.js";
import { el } from "../design/dom.js";
import {
  commandLine,
  failedChecks,
  files,
  seconds,
  unended,
  warningCount,
  warningsOf,
} from "../store/runs.js";
import { count, decimal, stamp } from "../text/fmt.js";
import { plural, t } from "../text/strings.js";
import { ACTIVITY, failureSentence } from "./activity.js";

/** How many runs the card lists. */
export const LISTED = 10;

/**
 * What the two cards ask the shell. `ui/wiring.js` fills it in; a test sets a fake one.
 *
 * @typedef {{
 *   runs: (count: number) => Promise<any>,
 *   diagnose: () => Promise<any>,
 *   reveal: (name: string) => Promise<any>,
 * }} RunsPort
 *
 * @type {{ port: RunsPort | null }}
 */
export const RUNS = { port: null };

/** The rows open, by run id. Navigation, like the Settings screen's open tab. */
const opened = new Set();

/** The diagnosis: whether one is running, and how the last one ended. */
const diagnosis = {
  running: false,
  /** @type {any} */
  last: null,
  /** The area on screen now, so an answer that arrives after a rebuild lands in the
   *  tree the reader is looking at. @type {null | (() => void)} */
  draw: /** @type {null | (() => void)} */ (null),
};

/**
 * The two cards, for the Engine tab.
 *
 * @param {import("./screens.js").ScreenState} state
 * @returns {Element[]}
 */
export function engineRuns(state) {
  if (!RUNS.port) return [];
  return [recentRuns(), diagnose(state)];
}

/* --- recent runs --------------------------------------------------------------------- */

function recentRuns() {
  const holder = el("div", { class: "runs-holder" });
  holder.hidden = true;
  const fill = () => {
    RUNS.port
      ?.runs(LISTED)
      .then((answer) => draw(holder, answer))
      .catch(() => {
        holder.innerHTML = "";
        holder.appendChild(el("p", { class: "engine-note", text: t("runs.unread") }));
        holder.hidden = false;
      });
  };
  fill();
  // A run that ends without moving the store (a review declined, a run that failed) still
  // leaves a record; the screen is not rebuilt for it, so the card reads again itself.
  ACTIVITY.mounts.set("runs", (kind, before) => {
    if (kind === "state" && before.running && !ACTIVITY.now.running) fill();
  });
  return holder;
}

/**
 * @param {any} holder
 * @param {any} answer `{ runs, unreadable }` from the shell
 */
function draw(holder, answer) {
  holder.innerHTML = "";
  const runs = Array.isArray(answer?.runs) ? answer.runs : [];
  const unreadable = Number(answer?.unreadable ?? 0);
  if (!runs.length && !unreadable) {
    holder.hidden = true;
    return;
  }
  const body = el("div", { class: "run-list" });
  runs.forEach((run, index) => body.appendChild(entry(run, index === 0)));
  if (unreadable) {
    body.appendChild(
      el("p", { class: "engine-note", text: t("runs.unreadable", count(unreadable)) })
    );
  }
  holder.appendChild(
    panel({ title: t("runs.title"), note: t("runs.note"), body, method: t("runs.method") })
  );
  holder.hidden = false;
}

/** How long a run took, in the reader's words. */
function took(value) {
  if (value < 60) return t("runs.duration.seconds", decimal(value, value < 10 ? 1 : 0));
  const whole = Math.round(value);
  return t("runs.duration.minutes", count(Math.floor(whole / 60)), count(whole % 60));
}

/**
 * One run: a line that says what it was, opening onto what the engine wrote about it.
 *
 * A record still open is running only if it is the newest one and the shell says a run is
 * going; any other open record is a run that was interrupted.
 *
 * @param {any} run
 * @param {boolean} newest
 */
function entry(run, newest) {
  const open = unended(run);
  const going = open && newest && Boolean(ACTIVITY.now.running);
  const length = seconds(run);
  const when = open
    ? t(going ? "runs.running" : "runs.interrupted")
    : length === null
      ? t("common.dash")
      : took(length);

  const facts = [];
  const read = files(run);
  if (read) facts.push(t("runs.files", count(read.parsed), count(read.skipped)));
  const warnings = warningCount(run);
  if (warnings) facts.push(plural("runs.warnings", warnings, count(warnings)));
  const failed = failedChecks(run).length;
  if (failed) facts.push(plural("runs.failedChecks", failed, count(failed)));

  const summary = el("summary", { class: "run-summary" }, [
    el("span", { class: "run-when", text: stamp(run?.started_at) }),
    el("span", { class: "run-command", text: commandLine(run) }),
    el("span", { class: open && !going ? "run-took is-interrupted" : "run-took", text: when }),
  ]);
  if (facts.length) {
    summary.appendChild(
      el(
        "span",
        { class: warnings || failed ? "run-facts is-flagged" : "run-facts" },
        facts.map((text) => el("span", { text }))
      )
    );
  }

  const details = el("details", { class: "run-entry" }, [summary, ...recorded(run)]);
  const id = run?.run_id ? String(run.run_id) : null;
  if (id && opened.has(id)) /** @type {any} */ (details).open = true;
  details.addEventListener("toggle", () => {
    if (!id) return;
    if (/** @type {any} */ (details).open) opened.add(id);
    else opened.delete(id);
  });
  return details;
}

/** A value from the engine, as it wrote it: a string as it is, anything else as JSON. */
function asWritten(value) {
  if (value === null || value === undefined) return t("common.dash");
  return typeof value === "string" ? value : JSON.stringify(value);
}

/** A small table of the engine's own values. */
function table(columns, rows) {
  return el("table", { class: "data run-table" }, [
    el("thead", {}, [el("tr", {}, columns.map((text) => el("th", { text })))]),
    el(
      "tbody",
      {},
      rows.map((row) => el("tr", {}, row.map((text) => el("td", { text }))))
    ),
  ]);
}

/** What opens under a run: its warnings, its failed checks and its error. */
function recorded(run) {
  const nodes = [];
  const warnings = warningsOf(run);
  if (warnings.length) {
    nodes.push(el("h4", { class: "run-head", text: t("runs.warningsHead") }));
    nodes.push(
      table(
        [t("runs.column.kind"), t("runs.column.count"), t("runs.column.sample")],
        warnings.map((warning) => [
          String(warning?.kind ?? ""),
          count(Number(warning?.count ?? 0)),
          asWritten(warning?.sample),
        ])
      )
    );
  }
  const failed = failedChecks(run);
  if (failed.length) {
    nodes.push(el("h4", { class: "run-head", text: t("runs.checksHead") }));
    nodes.push(
      table(
        [t("runs.column.check"), t("runs.column.numbers")],
        failed.map((check) => [String(check?.name ?? ""), asWritten(check?.numbers)])
      )
    );
  }
  if (run?.error) {
    nodes.push(el("h4", { class: "run-head", text: t("runs.errorHead") }));
    // The engine's own words: its exception's type and message, English as it wrote them.
    const kind = run.error.type ? `${run.error.type}: ` : "";
    nodes.push(el("p", { class: "run-error", text: `${kind}${run.error.message ?? ""}` }));
  }
  if (!nodes.length) nodes.push(el("p", { class: "engine-note", text: t("runs.clean") }));
  return [el("div", { class: "run-recorded" }, nodes)];
}

/* --- the diagnosis ------------------------------------------------------------------- */

/** @param {import("./screens.js").ScreenState} state */
function diagnose(state) {
  const button = el("button", { class: "btn plain", type: "button", text: t("diagnose.action") });
  const said = el("div", { class: "diagnose-said" });
  button.addEventListener("click", () => start());

  const redraw = () => {
    /** @type {any} */ (button).disabled = diagnosis.running;
    said.innerHTML = "";
    const last = diagnosis.last;
    if (diagnosis.running) {
      said.appendChild(el("p", { class: "engine-line", text: t("diagnose.running") }));
    } else if (last?.path) {
      said.appendChild(
        el("div", { class: "fact" }, [
          el("div", { class: "fact-label", text: t("diagnose.written") }),
          el("div", { class: "fact-value is-path", text: String(last.path) }),
        ])
      );
      said.appendChild(
        el("div", { class: "engine-actions" }, [
          plain(t("diagnose.reveal"), () => RUNS.port?.reveal("diagnose")),
        ])
      );
    } else if (last) {
      said.appendChild(el("p", { class: "engine-line", text: t("diagnose.failed") }));
      said.appendChild(
        el("p", {
          class: "engine-line",
          text:
            last.errorKind === "noBundle"
              ? t("diagnose.noBundle")
              : failureSentence(String(last.errorKind ?? "")),
        })
      );
      // The engine's own words, as a failed run's are shown.
      if (last.error) said.appendChild(el("p", { class: "engine-said", text: String(last.error) }));
    }
  };
  diagnosis.draw = redraw;
  redraw();

  const body = el("div", { class: "fact-list" }, [
    el("div", { class: "engine-actions" }, [button]),
    said,
  ]);
  const logs = state.info?.logs;
  if (logs) {
    body.appendChild(el("p", { class: "engine-note", text: t("diagnose.logs", String(logs)) }));
    body.appendChild(
      el("div", { class: "engine-actions" }, [
        plain(t("diagnose.revealLogs"), () => RUNS.port?.reveal("logs")),
      ])
    );
  }
  return panel({ title: t("diagnose.title"), note: t("diagnose.note"), body });
}

function plain(label, onClick) {
  const node = el("button", { class: "btn plain", type: "button", text: label });
  node.addEventListener("click", onClick);
  return node;
}

/** Run `prudence diagnose` once, and say how it ended wherever the card is by then. */
function start() {
  const port = RUNS.port;
  if (!port || diagnosis.running) return;
  diagnosis.running = true;
  diagnosis.draw?.();
  port
    .diagnose()
    .then((answer) => {
      diagnosis.last = answer ?? null;
    })
    .catch((error) => {
      // The shell itself did not answer: said, not swallowed, in the card that asked.
      diagnosis.last = {
        errorKind: "failed",
        error: error instanceof Error ? error.message : String(error),
      };
    })
    .finally(() => {
      diagnosis.running = false;
      diagnosis.draw?.();
    });
}

/** Forget what is kept between renders. For a test, and for nothing else. */
export function forget() {
  opened.clear();
  diagnosis.running = false;
  diagnosis.last = null;
  diagnosis.draw = null;
}
