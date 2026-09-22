/* The menu bar panel, and the rule it exists to keep from being broken again.
 *
 * ## Why this file was written
 *
 * The panel's Ingest now and Review now printed "arrives with the engine wiring, in batch
 * 7" for three batches after batch 7 shipped. The wiring was real; it was placed on the
 * **window** (`ui/wiring.js`, called from `window.html`) and nothing called anything for
 * `index.html`, so the panel kept its placeholder.
 *
 * It survived because every check the batch had was a check of the window: the Rust tests
 * spawn the engine, the bridge test pins the command names, the harness can press a button
 * by its label but reads `PRUDENCE_PRESS` in `ui/window.js`, and the panel had no test at
 * all. A button that is there and does nothing passes all of that.
 *
 * So the last test here is the guard for the class, and it is deliberately not about
 * ingesting: **no surface may leave a button wired to nothing.** Every button the panel
 * draws is pressed against a fake shell and has to reach it.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { installDom } from "./dom.mjs";

installDom();

const here = dirname(fileURLToPath(import.meta.url));
const app = join(here, "..");

import * as Str from "../src/text/strings.js";
import { readPayload } from "../src/store/payload.js";
import { projects } from "../src/text/fmt.js";
const { page, PANEL_RUN } = /** @type {any} */ (await import("../src/ui/panel.js"));
const { forget } = /** @type {any} */ (await import("../src/store/readiness.js"));

for (const language of Str.LANGUAGES) {
  Str.load(
    language,
    JSON.parse(readFileSync(join(app, `src/text/strings.${language}.json`), "utf8"))
  );
}
Str.setLang("en");

const settled = () => new Promise(setImmediate);

const DATA = readPayload({
  status: { engine_version: "0.4.0", last_ingest_at: "2026-09-21T09:00:00Z" },
  usage: [],
  commits: [],
  sessions: [],
  outcomes: [],
  observations: [],
  reviews: [],
  projects: [],
});

/**
 * Draw the panel into a container that is really in the shim's body, so the status line
 * can be found by id the way the panel finds it.
 *
 * The body is emptied first: `document.getElementById` walks it, and two panels in it at
 * once would have the second one report into the first one's line.
 */
function draw() {
  PANEL_RUN.running = null;
  PANEL_RUN.at = null;
  // A readiness answer is remembered against the store it was taken for, and every test
  // here draws the same store; without this the second one reads the first one's answer.
  forget();
  return again();
}

/**
 * The same panel, drawn again into a body with nothing else in it, keeping whatever a run
 * has put in `PANEL_RUN`. That is what the store watcher does while an ingest is going.
 */
function again() {
  /** @type {any} */ (document).body.children = [];
  const container = document.createElement("div");
  /** @type {any} */ (document).body.appendChild(container);
  page.render(/** @type {any} */ (container), { data: DATA });
  return /** @type {any} */ (container);
}

function buttons(container) {
  return container.findAll("button");
}

function pressed(container, label) {
  const button = buttons(container).find((node) => node.textContent === label);
  assert.ok(button, `the panel has no button labelled ${label}`);
  button.fire("click");
  return button;
}

function note(container) {
  const line = container.findAll(".coverage-chip").find((node) => node.id === "pop-note");
  assert.ok(line, "the panel has no line to report into");
  return line;
}

/** The same place, when it is carrying a bar rather than a sentence. */
function bar(container) {
  const line = container.findAll(".pop-progress").find((node) => node.id === "pop-note");
  assert.ok(line, "the panel is not drawing a progress bar");
  return line;
}

/**
 * The shell, as this file's tests drive it: the events it would send and whether the page
 * stopped listening. Beside the recorder rather than on it, because the recorder is
 * compared with `deepEqual` and an array carrying properties is not the array it looks
 * like.
 */
const shell = { send: (/** @type {any} */ _progress) => {}, stopped: false };

