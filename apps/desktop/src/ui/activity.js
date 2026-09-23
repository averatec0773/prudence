/* What the engine is doing, on the window: the toolbar's two actions, the sidebar's status
 * row, and the report a run leaves when it needs the reader.
 *
 * ## One answer, from the shell
 *
 * A run can begin in the toolbar, in the panel, on the timer or in a terminal, and every
 * one of those has to show here. So the page does not keep its own idea of whether a run
 * is going: `src-tauri/src/activity.rs` keeps one, announces every change over
 * `engine-activity`, and answers `engine_activity` for a window drawn in the middle of a
 * run. `ACTIVITY.now` is that answer as it last arrived, and progress lines, which have an
 * event of their own, are folded into it as they come.
 *
 * ## Three places draw from it
 *
 * - `runActions`, the toolbar's right side: `Review now` and `Ingest now`, or while a run
 *   is going the run itself in their place, then how it ended for `OUTCOME_SHOWN`, then
 *   the two buttons again. The area has one declared size in every state, so nothing
 *   beside it moves and nothing under it grows.
 * - `statusRow`, the foot of the sidebar: when the store was last ingested, or the same
 *   run in its compact form, or the same outcome line. Reserved height, never grows.
 * - `runReport`, a card at the foot of the window for the two outcomes a line cannot
 *   carry: a failure in the engine's own words, and a review the engine declined, with
 *   the decision to write one anyway. It is the only one of the three that waits for the
 *   reader, and it reports only runs this window started.
 *
 * Each place is rebuilt whenever the window is (every store change redraws the whole
 * page), so each registers itself in `ACTIVITY.mounts` under its own name and the one
 * mounted last is the one that is told. A tree that has been replaced is never told again.
 *
 * ## Why the page may keep this
 *
 * The page contract forbids a screen to keep data between renders. This is not a screen
 * and it is not the store: it is the shell's answer about a process, the same kind of
 * thing `store/asked.js` keeps for the engine's answers, and a window rebuilt because an
 * ingest wrote the store must not forget that the ingest is still going.
 */

import { runProgress } from "../design/components.js";
import { el } from "../design/dom.js";
import { relative, sessions as sessionPhrase, stamp as timeStamp } from "../text/fmt.js";
import { t } from "../text/strings.js";

/** How long the outcome of a run is said in the toolbar and the status row before they
 *  go back to what they say when nothing is running. Long enough to read one line, short
 *  enough that the toolbar is not a notification. */
export const OUTCOME_SHOWN = 4000;

/** How often the status row's "13 hours ago" is said again while nothing moves the store.
 *  A relative time that is never redrawn is a figure that goes wrong while it is on
 *  screen; the store's own changes redraw it too, so this only covers the quiet hours. */
export const CLOCK = 60_000;

/**
 * What the toolbar asks the shell. `ui/wiring.js` fills it in; a test sets a fake one.
 *
 * @typedef {{
 *   read: () => Promise<any>,
 *   onActivity: (handler: (activity: any) => void) => Promise<() => void>,
 *   onProgress: (handler: (progress: any) => void) => Promise<() => void>,
 *   run: (action: string, force: boolean) => Promise<any>,
 * }} ActivityPort
 */

/** @typedef {{ running: string|null, outside: boolean, progress: any, outcome: any }} Activity */

/** @returns {Activity} */
function idle() {
  return { running: null, outside: false, progress: null, outcome: null };
}

export const ACTIVITY = {
  /** @type {ActivityPort | null} */
  port: null,
  /** The shell's answer, as it last arrived. */
  now: idle(),
  /** Until when the last run's outcome is said, in milliseconds since the epoch. Zero
   *  when there is nothing to say, which is also what a window opened after a run gets:
   *  an outcome is news only to somebody who saw the run end. */
  sayUntil: 0,
  /** @type {ReturnType<typeof setTimeout> | null} */
  lapse: null,
  /** Whoever draws from this, by place. `kind` is `state` for a run starting or ending
   *  and `progress` for a line inside one; only the first can change a screen.
   *  @type {Map<string, (kind: "state"|"progress", before: Activity) => void>} */
  mounts: new Map(),
};

