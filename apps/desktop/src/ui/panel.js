/* The menu bar panel: one column, a caption above every block, the actions at the foot.
 *
 * The variant the founder settled on (M4 plan, "Variant choices", and their clarification
 * the next day: content in the centre, not titles left and values right).
 *
 * Nothing in this file knows it is inside a Tauri window.
 */

import * as Bridge from "../bridge.js";
import * as Measure from "../measure.js";
import { miniStack } from "../design/charts.js";
import { runProgress } from "../design/components.js";
import { el } from "../design/dom.js";
import { mark } from "../design/brand.js";
import { BUCKETS, bucketColour } from "../design/buckets.js";
import {
  bucket,
  hourPhrase,
  list,
  listSeparator,
  percent,
  projects,
  rangeName,
  sessions,
  commits,
  tokenPhrase,
  day,
} from "../text/fmt.js";
import {
  observationCaveat,
  observationSentence,
  readinessSentence,
  readinessSource,
  reviewLine,
  stampedAgo,
} from "../text/sentences.js";
import { PRODUCT_NAME, t } from "../text/strings.js";
import { bucketShares, daysWindow, today } from "../store/payload.js";
import { readiness } from "../store/readiness.js";

/** Set by `render`, so the size report can run again when the content changes. `why` is
 *  what asked for it, which is only ever read by a harness build's timing log. */
let refit = /** @type {(why?: string) => number|undefined} */ (() => undefined);

/**
 * The panel's own range choices: a day count and the catalogue key for its label.
 *
 * Distinct from the window's seven ranges (`store/overview.js`): this block draws no
 * chart, so there is no reason for a bucket to become a week past sixty days, and 60
 * days, 365 days and "all" are not questions asked here. Every choice is the same rule
 * this block always summed under its one fixed name ("Last 7 days"): a local day, today
 * and the ones before it (`store/payload.js`, `daysWindow`).
 */
const PANEL_RANGES = [
  { key: "1d", days: 1 },
  { key: "7d", days: 7 },
  { key: "30d", days: 30 },
  { key: "90d", days: 90 },
];

const DEFAULT_PANEL_RANGE = "7d";

function panelRangeOf(key) {
  return PANEL_RANGES.find((range) => range.key === key) ?? panelRangeOf(DEFAULT_PANEL_RANGE);
}

/**
 * Which range the block is drawn over.
 *
 * Remembered here for the session, the same way `PANEL_RUN` outlives a redraw the store
 * watcher causes: `render` runs again on every store change, and a choice made mid-session
 * must not be thrown back to whatever the shell answered at boot. `restored` is flipped
 * once `render` has read `info.panel_range`, the one time this is allowed to move without
 * a click; a test resets both, the same way it resets `PANEL_RUN`.
 */
export const PANEL_RANGE = { key: DEFAULT_PANEL_RANGE, restored: false };

function text(content, className) {
  return el("span", { class: className ?? "", text: content });
}

/** A caption on its own line and the content full width under it. */
function block(caption, node) {
  return el("div", { class: "pop-block" }, [el("span", { class: "k", text: caption }), node]);
}

/**
 * The head: what this is, what it is over, and what wrote the store.
 *
 * **The scope is the answer to "what are these figures about?"** Every number on the panel
 * is the whole store, all projects, and nothing said so: a reader with three repositories
 * recorded had no way to know that from here. It is the same list the window's project
 * picker offers, which is the projects the store has sessions for.
 */
function head(data) {
  const bar = el("div", { class: "pop-head" });
  const brand = mark(18);
  brand.classList.add("brand-mark");
  bar.appendChild(brand);
  bar.appendChild(el("span", { class: "name", text: PRODUCT_NAME }));
  bar.appendChild(
    el("span", { class: "scope-count", text: projects((data.projects ?? []).length) })
  );
  bar.appendChild(
    el("span", { class: "ver", text: `prudence ${data.status?.engine_version ?? ""}` })
  );
  return bar;
}

function todayBlock(data) {
  const now = today(data);
  const counted = now.sessions > 0 || now.commits > 0;
  const wrap = el("div");
  wrap.appendChild(
    el("div", {
      class: counted ? "headline" : "obs-line",
      text: counted ? list([sessions(now.sessions), commits(now.commits)]) : t("menu.noSessionsToday"),
    })
  );
  wrap.appendChild(el("div", { class: "headline-sub", text: day(now.day) }));
  return wrap;
}