/**
 * A shell that answers whatever the test says, and records what it was asked.
 *
 * `options.readiness` is what the engine says about writing a review, or nothing at all.
 */
function fakeShell(answer, options = {}) {
  const asked = [];
  shell.send = () => {};
  shell.stopped = false;
  PANEL_RUN.port = {
    run: (action) => {
      asked.push(action);
      return typeof answer === "function" ? answer(action) : Promise.resolve(answer ?? { action, ok: true });
    },
    onProgress: (handler) => {
      shell.send = handler;
      return Promise.resolve(() => {
        shell.stopped = true;
      });
    },
    readiness: () => Promise.resolve(options.readiness ?? null),
  };
  return asked;
}

/** One `engine-progress` payload, as the shell serialises it. */
function event(overrides = {}) {
  return {
    step: "archive",
    stepIndex: 2,
    steps: 11,
    current: 17,
    total: 494,
    unit: "files",
    label: "Archiving beatos",
    ...overrides,
  };
}

test("the panel draws its five buttons", () => {
  PANEL_RUN.port = null;
  PANEL_RUN.running = null;
  const container = draw();
  assert.deepEqual(
    buttons(container).map((node) => node.textContent),
    [
      Str.t("menu.openPrudence"),
      Str.t("menu.reviewNow"),
      Str.t("menu.ingestNow"),
      Str.t("menu.settings"),
      Str.t("menu.quit"),
    ]
  );
});

/* The defect this file exists for. The note is the exact sentence that was on screen. */
test("no button on the panel says which batch it arrives in", () => {
  PANEL_RUN.port = null;
  const container = draw();
  pressed(container, Str.t("menu.ingestNow"));
  assert.equal(
    container.textContent.includes("batch 7"),
    false,
    "the placeholder is still there"
  );
});

test("Ingest now runs an ingest, and Review now runs a review", async () => {
  const asked = fakeShell();
  const container = draw();
  pressed(container, Str.t("menu.ingestNow"));
  await settled();
  pressed(container, Str.t("menu.reviewNow"));
  await settled();
  assert.deepEqual(asked, ["ingest", "review"]);
});

/* --- what the panel is over, and how the mix is named ----------------------------------
 *
 * Every figure on the panel is the whole store, all projects, and nothing said so: a reader
 * with three repositories recorded had no way to know that from here.
 */