/**
 * Which of its three states a place is in. A pure function of the answer and the clock,
 * so a test can ask it at any moment without waiting for one.
 *
 * @param {Activity} now
 * @param {number} sayUntil
 * @param {number} at
 * @returns {"running"|"outcome"|"idle"}
 */
export function phase(now, sayUntil, at) {
  if (now.running) return "running";
  if (now.outcome && at < sayUntil) return "outcome";
  return "idle";
}

/** Whether an ingest is going, from anywhere. The Overview says so in its summary line. */
export function ingesting() {
  return ACTIVITY.now.running === "ingest";
}

function tell(kind, before) {
  for (const draw of ACTIVITY.mounts.values()) draw(kind, before);
}

/**
 * Take the shell's answer.
 *
 * A run that has just ended is the one moment an outcome is news, so that is the only
 * moment the clock for saying it starts. The same answer read by a window opened a minute
 * later carries the same outcome and says nothing about it.
 *
 * @param {Partial<Activity>} next
 * @param {number} [at]
 */
export function take(next, at = Date.now()) {
  const before = ACTIVITY.now;
  ACTIVITY.now = { ...idle(), ...next };
  if (before.running && !ACTIVITY.now.running && ACTIVITY.now.outcome) {
    ACTIVITY.sayUntil = at + OUTCOME_SHOWN;
    if (ACTIVITY.lapse) clearTimeout(ACTIVITY.lapse);
    ACTIVITY.lapse = setTimeout(() => {
      ACTIVITY.lapse = null;
      tell("state", ACTIVITY.now);
    }, OUTCOME_SHOWN);
  }
  if (ACTIVITY.now.running) ACTIVITY.sayUntil = 0;
  tell("state", before);
}

/** One progress line of the run in hand. A line arriving with no run in hand belongs to a
 *  run whose start this page has not heard of yet, and the answer that follows it says. */
export function progressed(progress) {
  if (!ACTIVITY.now.running) return;
  const before = ACTIVITY.now;
  ACTIVITY.now = { ...ACTIVITY.now, progress };
  tell("progress", before);
}

/**
 * Listen to the shell, and ask it once what is going on already. Called by the wiring,
 * once per page that has a shell behind it.
 *
 * The port's three calls settle rather than reject: `ui/wiring.js` writes a refusal to the
 * shell's standard error, which is where the page's failures go, and an answer that could
 * not be read leaves the page as idle as it started.
 */
export function follow() {
  const port = ACTIVITY.port;
  if (!port) return;
  port.onActivity((next) => take(next));
  port.onProgress((progress) => progressed(progress));
  port.read().then((next) => take(next ?? {}));
}

/** Say the status row's relative time again. The window calls this every `CLOCK`. */
export function tick() {
  ACTIVITY.mounts.get("status")?.("state", ACTIVITY.now);
}

/* --- what a run is, in words ---------------------------------------------------------- */

/** A run that counts nothing, said in one line in the place a bar would go. */
function runLabel(text) {
  return el("div", { class: "progress is-compact" }, [
    el("div", { class: "progress-head" }, [el("span", { class: "progress-label", text })]),
  ]);
}

/**
 * The run in hand, compact: the step and the engine's count over a thin bar for an
 * ingest this app started, and a line for everything that counts nothing it can see.
 *
 * @param {Activity} now
 */
function running(now) {
  if (now.outside) return runLabel(t("activity.outside"));
  if (now.running === "review") return runLabel(t("menu.writingReview"));
  // Before the first line the engine is reading its repositories and has nothing to
  // count; `runProgress` draws that as the label over an empty track, which is the truth.
  const bar = runProgress(now.progress ?? { label: t("menu.ingesting") });
  bar.classList.add("is-compact");
  return bar;
}

