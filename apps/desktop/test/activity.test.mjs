/* The toolbar's two actions, the sidebar's status row, and the report a run leaves.
 *
 * What these guard: that both places follow the **shell's** answer about what is running,
 * whoever started the run, rather than the promise of a button this page pressed; that a
 * run's outcome is said once, for a moment, to a window that saw the run end, and never to
 * one opened afterwards; that each place keeps one declared size in every state; and that
 * the report still says, in the engine's own words, the two things a line cannot carry.
 *
 * The shell is a fake port and the DOM is the shim in `dom.mjs`. The shell's own half of
 * the answer (who holds the lock, when a run starts and ends) is `src-tauri/src/activity.rs`
 * and its tests.
 *
 *     pnpm test
 */

import { test, afterEach } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { installDom } from "./dom.mjs";

installDom();

const here = dirname(fileURLToPath(import.meta.url));
const app = join(here, "..");

const Str = await import("../src/text/strings.js");
const Fmt = await import("../src/text/fmt.js");
const {
  ACTIVITY,
  OUTCOME_SHOWN,
  failureSentence,
  follow,
  phase,
  runActions,
  runNow,
  runReport,
  statusRow,
  take,
  progressed,
} = /** @type {any} */ (await import("../src/ui/activity.js"));

for (const language of Str.LANGUAGES) {
  Str.load(
    language,
    JSON.parse(readFileSync(join(app, `src/text/strings.${language}.json`), "utf8"))
  );
}
Str.setLang("en");

const settled = () => new Promise(setImmediate);

const IDLE = { running: null, outside: false, progress: null, outcome: null };

afterEach(() => {
  if (ACTIVITY.lapse) clearTimeout(ACTIVITY.lapse);
  ACTIVITY.lapse = null;
  ACTIVITY.now = { ...IDLE };
  ACTIVITY.sayUntil = 0;
  ACTIVITY.port = null;
  ACTIVITY.mounts.clear();
});

/**
 * A shell that answers whatever the test says and records what it was asked. The two
 * listeners are handed back, so a test sends the events the shell would send.
 */
function fakePort(answers = {}) {
  const asked = { runs: [], activity: null, progress: null };
  ACTIVITY.port = {
    read: () => Promise.resolve(answers.now ?? IDLE),
    onActivity: (handler) => {
      asked.activity = handler;
      return Promise.resolve(() => {});
    },
    onProgress: (handler) => {
      asked.progress = handler;
      return Promise.resolve(() => {});
    },
    run: (action, force) => {
      asked.runs.push({ action, force });
      const answer = answers.run;
      return typeof answer === "function"
        ? answer(action, force)
        : Promise.resolve(answer ?? { action, ok: true });
    },
  };
  return asked;
}

const ARCHIVING = {
  step: "archive",
  stepIndex: 2,
  steps: 11,
  current: 17,
  total: 494,
  unit: "files",
  label: "Archiving beatos",
};

/** What a place holds right now, by kind. */
function holds(node) {
  return node.children.map((child) => child.className.split(/\s+/)[0] || child.localName);
}

/* --- the three states ------------------------------------------------------------------ */

test("a place is running while the shell says so, whatever the outcome before it was", () => {
  assert.equal(phase({ ...IDLE, running: "ingest" }, 0, 0), "running");
  assert.equal(phase({ ...IDLE, running: "ingest", outcome: { ok: true } }, 10, 0), "running");
  assert.equal(phase({ ...IDLE, outcome: { ok: true } }, 10, 5), "outcome");
  assert.equal(phase({ ...IDLE, outcome: { ok: true } }, 10, 10), "idle");
  assert.equal(phase(IDLE, 10, 5), "idle");
});

/* An outcome is news only to a window that saw the run end. The same answer read by a
   window opened a minute later carries the same outcome and must not say it again. */
