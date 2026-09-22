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
const { page, PANEL_RUN } = /** @type {any} */ (await import("../src/ui/panel.js"));

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

/** A shell that answers whatever the test says, and records what it was asked. */
function fakeShell(answer) {
  const asked = [];
  PANEL_RUN.port = {
    run: (action) => {
      asked.push(action);
      return typeof answer === "function" ? answer(action) : Promise.resolve(answer ?? { action, ok: true });
    },
  };
  return asked;
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

/* In flight: one line, and the two buttons dead. The next sheet replaces the line with a
   progress bar, so what is asserted is the state and not the wording of the bar. */
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