/**
 * How a run ended, as one short line and the long form under the pointer.
 *
 * The short forms are the ones the panel already says. The long form is the engine's own
 * figure or words: the session count, the reason a review was declined, the failure.
 *
 * @param {any} outcome
 * @returns {[string, string|null]}
 */
export function outcomeWords(outcome) {
  if (outcome?.errorKind === "busy") return [t("engine.busy"), null];
  if (outcome?.errorKind) return [t("engine.failed.title"), outcome.error ?? null];
  if (outcome?.notReady) return [t("review.notReady.title"), outcome.reason ?? null];
  if (outcome?.action === "review") {
    return [
      outcome.reviewId === null || outcome.reviewId === undefined
        ? t("menu.reviewWritten")
        : t("menu.reviewWrittenId", String(outcome.reviewId)),
      null,
    ];
  }
  return [
    t("menu.ingestFinished"),
    outcome?.sessions === null || outcome?.sessions === undefined
      ? null
      : t("engine.ingestFinished.sessions", sessionPhrase(Number(outcome.sessions))),
  ];
}

function outcomeLine(outcome) {
  const [short, long] = outcomeWords(outcome);
  const line = el("div", { class: "run-outcome", text: short });
  if (long) line.title = long;
  return line;
}

/* --- the toolbar ---------------------------------------------------------------------- */

/**
 * `Review now` and `Ingest now`, with the same words the panel uses.
 *
 * While any run is going both give way to it: the shell refuses a second run, so two
 * buttons beside a bar would be two things that cannot be pressed. The run takes the
 * whole area, which has one width in every state, so the primary is replaced in place and
 * the button beside it does not slide.
 */
export function runActions() {
  const root = el("div", { class: "run-actions" });

  const draw = () => {
    root.innerHTML = "";
    const at = phase(ACTIVITY.now, ACTIVITY.sayUntil, Date.now());
    if (at === "running") {
      root.appendChild(running(ACTIVITY.now));
      return;
    }
    if (at === "outcome") {
      root.appendChild(outcomeLine(ACTIVITY.now.outcome));
      return;
    }
    const review = el("button", { class: "btn", type: "button", text: t("menu.reviewNow") });
    review.addEventListener("click", () => runNow("review"));
    const ingest = el("button", { class: "btn primary", type: "button", text: t("menu.ingestNow") });
    ingest.addEventListener("click", () => runNow("ingest"));
    root.appendChild(review);
    root.appendChild(ingest);
  };

  ACTIVITY.mounts.set("toolbar", draw);
  draw();
  return root;
}

/* --- the status row ------------------------------------------------------------------- */

/** When the store was last ingested, in the reader's words: `Last ingest 13h ago`, in the
 *  narrow form, because the whole line has a sidebar's width. The full stamp is on the
 *  pointer. */
function lastIngest(stamp) {
  const line = el("div", {
    class: "run-outcome is-idle",
    text: stamp
      ? t("activity.lastIngest", relative(stamp, undefined, undefined, "narrow"))
      : t("activity.neverIngested"),
  });
  if (stamp) line.title = t("common.dateWithRelative", timeStamp(stamp), relative(stamp));
  return line;
}

/**
 * The foot of the sidebar: the last ingest, a run while one goes, its outcome for a moment.
 *
 * @param {any} data the payload, for `app_status.last_ingest_at`
 */
export function statusRow(data) {
  const root = el("div", { class: "status-row", role: "status" });

  const draw = () => {
    root.innerHTML = "";
    const at = phase(ACTIVITY.now, ACTIVITY.sayUntil, Date.now());
    if (at === "running") root.appendChild(running(ACTIVITY.now));
    else if (at === "outcome") root.appendChild(outcomeLine(ACTIVITY.now.outcome));
    else root.appendChild(lastIngest(data?.status?.last_ingest_at));
  };

  ACTIVITY.mounts.set("status", draw);
  draw();
  return root;
}

/* --- starting one, and the report that waits for the reader ------------------------- */

/** The card currently on the page, or nothing. One per page; see `runReport`. */
let card = /** @type {any} */ (null);