/** "Today", or "Last 7 days" / "Last 30 days" / "Last 90 days": the caption keeps naming
 *  the range in force, the same words the picker beside it offers. */
function rangeCaption(range) {
  return range.days === 1 ? t("menu.today") : t("menu.lastRangeDays", rangeName(range));
}

/**
 * What the replies did over a range, in words, the same mix as a bar, and the totals.
 *
 * **The sentence is the legend.** It used to be stated in words, drawn as a bar, and then
 * named a third time by a swatch legend under it: three rows for one fact in a 360 pt
 * window. Each bucket's own colour goes on its name where the name already is ("change
 * 40%, run 33%, read 20%, talk 7%"), which is what makes the bar readable and returns a
 * row. Colour is identity here, as it is everywhere: it says which bucket this is and
 * never whether a share is good.
 *
 * One range among four (`PANEL_RANGES`); `rangeSection` below is what lets the reader
 * choose which, and calls this again for whichever they picked.
 */
function rangeBody(data, range) {
  const week = daysWindow(data, range.days);
  const shares = bucketShares(week);
  const summary = shares.length
    ? list(shares.map((part) => `${bucket(part.bucket)} ${percent(part.share)}`))
    : range.days === 1
      ? t("menu.noTokensToday")
      : t("menu.noTokensInRange", rangeName(range));

  const wrap = el("div", { class: "week-row" });

  const line = el("div", { class: "obs-line" });
  if (!shares.length) {
    line.appendChild(document.createTextNode(summary));
  } else {
    shares.forEach((part, index) => {
      if (index) line.appendChild(document.createTextNode(listSeparator()));
      const named = el("span", { class: "bucket-name", text: bucket(part.bucket) });
      named.style.color = bucketColour(part.bucket);
      line.appendChild(named);
      // A space between a name and its figure is not punctuation the language chooses, so
      // it is part of the figure's own element rather than a bare text node in between.
      line.appendChild(el("span", { class: "bucket-share", text: ` ${percent(part.share)}` }));
    });
  }
  wrap.appendChild(line);

  wrap.appendChild(
    miniStack({
      parts: BUCKETS.map((key) => ({ value: week.byBucket[key], colour: bucketColour(key) })),
      // The whole range, so tokens in a bucket this build does not know stay as unfilled
      // track rather than being shared out among the four.
      total: week.total,
      height: 8,
      caption: `${rangeCaption(range)}: ${summary} (${tokenPhrase(week.total)}, ${sessions(week.sessions)})`,
    })
  );
  if (week.total) {
    wrap.appendChild(
      el("div", { class: "week-figures" }, [
        text(tokenPhrase(week.total)),
        text(sessions(week.sessions)),
        text(hourPhrase(week.hours)),
      ])
    );
  }

  return wrap;
}

/**
 * The block's caption row and the range block itself: the caption naming the range in
 * force on the left, the picker on the right, one click switching the sentence, the bar
 * and the numbers under it.
 *
 * **The picker's own row never changes shape.** All four choices are drawn at first
 * paint, plain labels of the app's own quiet button (`.btn.plain`, `DESIGN.md`'s "the
 * plain button is quiet ink with the accent only under the pointer"), the chosen one in
 * ink and the rest quiet; a click only ever changes which one is ink, so the row this
 * caption sits on is exactly as tall after a switch as before it, and nothing about it
 * ever has to be reserved the way the two late rows in the footer are.
 */
