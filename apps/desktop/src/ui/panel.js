/* The menu bar panel: one column, a caption above every block, the actions at the foot.
 *
 * The variant the founder settled on (M4 plan, "Variant choices", and their clarification
 * the next day: content in the centre, not titles left and values right).
 *
 * Nothing in this file knows it is inside a Tauri window.
 */

import * as Bridge from "../bridge.js";
import { miniStack } from "../design/charts.js";
import { el } from "../design/dom.js";
import { mark } from "../design/brand.js";
import { hourPhrase, list, percent, purpose, sessions, commits, tokenPhrase, day } from "../text/fmt.js";
import { observationCaveat, observationSentence, reviewLine, stampedAgo } from "../text/sentences.js";
import { PRODUCT_NAME, t } from "../text/strings.js";
import { lastSevenDays, purposeShares, today } from "../store/payload.js";

/** Set by `render`, so the size report can run again when the content changes. */
let refit = () => {};

function text(content, className) {
  return el("span", { class: className ?? "", text: content });
}

/** A caption on its own line and the content full width under it. */
function block(caption, node) {
  return el("div", { class: "pop-block" }, [el("span", { class: "k", text: caption }), node]);
}

function head(data) {
  const bar = el("div", { class: "pop-head" });
  const brand = mark(18);
  brand.classList.add("brand-mark");
  bar.appendChild(brand);
  bar.appendChild(el("span", { class: "name", text: PRODUCT_NAME }));
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

function weekBlock(data) {
  const week = lastSevenDays(data);
  const shares = purposeShares(week);
  const summary = shares.length
    ? list(shares.map((part) => `${purpose(part.purpose)} ${percent(part.share)}`))
    : t("menu.noTokensThisWeek");

  const wrap = el("div", { class: "week-row" });
  wrap.appendChild(text(summary, "obs-line"));
  wrap.appendChild(
    miniStack({
      byPurpose: week.byPurpose,
      height: 8,
      caption: `${t("menu.thisWeek")}: ${summary} (${tokenPhrase(week.total)}, ${sessions(week.sessions)})`,
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

  const legend = el("div", { class: "legend" });
  for (const part of shares) {
    const key = el("span", { class: "key" });
    const swatch = document.createElement("i");
    swatch.style.background = `var(--p-${part.purpose})`;
    key.appendChild(swatch);
    key.appendChild(document.createTextNode(purpose(part.purpose)));
    legend.appendChild(key);
  }
  wrap.appendChild(legend);
  return wrap;
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
 * **window**: `ui/engine-section.js` owns the run and the report, and `window.html` calls
 * the wiring. Nothing calls it for `index.html`, so the panel kept the note.
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
 * One line, in the place the note already occupied, and the buttons disabled. The next
 * sheet replaces that line with a real progress bar: `progress()` is the only thing that
 * writes it and `PANEL_RUN.progress` is the only number it reads, so the swap is that
 * function and nothing else.
 */

/**
 * What the panel asks the shell, and whether a run is going.
 *
 * `port` is null in the app and is the bridge by default; a test sets it to a fake shell,
 * which is the only way to press these two buttons under `node --test`. The panel does
 * **not** use the engine block's runner: that one reports on a strip appended to the
 * document body, and the panel measures its own content to size its window, so a strip in
 * it would be measured into its height.
 *
 * @typedef {{ run: (action: "ingest"|"review") => Promise<any> }} PanelPort
 * @type {{ port: PanelPort | null, running: string | null }}
 */
export const PANEL_RUN = { port: null, running: null };

/** The fake shell a test injected, the real one, or nothing at all. */
function runner() {
  if (PANEL_RUN.port) return PANEL_RUN.port;
  if (!Bridge.attached()) return null;
  return { run: (action) => Bridge.runEngine(action, false) };
}

/** Every button a run disables, in the tree currently on screen. */
const actionButtons = new Set();

/**
 * The one line under the buttons: what a run is doing, or how it ended.
 *
 * It re-measures, because the line is content and the window is only as tall as its
 * content. The next sheet's progress bar replaces the body of this function.
 */
function progress(text) {
  const line = document.getElementById("pop-note");
  if (!line) return;
  if (!text) {
    line.hidden = true;
    line.textContent = "";
  } else {
    line.textContent = text;
    line.hidden = false;
    // On the shell's standard error as well, for the same reason `page_log` exists at
    // all: a menu bar app has no console anybody is watching, and this line is the only
    // report a run started from the panel makes. Only where there is a shell to say it
    // to: the page is opened in a browser while layout is worked on, and under a test.
    if (Bridge.attached()) Bridge.log(`panel: ${text}`);
  }
  refit();
}

function setRunning(action) {
  PANEL_RUN.running = action;
  for (const button of actionButtons) /** @type {any} */ (button).disabled = Boolean(action);
}

/**
 * Start a run from the panel, and report it in the panel.
 *
 * The same two engine actions the window's Engine tab runs, through the same shell
 * command. The outcome sentence is the engine's own answer, said in the reader's
 * language, which is the same set of sentences `engine-section.js` prints.
 *
 * @param {"ingest"|"review"} action
 */
function run(action) {
  const port = runner();
  if (!port) {
    progress(t("engine.noShell.detail"));
    return;
  }
  if (PANEL_RUN.running) {
    progress(t("engine.busy"));
    return;
  }
  setRunning(action);
  progress(action === "ingest" ? t("menu.ingesting") : t("menu.writingReview"));
  port
    .run(action)
    .then((outcome) => {
      setRunning(null);
      progress(outcomeLine(action, outcome));
    })
    .catch((error) => {
      setRunning(null);
      progress(error instanceof Error ? error.message : String(error));
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
function footer() {
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

  const note = el("div", { class: "coverage-chip", text: "" });
  note.id = "pop-note";
  note.hidden = true;

  return el("div", { class: "pop-foot" }, [
    note,
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
    const pop = el("div", { class: "popover" }, [head(data)]);

    const body = el("div", { class: "pop-body" }, [
      block(t("menu.today"), todayBlock(data)),
      block(t("menu.thisWeek"), weekBlock(data)),
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
    pop.appendChild(footer());

    container.innerHTML = "";
    container.appendChild(pop);

    /* A popover is as tall as what is in it. The stretch that pins the footer to the
       bottom is lifted for one measurement, or the window's own height is what gets
       measured and the panel can only ever grow. */
    refit = () => {
      if (!Bridge.attached()) return;
      const stretch = pop.style.minHeight;
      pop.style.minHeight = "0";
      const height = Math.ceil(pop.getBoundingClientRect().height);
      pop.style.minHeight = stretch;
      if (height > 0) Bridge.fitPanel(360, height);
      return height;
    };
    refit();

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
      globalThis.addEventListener("focus", () => arriving?.());
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