/**
 * The card a run leaves when a line is not enough. Put on the page once by the wiring,
 * because a run outlives the screen it was started on.
 *
 * @returns {Element}
 */
export function runReport() {
  card = el("div", { class: "run-report" });
  card.hidden = true;
  return card;
}

function clear() {
  if (!card) return;
  card.innerHTML = "";
  card.hidden = true;
}

/** @param {Element[]} nodes */
function report(nodes) {
  if (!card) return;
  card.innerHTML = "";
  for (const node of nodes) card.appendChild(node);
  card.hidden = false;
}

function said(text) {
  return el("p", { class: "run-said", text });
}

function button(label, variant, onClick) {
  const node = el("button", { class: `btn ${variant}`.trim(), type: "button", text: label });
  node.addEventListener("click", onClick);
  return node;
}

/**
 * The sentence for a failure kind, with no way to reach a key that is not there.
 *
 * Every kind the shell can send is named here. A kind this build has never heard of gets
 * the general sentence rather than its own name, because a reader should never be shown
 * an identifier.
 */
export function failureSentence(kind) {
  // `busy` and `notFound` have their own sentences elsewhere in the catalogue: "a run is
  // already going", and the general "the engine is not there", which is a different
  // statement from a file that will not say what it is.
  if (kind === "busy") return t("engine.busy");
  if (kind === "notFound") return t("menu.engineMissing");
  // `EngineError::kind()` can return exactly `notFound`, `launch`, `failed`, `noVersion`
  // and `busy`; `notExecutable` is the sentence for a file found and refused.
  const known = ["notExecutable", "noVersion", "launch", "failed"];
  return known.includes(kind) ? t(`engine.error.${kind}`) : t("engine.failed.detail");
}

function message(error) {
  return error instanceof Error ? error.message : String(error);
}

/**
 * What the engine said, where a line is not enough: its failure, or its refusal to write a
 * review, with the decision that is the reader's to make. Anything else has been said in
 * the toolbar and the status row already, and the card goes.
 */
function explain(outcome) {
  if (outcome?.errorKind) {
    const nodes = [said(t("engine.failed.title")), said(failureSentence(String(outcome.errorKind)))];
    // The engine's own words, as `store.rs`'s errors are shown as they come.
    if (outcome.error) nodes.push(said(String(outcome.error)));
    nodes.push(button(t("common.dismiss"), "plain", clear));
    report(nodes);
    return;
  }
  if (outcome?.notReady) {
    // `--force` is the only way past the engine's readiness rule, and that is the
    // reader's decision to make, not the app's.
    report([
      said(t("review.notReady.title")),
      // The engine's own sentence, printed as it came: it names the counts and the
      // thresholds, and rewording it would make the app and the CLI disagree.
      said(String(outcome.reason ?? t("menu.reviewNotReady"))),
      button(t("review.writeAnyway"), "primary", () => runNow("review", { force: true })),
      button(t("common.cancel"), "plain", clear),
    ]);
    return;
  }
  clear();
}

/**
 * Start a run from this window.
 *
 * What it is doing reaches the toolbar and the status row from the shell, as every run's
 * does; what this adds is the report above, for the two outcomes that need the reader.
 * Nothing is plumbed into the screens: the shell watches the store and every page follows
 * it when the run lands.
 *
 * @param {"ingest"|"review"} action
 * @param {{ force?: boolean }} [options]
 * @returns {Promise<void>}
 */
export function runNow(action, options) {
  const port = ACTIVITY.port;
  if (!port) {
    report([said(t("menu.engineMissing")), said(t("engine.notFound.detail"))]);
    return Promise.resolve();
  }
  clear();
  return port
    .run(action, Boolean(options?.force))
    .then(explain)
    .catch((error) => {
      // The shell itself did not answer. Not the engine's failure, and it still has to be
      // said: a swallowed rejection here is a run that silently did nothing.
      report([
        said(t("engine.failed.title")),
        said(message(error)),
        button(t("common.dismiss"), "plain", clear),
      ]);
    });
}