function rangeSection(data) {
  const caption = el("span", { class: "k", text: "" });
  const body = el("div");
  const picker = el("div", { class: "range-choices", role: "radiogroup", "aria-label": t("scope.range") });

  /** @type {{ button: HTMLElement, range: { key: string, days: number } }[]} */
  const choices = [];

  function paint() {
    const range = panelRangeOf(PANEL_RANGE.key);
    caption.textContent = rangeCaption(range);
    for (const { button, range: choice } of choices) {
      const chosen = choice.key === PANEL_RANGE.key;
      button.className = `btn plain range-choice${chosen ? " is-chosen" : ""}`;
      button.setAttribute("aria-checked", String(chosen));
    }
    body.innerHTML = "";
    body.appendChild(rangeBody(data, range));
    refit("range");
  }

  PANEL_RANGES.forEach((range, index) => {
    if (index) picker.appendChild(el("span", { class: "range-sep", text: " · " }));
    const button = el("button", {
      class: "btn plain range-choice",
      type: "button",
      role: "radio",
      text: range.days === 1 ? t("menu.today") : rangeName(range),
    });
    // No guard against re-clicking the range already chosen: `ui/window.js`'s own range
    // picker sets and redraws unconditionally too, and a button that sometimes does
    // nothing is the one thing "no surface may leave a button wired to nothing"
    // (`test/panel.test.mjs`) exists to catch.
    button.addEventListener("click", () => {
      PANEL_RANGE.key = range.key;
      if (Bridge.attached()) Bridge.setPanelRange(range.key).catch(() => {});
      paint();
    });
    choices.push({ button, range });
    picker.appendChild(button);
  });

  paint();

  return el("div", { class: "pop-block" }, [
    el("div", { class: "pop-block-head" }, [caption, picker]),
    body,
  ]);
}

function observationBlock(data) {
  const row = data.observations[0];
  if (!row) return text(t("menu.noObservation"), "obs-line");
  const wrap = el("div");
  wrap.appendChild(text(observationSentence(row), "obs-sentence"));
  wrap.appendChild(el("div", { class: "coverage-chip", text: observationCaveat(row) }));
  return wrap;
}

/* --- the two actions ------------------------------------------------------------------
 *
 * ## Why the placeholder survived the delivery
 *
 * The panel's Ingest now and Review now printed "arrives with the engine wiring, in batch
 * 7" until this batch, and batch 7 shipped. The wiring was written and placed on the
 * **window**: `ui/engine-section.js` owned the run and the report then (`ui/activity.js`
 * does now), and `window.html` calls the wiring. Nothing calls it for `index.html`, so the panel kept the note.
 *
 * It survived because every check the batch had was a check of the window. The Rust tests
 * spawn the engine, the bridge test pins the command names, and the harness can press a
 * button by its label, but `PRUDENCE_PRESS` is handed to the page through `shell_info`
 * and read by `ui/window.js`, which the panel is not. The panel's own test renders it and
 * asserts what it draws, and what it drew was a button with the right label on it. A
 * button that is there and does nothing passes every one of those.
 *
 * The guard is the last test in `test/panel.test.mjs`: **no surface may leave a button
 * wired to nothing**. It renders the panel, presses each of the four buttons against a
 * fake shell, and asserts that each one reached it. A label with no call behind it fails
 * it, whichever surface grows the next one.
 *
 * ## What is drawn while a run is going
 *
 * The note's place carries one of two things: a sentence, which is what a run's outcome
 * and every refusal is, or the progress bar, which is what the engine is doing right now.
 * `note()` and `showProgress()` are the only two things that write it, and both re-measure
 * the panel afterwards, because the window is only as tall as its content.
 *
 * The last event is kept in `PANEL_RUN.at` on purpose. `render` runs again whenever the
 * store changes, which an ingest does several times while it is working, and a redraw
 * would otherwise leave the bar blank until the engine happened to count something else.
 */

/**
 * What the panel asks the shell, and whether a run is going.
 *
 * `port` is null in the app and is the bridge by default; a test sets it to a fake shell,
 * which is the only way to press these two buttons under `node --test`. The panel does
 * **not** use the window's runner (`ui/activity.js`): that one reports in a toolbar, a
 * sidebar and a card appended to the document body, and the panel measures its own
 * content to size its window, so a card in it would be measured into its height.
 *
 * @typedef {{
 *   run: (action: "ingest"|"review") => Promise<any>,
 *   onProgress?: (handler: (progress: any) => void) => Promise<() => void>,
 *   readiness?: () => Promise<any>,
 * }} PanelPort
 * @type {{ port: PanelPort | null, running: string | null, at: any }}
 */
export const PANEL_RUN = { port: null, running: null, at: null };