test("a run's end starts the moment its outcome is said, and a late window says nothing", () => {
  take({ ...IDLE, outcome: { action: "ingest", ok: true } }, 1000);
  assert.equal(ACTIVITY.sayUntil, 0, "a window opened after the run said its outcome");

  take({ ...IDLE, running: "ingest" }, 2000);
  take({ ...IDLE, outcome: { action: "ingest", ok: true } }, 3000);
  assert.equal(ACTIVITY.sayUntil, 3000 + OUTCOME_SHOWN);
  assert.equal(phase(ACTIVITY.now, ACTIVITY.sayUntil, 3000 + OUTCOME_SHOWN - 1), "outcome");
  assert.equal(phase(ACTIVITY.now, ACTIVITY.sayUntil, 3000 + OUTCOME_SHOWN), "idle");
});

/* A progress line belongs to the run in hand; one arriving before the page has heard of
   any run is dropped rather than inventing one. */
test("a progress line is kept for the run in hand and dropped with none", () => {
  progressed(ARCHIVING);
  assert.equal(ACTIVITY.now.progress, null);
  take({ ...IDLE, running: "ingest" });
  progressed(ARCHIVING);
  assert.deepEqual(ACTIVITY.now.progress, ARCHIVING);
});

/* --- the toolbar ------------------------------------------------------------------------- */

test("idle, the toolbar offers the panel's two actions, the primary last", async () => {
  const asked = fakePort();
  const actions = runActions();
  const buttons = actions.findAll("button");
  assert.deepEqual(
    buttons.map((node) => [node.textContent, node.className]),
    [
      [Str.t("menu.reviewNow"), "btn"],
      [Str.t("menu.ingestNow"), "btn primary"],
    ]
  );
  buttons[1].fire("click");
  buttons[0].fire("click");
  await settled();
  assert.deepEqual(asked.runs, [
    { action: "ingest", force: false },
    { action: "review", force: false },
  ]);
});

/* The case the whole shell half exists for: a run nobody pressed in this window. The
   toolbar follows the shell's events, not a promise of its own. */
test("a run started anywhere takes the buttons' place, and its lines move the bar", () => {
  const asked = fakePort();
  follow();
  const actions = runActions();

  asked.activity({ ...IDLE, running: "ingest" });
  assert.equal(actions.findAll("button").length, 0, "a button is offered during a run");
  assert.equal(
    actions.find(".progress-label").textContent,
    Str.t("menu.ingesting"),
    "before its first line an ingest says what it is"
  );

  asked.progress(ARCHIVING);
  const bar = actions.find(".progress");
  assert.ok(bar.className.split(/\s+/).includes("is-compact"), "the toolbar's bar is not compact");
  assert.equal(bar.find(".progress-label").textContent, Str.t("engine.step.archive"));
  assert.equal(
    bar.find(".progress-count").textContent,
    Str.t("engine.progress.count", "17", "494", Str.t("engine.unit.files"))
  );
  assert.equal(bar.find(".progress-fill").style.width, `${(17 / 494) * 100}%`);
});

test("then how it ended, with the engine's own figure under the pointer, then the buttons", () => {
  const asked = fakePort();
  follow();
  const actions = runActions();
  asked.activity({ ...IDLE, running: "ingest" });
  asked.activity({ ...IDLE, outcome: { action: "ingest", ok: true, sessions: 151 } });

  const line = actions.find(".run-outcome");
  assert.ok(line, "the outcome was not said");
  assert.equal(line.textContent, Str.t("menu.ingestFinished"));
  assert.equal(line.title, Str.t("engine.ingestFinished.sessions", Fmt.sessions(151)));

  // The moment lapses: what the timer does, without waiting for it.
  ACTIVITY.sayUntil = 0;
  ACTIVITY.mounts.get("toolbar")();
  assert.equal(actions.findAll("button").length, 2, "the buttons never came back");
});

test("a run from outside the app and a review each say what they are", () => {
  const asked = fakePort();
  follow();
  const actions = runActions();

  asked.activity({ ...IDLE, running: "ingest", outside: true });
  assert.equal(actions.textContent, Str.t("activity.outside"));
  assert.equal(actions.find(".progress-track"), null, "a run that counts nothing drew a track");

  asked.activity({ ...IDLE, running: "review" });
  assert.equal(actions.textContent, Str.t("menu.writingReview"));
});

/* One declared box, every state. A DOM test cannot measure a pixel, so what it guards is
   that each state is one thing in the same node, and that the stylesheet gives the node
   its size rather than its content. */