/** Today, as the engine writes a day, so a row lands inside the rolling seven days. */
function today() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(
    now.getDate()
  ).padStart(2, "0")}`;
}

function drawWith(payload) {
  PANEL_RUN.running = null;
  PANEL_RUN.at = null;
  forget();
  /** @type {any} */ (document).body.children = [];
  const container = document.createElement("div");
  /** @type {any} */ (document).body.appendChild(container);
  page.render(/** @type {any} */ (container), { data: readPayload(payload) });
  return /** @type {any} */ (container);
}

test("the head says what the panel is over", () => {
  PANEL_RUN.port = null;
  const container = drawWith({
    status: { engine_version: "0.4.0" },
    usage: [],
    commits: [],
    sessions: [],
    outcomes: [],
    observations: [],
    reviews: [],
    projects: [
      { key: "root:a", name: "a" },
      { key: "root:b", name: "b" },
      { key: "root:c", name: "c" },
    ],
  });
  const head = container.find(".pop-head");
  assert.ok(
    head.textContent.includes(projects(3)),
    `the head does not say what it is over: ${head.textContent}`
  );
});

/* The sentence names the purposes in order and the bar draws them, so a swatch legend
   naming the same three words was a third row for one fact in a 360 pt window. The colour
   goes on the name instead: identity, never judgement. */
test("the purposes are coloured in the sentence and named nowhere else", () => {
  PANEL_RUN.port = null;
  const container = drawWith({
    status: { engine_version: "0.4.0" },
    usage: {
      columns: ["day", "project", "repo_key", "purpose", "total_tokens", "active_minutes", "measured_sessions", "sessions"],
      rows: [
        [today(), "a", "root:a", "development", 900, 60, 1, 1],
        [today(), "a", "root:a", "research", 100, 10, 1, 1],
      ],
    },
    commits: [],
    sessions: [],
    outcomes: [],
    observations: [],
    reviews: [],
    projects: [{ key: "root:a", name: "a" }],
  });

  const named = container.findAll(".purpose-name");
  assert.deepEqual(
    named.map((node) => node.textContent),
    [Str.t("purpose.development"), Str.t("purpose.research")],
    "the purposes are not named in the sentence"
  );
  for (const node of named) {
    assert.match(node.style.color, /^var\(--p-[a-z]+\)$/, `no purpose colour on ${node.textContent}`);
  }
  assert.deepEqual(container.findAll(".legend"), [], "the swatch legend is still under the bar");
});

/* --- what a run says while it is going ------------------------------------------------
 *
 * The place the note occupies carries one of two things: a sentence, or the bar. What is
 * asserted is that the engine's own event is what the bar is drawn from, that the outcome
 * sentence replaces it when the run ends, and that a redraw part way through a run does
 * not blank it.
 */

test("a progress event replaces the line with the engine's own step and count", async () => {
  let finish;
  const asked = fakeShell(() => new Promise((resolve) => { finish = resolve; }));
  const container = draw();
  pressed(container, Str.t("menu.ingestNow"));
  await settled();

  // Before the first event: the sentence that says a run started, because the engine
  // reads its repositories before it can count anything.
  assert.equal(note(container).textContent, Str.t("menu.ingesting"));

  shell.send(event());
  const shown = bar(container);
  assert.ok(shown.textContent.includes(Str.t("engine.step.archive")), shown.textContent);
  assert.ok(
    shown.textContent.includes(
      Str.t("engine.progress.count", "17", "494", Str.t("engine.unit.files"))
    ),
    shown.textContent
  );
  assert.equal(shown.find(".progress-fill").style.width, `${(17 / 494) * 100}%`);

  finish({ action: "ingest", ok: true, sessions: 151 });
  await settled();
  // The engine's own outcome replaces the bar, and the listener is taken down with it.
  assert.ok(note(container).textContent.includes("151"), note(container).textContent);
  assert.equal(shell.stopped, true, "the panel went on listening after the run ended");
  assert.deepEqual(asked, ["ingest"]);
});

/* A redraw mid-run used to blank the line: an ingest announces itself to the store watcher
   several times while it works, every announcement redraws the panel, and the new tree had
   an empty note until the engine happened to count something else. On the `parse` step
   that is seconds of a surface saying nothing about a run it started. */
test("a redraw part way through a run keeps the bar on screen", async () => {
  fakeShell(() => new Promise(() => {}));
  const container = draw();
  pressed(container, Str.t("menu.ingestNow"));
  await settled();
  shell.send(event({ step: "parse", stepIndex: 3, current: 40, total: 151, unit: "sessions" }));

  // What the store watcher does: the same page, drawn again, with the run still going.
  const shown = bar(again());
  assert.ok(shown.textContent.includes(Str.t("engine.step.parse")), shown.textContent);
  assert.equal(shown.find(".progress-fill").style.width, `${(40 / 151) * 100}%`);

  // And before the first event, the sentence comes back rather than nothing at all.
  PANEL_RUN.at = null;
  assert.equal(note(again()).textContent, Str.t("menu.ingesting"));
  PANEL_RUN.running = null;
});

/* --- whether a review is ready ---------------------------------------------------------- */

/* --- the panel is its final height at first paint -------------------------------------
 *
 * The readiness answer comes from a subprocess and used to arrive into a row that was
 * `hidden` until it did. A popover is only as tall as its content and is anchored under the
 * status item when it is shown, so the window was re-measured and re-anchored under the
 * reader a second after it opened: 635 px at render, 677 px a second later, measured
 * against a copy of the founder's store on 2026-09-22.
 *
 * A node test has no layout, so what is asserted here is the property the equal height
 * rests on: **the answer changes no node**. The slot is in the tree from the first paint,
 * it is never hidden, and filling it adds nothing and removes nothing. The height itself is
 * checked in the app, where `[measure] panel refit` prints it.
 */
function nodeCount(container) {
  let count = 0;
  for (const _ of container.walk()) count += 1;
  return count;
}

test("the readiness answer arrives into a reserved row and changes no node", async () => {
  fakeShell(undefined, {
    readiness: { ready: false, newSessions: 2, requiredSessions: 5, maturedCommits: 0, requiredCommits: 1 },
  });
  const container = draw();

  const slot = container.findAll(".pop-reserve").find((node) => node.find(".coverage-chip")?.id === "pop-ready");
  assert.ok(slot, "the panel reserves no row for the readiness answer");
  const caption = slot.find(".coverage-chip");
  assert.equal(caption.hidden, false, "the readiness row is revealed rather than reserved");
  assert.equal(caption.textContent, "", "the row has an answer before the engine gave one");
  const before = nodeCount(container);

  await settled();
  assert.equal(caption.textContent, Str.t("review.readiness.needs", "2", "5", "0", "1"));
  assert.equal(
    nodeCount(container),
    before,
    "the readiness answer changed the panel's tree, so it changed its height"
  );
});

test("the panel says what the engine says about writing a review", async () => {
  fakeShell(undefined, {
    readiness: {
      ready: true,
      sentence: "A review is ready: 151 new sessions so far and 697 commits crossed their 7-day mark.",
    },
  });
  const container = draw();
  await settled();
  const caption = container.findAll(".coverage-chip").find((node) => node.id === "pop-ready");
  assert.ok(caption, "the panel has no readiness caption");
  assert.equal(caption.hidden, false, "the caption stayed hidden with an answer in hand");
  assert.ok(caption.textContent.includes("151 new sessions"), caption.textContent);
});

test("a review that is not ready says what is still needed, in the reader's language", async () => {
  fakeShell(undefined, {
    readiness: {
      ready: false,
      newSessions: 2,
      requiredSessions: 5,
      maturedCommits: 0,
      requiredCommits: 1,
    },
  });
  const container = draw();
  await settled();
  const caption = container.findAll(".coverage-chip").find((node) => node.id === "pop-ready");
  assert.equal(caption.textContent, Str.t("review.readiness.needs", "2", "5", "0", "1"));
});

/* An engine that does not carry readiness says nothing at all. "Not ready" would be this
   app inventing a verdict out of an answer it was never given. The row is reserved either
   way, and an empty one draws nothing: `.coverage-chip:empty` in `app.css`. */
test("no answer is no line rather than a guess", async () => {
  fakeShell(undefined, { readiness: null });
  const container = draw();
  await settled();
  const caption = container.findAll(".coverage-chip").find((node) => node.id === "pop-ready");
  assert.equal(caption.textContent, "", "a verdict was drawn with nothing behind it");
});

/* In flight: one line, and the two buttons dead. */
test("a run in flight says so and refuses a second press", async () => {
  let finish;
  const asked = fakeShell(() => new Promise((resolve) => { finish = resolve; }));
  const container = draw();
  pressed(container, Str.t("menu.ingestNow"));

  assert.equal(note(container).hidden, false, "nothing on screen says a run is going");
  assert.equal(note(container).textContent, Str.t("menu.ingesting"));
  const ingest = buttons(container).find((n) => n.textContent === Str.t("menu.ingestNow"));
  const review = buttons(container).find((n) => n.textContent === Str.t("menu.reviewNow"));
  assert.equal(ingest.disabled, true, "Ingest now is still pressable during a run");
  assert.equal(review.disabled, true, "Review now is still pressable during a run");

  finish({ action: "ingest", ok: true, sessions: 150 });
  await settled();
  assert.deepEqual(asked, ["ingest"], "the run was started once");
  assert.equal(ingest.disabled, false, "the buttons never came back");
});

test("the engine's own outcome is what the panel prints afterwards", async () => {
  const cases = [
    [{ action: "ingest", ok: true, sessions: 150 }, "ingest", "150 sessions"],
    [{ action: "ingest", ok: true }, "ingest", Str.t("menu.ingestFinished")],
    [{ action: "review", ok: true, reviewId: 7 }, "review", Str.t("menu.reviewWrittenId", "7")],
    [{ action: "review", ok: true }, "review", Str.t("menu.reviewWritten")],
    [
      { action: "review", notReady: true, reason: "not ready: 2 new sessions so far (needs 5)." },
      "review",
      "not ready: 2 new sessions so far (needs 5).",
    ],
    [{ action: "ingest", errorKind: "failed", error: "no repository is enabled" }, "ingest", Str.t("engine.failed.title")],
    [{ action: "ingest", errorKind: "busy" }, "ingest", Str.t("engine.busy")],
  ];
  for (const [answer, action, wanted] of cases) {
    fakeShell(answer);
    const container = draw();
    pressed(container, action === "ingest" ? Str.t("menu.ingestNow") : Str.t("menu.reviewNow"));
    await settled();
    assert.ok(
      note(container).textContent.includes(wanted),
      `${JSON.stringify(answer)} printed ${JSON.stringify(note(container).textContent)}`
    );
  }
});

test("a shell that never answers still leaves the buttons alive", async () => {
  fakeShell(() => Promise.reject(new Error("the shell went away")));
  const container = draw();
  pressed(container, Str.t("menu.ingestNow"));
  await settled();
  assert.ok(note(container).textContent.includes("the shell went away"));
  const ingest = buttons(container).find((n) => n.textContent === Str.t("menu.ingestNow"));
  assert.equal(ingest.disabled, false, "a failed run left the buttons dead for ever");
});

test("the panel draws in Chinese with no English left on it", () => {
  Str.setLang("zh-Hans");
  try {
    PANEL_RUN.port = null;
    const container = draw();
    const text = container.textContent;
    for (const key of ["menu.openPrudence", "menu.ingestNow", "menu.quit", "menu.today"]) {
      assert.equal(text.includes(Str.tIn("en", key)), false, `the English of ${key} is still there`);
      assert.ok(text.includes(Str.tIn("zh-Hans", key)), `${key} is not in Chinese`);
    }
  } finally {
    Str.setLang("en");
  }
});

/* --- the guard for the class ----------------------------------------------------------
 *
 * Not "the panel ingests". **No surface may leave a button wired to nothing.** Every
 * button the panel draws is pressed and has to reach something: the shell, the window, or
 * the runner. A label with nothing behind it is what shipped, and this is what would have
 * caught it.
 */
test("every button the panel draws reaches something", async () => {
  const reached = [];
  const asked = fakeShell((action) => {
    reached.push(`run:${action}`);
    return Promise.resolve({ action, ok: true });
  });
  const container = draw();

  // Open, Settings and Quit go straight to the shell rather than through the port. A
  // module's exported bindings are read-only, so the fake goes where every one of those
  // calls ends up: `__TAURI__`, which `bridge.js` reads afresh on each call.
  /** @type {any} */ (globalThis).__TAURI__ = {
    core: {
      invoke: (name) => {
        reached.push(`invoke:${name}`);
        return Promise.resolve();
      },
    },
  };
  try {
    for (const button of buttons(container)) {
      const before = reached.length;
      button.fire("click");
      await settled();
      assert.ok(
        reached.length > before,
        `the button labelled ${JSON.stringify(button.textContent)} reached nothing`
      );
    }
  } finally {
    delete (/** @type {any} */ (globalThis).__TAURI__);
  }
  assert.deepEqual(asked, ["review", "ingest"], "the two engine actions did not run");
});