/** The fake shell a test injected, the real one, or nothing at all. */
function runner() {
  if (PANEL_RUN.port) return PANEL_RUN.port;
  if (!Bridge.attached()) return null;
  return {
    run: (action) => Bridge.runEngine(action, false),
    onProgress: (handler) => Bridge.onEngineProgress(handler),
    readiness: () => Bridge.engineReadiness(),
  };
}

/** Every button a run disables, in the tree currently on screen. */
const actionButtons = new Set();

/**
 * The one line under the buttons: how a run ended, or why it did not start.
 *
 * It re-measures, because the line is content and the window is only as tall as its
 * content.
 */
function note(text) {
  const line = document.getElementById("pop-note");
  if (!line) return;
  PANEL_RUN.at = null;
  line.className = "coverage-chip";
  line.textContent = text ?? "";
  if (text) {
    // On the shell's standard error as well, for the same reason `page_log` exists at
    // all: a menu bar app has no console anybody is watching, and this line is the only
    // report a run started from the panel makes. Only where there is a shell to say it
    // to: the page is opened in a browser while layout is worked on, and under a test.
    if (Bridge.attached()) Bridge.log(`panel: ${text}`);
  }
  refit("note");
}

/**
 * What the engine is doing, in the place the note occupies.
 *
 * The bar itself is `design/components.js`'s, the same one the window's toolbar draws, and the
 * event is the engine's own: this function chooses nothing and computes nothing.
 *
 * @param {any} progress one `engine-progress` payload
 */
function showProgress(progress) {
  PANEL_RUN.at = progress;
  const line = document.getElementById("pop-note");
  if (!line) return;
  line.className = "pop-progress";
  line.innerHTML = "";
  line.appendChild(runProgress(progress));
  line.hidden = false;
  if (Bridge.attached()) {
    Bridge.log(
      `panel: ${progress.step} ${progress.current}/${progress.total} ${progress.unit}` +
        ` (step ${progress.stepIndex} of ${progress.steps})`
    );
  }
  refit("progress");
}

function setRunning(action) {
  PANEL_RUN.running = action;
  for (const button of actionButtons) /** @type {any} */ (button).disabled = Boolean(action);
}

/**
 * Start a run from the panel, and report it in the panel.
 *
 * The same two engine actions the window's toolbar runs, through the same shell
 * command. The outcome sentence is the engine's own answer, said in the reader's
 * language, which is the same set of sentences `ui/activity.js` says.
 *
 * @param {"ingest"|"review"} action
 */
function run(action) {
  const port = runner();
  if (!port) {
    note(t("engine.noShell.detail"));
    return;
  }
  if (PANEL_RUN.running) {
    note(t("engine.busy"));
    return;
  }
  setRunning(action);
  // Said before the first event arrives, and replaced by the bar as soon as one does: the
  // engine reads its repositories before it can count anything, and a surface that says
  // nothing at all for that second is a surface that looks as if the button did nothing.
  note(action === "ingest" ? t("menu.ingesting") : t("menu.writingReview"));

  let stop = /** @type {(() => void) | null} */ (null);
  // Only while this panel's own run is going. A timed ingest is announced to both pages,
  // and a bar under buttons that are not disabled would be a lie about what the reader
  // can do next.
  const listening = port.onProgress?.((progress) => {
    if (PANEL_RUN.running) showProgress(progress);
  });
  if (listening) {
    listening
      .then((off) => {
        stop = off;
      })
      .catch(() => {});
  }

  port
    .run(action)
    .then((outcome) => {
      setRunning(null);
      stop?.();
      note(outcomeLine(action, outcome));
    })
    .catch((error) => {
      setRunning(null);
      stop?.();
      note(error instanceof Error ? error.message : String(error));
    });
}

/** The engine's own answer, as one line. The panel has room for one. */
function outcomeLine(action, outcome) {
  if (outcome?.errorKind === "busy") return t("engine.busy");
  if (outcome?.errorKind) return t("engine.failed.title");
  // The engine declined. Its own sentence names the counts and the thresholds, and the
  // way past it is `--force`, which is a decision the window's strip offers and the panel
  // does not: a popover is not where somebody overrides a readiness rule.
  if (outcome?.notReady) return String(outcome.reason ?? t("menu.reviewNotReady"));
  if (action === "review") {
    return outcome?.reviewId === null || outcome?.reviewId === undefined
      ? t("menu.reviewWritten")
      : t("menu.reviewWrittenId", String(outcome.reviewId));
  }
  return outcome?.sessions === null || outcome?.sessions === undefined
    ? t("menu.ingestFinished")
    : t("engine.ingestFinished.sessions", sessions(Number(outcome.sessions)));
}