test("the toolbar and the status row hold one thing at a time, in a box of their own size", () => {
  const asked = fakePort();
  follow();
  const actions = runActions();
  const status = statusRow({ status: { last_ingest_at: null } });

  const states = [];
  const look = () => states.push([holds(actions), holds(status)]);
  look();
  asked.activity({ ...IDLE, running: "ingest" });
  look();
  asked.progress(ARCHIVING);
  look();
  asked.activity({ ...IDLE, outcome: { action: "ingest", ok: true } });
  look();
  assert.deepEqual(states, [
    [["btn", "btn"], ["run-outcome"]],
    [["progress"], ["progress"]],
    [["progress"], ["progress"]],
    [["run-outcome"], ["run-outcome"]],
  ]);

  const css = readFileSync(join(app, "src/ui/activity.css"), "utf8");
  for (const selector of [".run-actions {", ".status-row {"]) {
    const at = css.indexOf(selector);
    assert.notEqual(at, -1, `no rule for ${selector}`);
    const body = css.slice(at, css.indexOf("}", at));
    assert.match(body, /\bheight:\s*\d+px/, `${selector} takes its height from its content`);
    assert.match(body, /\bflex:\s*none/, `${selector} may be squeezed by its neighbours`);
  }
  const toolbar = css.slice(css.indexOf(".run-actions {"));
  assert.match(toolbar.slice(0, toolbar.indexOf("}")), /\bwidth:\s*\d+px/, "the toolbar's width follows its state");
});

/* --- the status row ---------------------------------------------------------------------- */

test("idle, the status row says when the store was last ingested, in the reader's words", () => {
  const stamp = new Date(Date.now() - 13 * 3600 * 1000).toISOString();
  for (const language of Str.LANGUAGES) {
    Str.setLang(language);
    try {
      const row = statusRow({ status: { last_ingest_at: stamp } });
      // The narrow form, because the line has a sidebar's width; the long one on the pointer.
      assert.equal(
        row.textContent,
        Str.t("activity.lastIngest", Fmt.relative(stamp, undefined, undefined, "narrow"))
      );
      assert.match(row.textContent, /13/);
      assert.ok(row.children[0].title.includes(Fmt.relative(stamp)), row.children[0].title);
      const never = statusRow({ status: { last_ingest_at: null } });
      assert.equal(never.textContent, Str.t("activity.neverIngested"));
    } finally {
      Str.setLang("en");
    }
  }
});

test("a window drawn in the middle of a run asks once and shows the step it is on", async () => {
  fakePort({ now: { ...IDLE, running: "ingest", progress: ARCHIVING } });
  const status = statusRow({ status: { last_ingest_at: null } });
  follow();
  await settled();
  assert.equal(status.find(".progress-label").textContent, Str.t("engine.step.archive"));
});

/* --- the report ------------------------------------------------------------------------ */

test("a success is said in the toolbar and leaves no report behind", async () => {
  const card = runReport();
  fakePort({ run: { action: "review", ok: true, reviewId: 2 } });
  await runNow("review");
  assert.equal(card.hidden, true);
});

/* The readiness rule belongs to the engine. The app shows its sentence and offers the one
   way past it, which is the reader's decision and not the app's. */
test("a review the engine declines shows its reason and offers to write anyway", async () => {
  const card = runReport();
  const reason = "not ready: 2 new sessions since 2026-09-14 (needs 5).";
  const asked = fakePort({
    run: (action, force) =>
      Promise.resolve(
        force
          ? { action: "review", ok: true, reviewId: 3 }
          : { action: "review", ok: false, notReady: true, reason }
      ),
  });

  await runNow("review");
  const said = card.findAll(".run-said").map((node) => node.textContent);
  assert.deepEqual(said, [Str.t("review.notReady.title"), reason]);
  assert.deepEqual(
    card.findAll("button").map((node) => node.textContent),
    [Str.t("review.writeAnyway"), Str.t("common.cancel")]
  );

  card.findAll("button")[0].fire("click");
  await settled();
  assert.deepEqual(asked.runs, [
    { action: "review", force: false },
    { action: "review", force: true },
  ]);
  assert.equal(card.hidden, true, "the report stayed after the review was written");
});

test("a review with no reason still says the engine declined", async () => {
  const card = runReport();
  fakePort({ run: { action: "review", notReady: true, reason: null } });
  await runNow("review");
  assert.deepEqual(
    card.findAll(".run-said").map((node) => node.textContent),
    [Str.t("review.notReady.title"), Str.t("menu.reviewNotReady")]
  );
});

test("a run that fails says so in the engine's own words, and never silently does nothing", async () => {
  const card = runReport();
  fakePort({
    run: {
      action: "ingest",
      ok: false,
      errorKind: "failed",
      error: "No repository is enabled. Run `prudence init`.",
    },
  });
  await runNow("ingest");
  assert.deepEqual(card.findAll(".run-said").map((node) => node.textContent), [
    Str.t("engine.failed.title"),
    Str.t("engine.error.failed"),
    "No repository is enabled. Run `prudence init`.",
  ]);
  assert.equal(card.hidden, false);
});

test("a shell that does not answer at all is reported too", async () => {
  const card = runReport();
  fakePort({ run: () => Promise.reject(new Error("the shell went away")) });
  await runNow("ingest");
  assert.deepEqual(card.findAll(".run-said").map((node) => node.textContent).slice(0, 2), [
    Str.t("engine.failed.title"),
    "the shell went away",
  ]);
});

test("with no shell at all the report says the engine is not there", async () => {
  const card = runReport();
  await runNow("review");
  assert.equal(card.find(".run-said").textContent, Str.t("menu.engineMissing"));
});

/* Every failure kind the shell can send reaches a sentence, not an identifier, in the
   report and in the toolbar's line. Read out of the Rust rather than listed here: a new
   kind in `EngineError::kind()` with no sentence fails this. */
test("every failure the shell can send is a sentence on screen, never a key", async () => {
  const source = readFileSync(join(app, "src-tauri/src/engine.rs"), "utf8");
  const kinds = [...source.matchAll(/Self::\w+(?:\([^)]*\)|\s*\{[^}]*\})?\s*=>\s*"(\w+)"/g)].map(
    (m) => m[1]
  );
  assert.ok(kinds.length >= 5, `only found ${kinds.length} failure kinds in engine.rs`);
  kinds.push("notExecutable");
  for (const language of Str.LANGUAGES) {
    Str.setLang(language);
    try {
      for (const kind of [...kinds, "somethingFromAFutureBuild"]) {
        const card = runReport();
        fakePort({ run: { action: "ingest", errorKind: kind } });
        await runNow("ingest");
        const said = card.findAll(".run-said").map((node) => node.textContent);
        assert.ok(said.length > 0, `${language} ${kind}: the report said nothing`);
        for (const text of [...said, failureSentence(kind)]) {
          assert.doesNotMatch(
            text,
            /^[a-z]+(\.[a-zA-Z]+)+$/,
            `${language} ${kind}: an unresolved key reached the screen: ${text}`
          );
        }
      }
    } finally {
      Str.setLang("en");
    }
  }
});

/* --- both languages -------------------------------------------------------------------- */

test("every key these places ask for is in both tables, and they draw in Chinese", () => {
  const source = readFileSync(join(app, "src/ui/activity.js"), "utf8");
  const keys = [...source.matchAll(/\bt\(\s*"([^"]+)"/g)].map((match) => match[1]);
  assert.ok(keys.length > 15, `only found ${keys.length} keys`);
  for (const language of Str.LANGUAGES) {
    for (const key of keys) {
      assert.notEqual(Str.tIn(language, key), key, `${language} has no ${key}`);
    }
  }

  Str.setLang("zh-Hans");
  try {
    fakePort();
    const actions = runActions();
    assert.deepEqual(
      actions.findAll("button").map((node) => node.textContent),
      ["立即回顾", "立即采集"]
    );
    take({ ...IDLE, running: "ingest", outside: true });
    assert.equal(actions.textContent, "正在采集（在应用外启动）");
  } finally {
    Str.setLang("en");
  }
});