/** A button that a run disables and a run's end brings back. */
function actionButton(label, onClick) {
  const button = el("button", { class: "btn", type: "button", text: label });
  button.addEventListener("click", onClick);
  actionButtons.add(button);
  /** @type {any} */ (button).disabled = Boolean(PANEL_RUN.running);
  return button;
}

/** The button grid: the primary full width, two equal cells under it, and one baseline
 *  carrying the two quiet actions out to the block's own edges. */
function footer(data) {
  // The buttons about to be replaced are gone; the new ones register themselves.
  actionButtons.clear();

  const open = el("button", { class: "btn primary wide", type: "button", text: t("menu.openPrudence") });
  const review = actionButton(t("menu.reviewNow"), () => run("review"));
  const ingest = actionButton(t("menu.ingestNow"), () => run("ingest"));
  const settings = el("button", { class: "btn plain", type: "button", text: t("menu.settings") });
  const quit = el("button", { class: "btn plain", type: "button", text: t("menu.quit") });

  open.addEventListener("click", () => Bridge.openWindow());
  settings.addEventListener("click", () => Bridge.openWindow());
  quit.addEventListener("click", () => Bridge.quit());

  /* Both of these rows are **reserved, never revealed**.
   *
   * They were hidden at first draw and shown when something arrived, and the readiness one
   * arrives from a subprocess a moment after the panel has been shown and anchored. The
   * panel is only as tall as its content, so the window was re-measured and re-anchored
   * under the status item while the reader was looking at it: 635 px at render and 677 px
   * a second later, measured on 2026-09-22.
   *
   * So the slots are in the layout from the first paint, at the height their answer needs
   * (`app.css`), and filling one changes no node and no height. An empty one draws nothing
   * at all: `.coverage-chip:empty` is what keeps a capsule from sitting there with nothing
   * in it. `refit` still runs, because a sentence longer than the slot must grow the window
   * rather than be cut off; it reports the height it already reported.
   */
  const line = el("div", { class: "coverage-chip", text: "" });
  line.id = "pop-note";

  // Whether a review is ready, beside the button that writes one, in the reader's words
  // from the engine's numbers, with the engine's own sentence under the pointer.
  //
  // Through `store/readiness.js`, which decides when the engine is asked at all. Asking on
  // every draw closes a loop with the store watcher, and that file holds the whole story.
  const ready = el("div", { class: "coverage-chip", text: "" });
  ready.id = "pop-ready";
  const port = runner();
  if (port?.readiness) {
    readiness(data, () => port.readiness())
      .then((found) => {
        // No answer is no line rather than a guess: the engine that carries no readiness
        // block has said nothing, and "not ready" would be this app inventing a verdict.
        const said = readinessSentence(found);
        if (!said) return;
        ready.textContent = said;
        ready.title = readinessSource(found);
        refit("readiness");
      })
      .catch(() => {});
  }

  return el("div", { class: "pop-foot" }, [
    el("div", { class: "pop-reserve" }, [line]),
    el("div", { class: "pop-reserve is-readiness" }, [ready]),
    open,
    el("div", { class: "buttons-row" }, [review, ingest]),
    el("div", { class: "buttons-row spread" }, [settings, quit]),
  ]);
}

/** Attached once: `render` runs again on every store change, and clearing the DOM does
 *  not clear listeners on `document` and `window`. */
let listening = false;
/** @type {(() => void) | null} */
let arriving = null;

/** A button a script asked to have pressed. Once, not on every store change: `render` runs
 *  again whenever an ingest lands, and a press without this guard would start the next one.
 *  `info.press` is null in a release build, so none of this is reachable by a user. */
let pressed = false;

function pressOnce(label) {
  for (const button of document.querySelectorAll("button")) {
    if ((button.textContent ?? "").trim() === label) {
      /** @type {HTMLElement} */ (button).click();
      return true;
    }
  }
  return false;
}

export const page = {
  name: "panel",
  /** @param {HTMLElement} container */
  render(container, { data, info }) {
    // Restored once, the first time this build hears from the shell; a choice made
    // mid-session (`rangeSection`'s `paint`) is not this app's to overwrite on the next
    // store change, which is the only other thing that calls `render` again.
    if (!PANEL_RANGE.restored) {
      const remembered = info?.panel_range;
      PANEL_RANGE.key = PANEL_RANGES.some((range) => range.key === remembered)
        ? remembered
        : DEFAULT_PANEL_RANGE;
      PANEL_RANGE.restored = true;
    }

    const pop = el("div", { class: "popover" }, [head(data)]);

    const body = el("div", { class: "pop-body" }, [
      block(t("menu.today"), todayBlock(data)),
      rangeSection(data),
      el("div", { class: "pop-sep" }),
      block(t("menu.latestObservation"), observationBlock(data)),
      el("div", { class: "pop-sep" }),
      block(t("menu.lastIngest"), text(stampedAgo(data.status?.last_ingest_at), "obs-line")),
      block(
        t("menu.lastReview"),
        text(data.reviews[0] ? reviewLine(data.reviews[0]) : t("menu.noReview"), "obs-line")
      ),
    ]);

    pop.appendChild(body);
    pop.appendChild(footer(data));

    container.innerHTML = "";
    container.appendChild(pop);

    /* A popover is as tall as what is in it. The stretch that pins the footer to the
       bottom is lifted for one measurement, or the window's own height is what gets
       measured and the panel can only ever grow. */
    refit = (why) => {
      if (!Bridge.attached()) return;
      const started = Measure.at();
      const stretch = pop.style.minHeight;
      pop.style.minHeight = "0";
      const height = Math.ceil(pop.getBoundingClientRect().height);
      pop.style.minHeight = stretch;
      if (height > 0) Bridge.fitPanel(360, height);
      Measure.say(`panel refit (${why ?? "?"}): ${height} px, ${Measure.since(started)} ms`);
      return height;
    };
    refit("render");

    /* A run outlives this tree. An ingest announces itself to the store watcher several
       times while it works, and every announcement redraws the panel, which builds a new
       empty note: without this the bar vanished part-way through the run it was drawn for
       and came back at the next event, which on the `parse` step can be seconds later. */
    if (PANEL_RUN.running) {
      if (PANEL_RUN.at) showProgress(PANEL_RUN.at);
      else note(PANEL_RUN.running === "ingest" ? t("menu.ingesting") : t("menu.writingReview"));
    }

    /* The shell focuses the panel when it shows it, which is the only signal the page
       gets that it went from hidden to visible. The class is removed when the animation
       ends so the next show replays it.

       `arrive` is re-bound each render because it closes over this render's `pop`; the
       listeners are attached once, because `render` runs again on every store change and
       `document` and `window` outlive the DOM this function just replaced. */
    arriving = () => {
      pop.classList.remove("is-arriving");
      // Reading a layout property between the two lines is what makes the browser start
      // the animation again instead of treating it as unchanged.
      void pop.offsetWidth;
      pop.classList.add("is-arriving");
    };
    pop.addEventListener("animationend", () => pop.classList.remove("is-arriving"));

    if (!listening) {
      listening = true;
      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") Bridge.hidePanel();
      });
      globalThis.addEventListener("focus", () => {
        // The one signal the page gets that the shell has put it on screen. Paired with
        // `[shown]` in the shell's log, the two are click to painted.
        Measure.say("panel arrived");
        arriving?.();
      });
    }
    arriving();

    // Harness only: the panel's own buttons are otherwise the one thing a script cannot
    // reach, because an agent cannot click a menu bar and the panel is not the window the
    // shell evaluates against. Every button it draws exists at first draw, so there is
    // nothing to wait for, unlike the engine block in the window.
    if (info?.press && !pressed) {
      pressed = true;
      Bridge.log(`[harness] panel press ${JSON.stringify(info.press)}: ${pressOnce(String(info.press)) ? "pressed" : "no such button"}`);
    }
  },
};
