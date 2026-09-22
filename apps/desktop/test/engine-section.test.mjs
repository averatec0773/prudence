/* The engine block, the activity strip, and the runner between them.
 *
 * Everything here is driven through a fake port, which is the only way to exercise the
 * states that matter: nothing found, a file found and refused, a review the engine
 * declines, and a run that fails. A machine in each of those states is not something a
 * test can arrange, and a test that only ever sees the happy one would pass on a build
 * where every failure draws a blank area.
 *
 * The last test parses `src-tauri/src/engine.rs` for the words the shell can send as a
 * failure and insists each of them has a sentence. A new failure kind in Rust with no
 * string in the catalogue would otherwise reach the reader as `engine.error.somethingNew`.
 *
 *     pnpm test
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

const Str = await import("../src/text/strings.js");
const Fmt = await import("../src/text/fmt.js");
// `any`, deliberately: the tree the block returns is the shim's, and asking it for
// `find` is the whole point of the shim.
const { ENGINE, engineSection, engineActivity, run, wireEngine } = /** @type {any} */ (
  await import("../src/ui/engine-section.js")
);
const { REVIEW_NOW } = /** @type {any} */ (await import("../src/ui/review.js"));

for (const language of Str.LANGUAGES) {
  Str.load(
    language,
    JSON.parse(readFileSync(join(app, `src/text/strings.${language}.json`), "utf8"))
  );
}
Str.setLang("en");

/** Let every queued promise callback run. The block draws first and fills when the shell
 *  answers, so there is always one turn between the two. */
const settled = () => new Promise(setImmediate);

/**
 * A shell that answers whatever the test says, and records what it was asked.
 *
 * @param {{ status?: any, run?: any, choose?: any }} answers
 */
function fakePort(answers = {}) {
  const asked = { status: 0, runs: [], choose: 0, forget: 0 };
  ENGINE.port = {
    status: () => {
      asked.status += 1;
      const answer = answers.status;
      return Promise.resolve(typeof answer === "function" ? answer(asked.status) : answer);
    },
    run: (action, force) => {
      asked.runs.push({ action, force });
      const answer = answers.run;
      return typeof answer === "function"
        ? answer(action, force)
        : Promise.resolve(answer ?? { action, ok: true });
    },
    choose: () => {
      asked.choose += 1;
      return Promise.resolve(answers.choose ?? { cancelled: true });
    },
    forget: () => {
      asked.forget += 1;
      return Promise.resolve();
    },
  };
  return asked;
}

const FOUND = {
  found: true,
  path: "/Users/someone/.local/bin/prudence",
  source: { kind: "directory", directory: "/Users/someone/.local/bin" },
  version: "0.4.0",
  remembered: false,
};

/** A page state as `screens.js` describes it, carrying only what this block reads. */
function state(engineVersion) {
  return { data: { status: engineVersion ? { engine_version: engineVersion } : null } };
}

/* --- the block ----------------------------------------------------------------------- */

test("the block says it is looking before the shell has answered", async () => {
  fakePort({ status: FOUND });
  const block = engineSection(state("0.4.0"));
  assert.equal(block.find(".engine-line").textContent, Str.t("menu.engineChecking"));
  await settled();
  assert.equal(block.find(".engine-path").textContent, FOUND.path);
});

test("a found engine shows its path, its version and where it came from", async () => {
  fakePort({ status: FOUND });
  const block = engineSection(state("0.4.0"));
  await settled();
  assert.equal(block.find(".engine-path").textContent, FOUND.path);
  assert.equal(
    block.find(".engine-line").textContent,
    Str.t("engine.versionAndSource", "0.4.0", Str.t("settings.foundAutomatically"))
  );
  // The note that says where the search looked is always there: it is what makes the
  // answer checkable.
  const notes = block.findAll(".engine-note").map((node) => node.textContent);
  assert.ok(notes.includes(Str.t("settings.enginePath.note")));
});

test("each of the three ways of finding it says which one it was", async () => {
  for (const { source, key } of [
    { source: { kind: "settings" }, key: "settings.source.settings" },
    {
      source: { kind: "directory", directory: "/opt/homebrew/bin" },
      key: "settings.foundAutomatically",
    },
    { source: { kind: "loginShell" }, key: "engine.source.loginShell" },
  ]) {
    fakePort({ status: { ...FOUND, source } });
    const block = engineSection(state("0.4.0"));
    await settled();
    assert.match(block.find(".engine-line").textContent, new RegExp(Str.t(key)));
  }
});

test("nothing found says engine not found, and offers a way to fix it", async () => {
  fakePort({ status: { found: false, errorKind: "notFound", remembered: false } });
  const block = engineSection(state("0.4.0"));
  await settled();
  assert.equal(block.find(".empty-title").textContent, Str.t("menu.engineMissing"));
  assert.equal(block.find(".empty-detail").textContent, Str.t("engine.notFound.detail"));

  const labels = block.findAll("button").map((node) => node.textContent);
  assert.deepEqual(labels, [Str.t("common.tryAgain"), Str.t("common.choose")]);
  // No action is offered for an engine that is not there: a button that cannot work is
  // worse than no button.
  assert.ok(!labels.includes(Str.t("menu.ingestNow")));
});

/* Found means verified. A file that is there and cannot say what it is has to be named,
   or the reader is told "not found" about a file they can see on their own disk. */
test("a file that was found and refused is named, with the engine's own words", async () => {
  fakePort({
    status: {
      found: false,
      path: "/Users/someone/bin/prudence",
      errorKind: "noVersion",
      error: "Python 3.12.1",
      remembered: true,
    },
  });
  const block = engineSection(state("0.4.0"));
  await settled();
  assert.equal(block.find(".engine-path").textContent, "/Users/someone/bin/prudence");
  const said = block.find(".engine-line").textContent;
  assert.match(said, new RegExp(Str.t("engine.error.noVersion").replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  assert.match(said, /Python 3\.12\.1/);
  // And a remembered path can be forgotten, which is the way out of a bad choice.
  assert.ok(block.findAll("button").some((node) => node.textContent === Str.t("common.clear")));
});

test("the chosen path can be cleared only when there is one", async () => {
  fakePort({ status: { ...FOUND, remembered: false } });
  let block = engineSection(state("0.4.0"));
  await settled();
  assert.ok(!block.findAll("button").some((n) => n.textContent === Str.t("common.clear")));

  fakePort({ status: { ...FOUND, remembered: true, source: { kind: "settings" } } });
  block = engineSection(state("0.4.0"));
  await settled();
  assert.ok(block.findAll("button").some((n) => n.textContent === Str.t("common.clear")));
});

/* --- the two versions ---------------------------------------------------------------- */

test("the CLI and the store disagreeing is said, calmly, and only when they do", async () => {
  fakePort({ status: FOUND });
  let block = engineSection(state("0.3.1"));
  await settled();
  const notes = block.findAll(".engine-note").map((node) => node.textContent);
  assert.ok(notes.includes(Str.t("engine.versionMismatch", "0.4.0", "0.3.1")));

  // The same version, and there is nothing to say.
  fakePort({ status: FOUND });
  block = engineSection(state("0.4.0"));
  await settled();
  assert.ok(
    !block
      .findAll(".engine-note")
      .some((node) => node.textContent.includes(Str.t("engine.versionMismatch", "0.4.0", "0.4.0")))
  );

  // And a store that has not been read yet is not a disagreement.
  fakePort({ status: FOUND });
  block = engineSection(state(null));
  await settled();
  assert.equal(block.findAll(".engine-note").length, 1);
});

/* --- the picker ---------------------------------------------------------------------- */

test("cancelling the picker changes nothing, and choosing a file asks the shell again", async () => {
  let asked = fakePort({ status: FOUND, choose: { cancelled: true } });
  let block = engineSection(state("0.4.0"));
  await settled();
  block.findAll("button").find((n) => n.textContent === Str.t("common.choose")).fire("click");
  await settled();
  assert.equal(asked.choose, 1);
  assert.equal(asked.status, 1, "a cancelled picker is not a new answer");

  asked = fakePort({ status: FOUND, choose: { path: "/elsewhere/prudence", version: "0.4.0" } });
  block = engineSection(state("0.4.0"));
  await settled();
  block.findAll("button").find((n) => n.textContent === Str.t("common.choose")).fire("click");
  await settled();
  assert.equal(asked.status, 2, "a chosen file is a new answer and the shell is asked");
});

/* --- the runner and the strip -------------------------------------------------------- */

test("a run says it is going, then says what the engine said", async () => {
  const strip = engineActivity();
  let release = () => {};
  fakePort({
    run: () => new Promise((resolve) => (release = () => resolve({ action: "ingest", ok: true, sessions: 151 }))),
  });

  const going = run("ingest");
  assert.equal(strip.hidden, false);
  assert.equal(strip.find(".engine-said").textContent, Str.t("menu.ingesting"));

  release();
  await going;
  assert.equal(
    strip.find(".engine-said").textContent,
    Str.t("engine.ingestFinished.sessions", Fmt.sessions(151))
  );
});

test("the session count is the engine's own figure, and its absence is not a zero", async () => {
  const strip = engineActivity();
  fakePort({ run: Promise.resolve({ action: "ingest", ok: true, sessions: null }) });
  await run("ingest");
  assert.equal(strip.find(".engine-said").textContent, Str.t("menu.ingestFinished"));
});

test("a written review is reported with the id the engine gave it", async () => {
  const strip = engineActivity();
  fakePort({ run: Promise.resolve({ action: "review", ok: true, reviewId: 2 }) });
  await run("review");
  assert.equal(strip.find(".engine-said").textContent, Str.t("menu.reviewWrittenId", "2"));
});

/* The readiness rule belongs to the engine. The app shows its sentence and offers the one
   way past it, which is the reader's decision and not the app's. */
test("a review the engine declines shows its reason and offers to write anyway", async () => {
  const strip = engineActivity();
  const reason = "not ready: 2 new sessions since 2026-09-14 (needs 5).";
  const asked = fakePort({
    run: (action, force) =>
      Promise.resolve(
        force
          ? { action: "review", ok: true, reviewId: 3 }
          : { action: "review", ok: false, notReady: true, reason }
      ),
  });

  await run("review");
  const said = strip.findAll(".engine-said").map((node) => node.textContent);
  assert.equal(said[0], Str.t("review.notReady.title"));
  assert.equal(said[1], reason, "the engine's own sentence, printed as it came");
  assert.deepEqual(
    strip.findAll("button").map((node) => node.textContent),
    [Str.t("review.writeAnyway"), Str.t("common.cancel")]
  );

  const write = strip.findAll("button")[0];
  write.fire("click");
  await settled();
  assert.deepEqual(asked.runs, [
    { action: "review", force: false },
    { action: "review", force: true },
  ]);
  assert.equal(strip.find(".engine-said").textContent, Str.t("menu.reviewWrittenId", "3"));
});

test("a review with no reason still says the engine declined", async () => {
  const strip = engineActivity();
  fakePort({ run: Promise.resolve({ action: "review", notReady: true, reason: null }) });
  await run("review");
  const said = strip.findAll(".engine-said").map((node) => node.textContent);
  assert.deepEqual(said, [Str.t("review.notReady.title"), Str.t("menu.reviewNotReady")]);
});

test("a run that fails says so with the reason, and never silently does nothing", async () => {
  const strip = engineActivity();
  fakePort({
    run: Promise.resolve({
      action: "ingest",
      ok: false,
      errorKind: "failed",
      error: "No repository is enabled. Run `prudence init`.",
    }),
  });
  await run("ingest");
  const said = strip.findAll(".engine-said").map((node) => node.textContent);
  assert.equal(said[0], Str.t("engine.failed.title"));
  assert.equal(said[1], Str.t("engine.error.failed"));
  assert.equal(said[2], "No repository is enabled. Run `prudence init`.");
  assert.equal(strip.hidden, false);
});

/* The case a swallowed rejection turns into a strip that reads "Ingesting..." for ever. */
test("a shell that does not answer at all is reported too", async () => {
  const strip = engineActivity();
  fakePort({ run: Promise.reject(new Error("the shell went away")) });
  await run("ingest");
  const said = strip.findAll(".engine-said").map((node) => node.textContent);
  assert.equal(said[0], Str.t("engine.failed.title"));
  assert.equal(said[1], "the shell went away");
});

test("a second run while one is going is refused rather than started", async () => {
  const strip = engineActivity();
  let release = () => {};
  const asked = fakePort({
    run: () => new Promise((resolve) => (release = () => resolve({ action: "ingest", ok: true }))),
  });

  const going = run("ingest");
  await run("review");
  assert.equal(strip.find(".engine-said").textContent, Str.t("engine.busy"));
  assert.deepEqual(asked.runs, [{ action: "ingest", force: false }]);

  release();
  await going;
});

test("with no shell at all the strip says the engine is not there", async () => {
  const strip = engineActivity();
  ENGINE.port = null;
  await run("review");
  assert.equal(strip.find(".engine-said").textContent, Str.t("menu.engineMissing"));
});

/* --- the wiring ---------------------------------------------------------------------- */

test("the wiring sets the Review screen's seam and puts the strip on the page", () => {
  const before = document.body.children.length;
  try {
    wireEngine();
    assert.equal(typeof REVIEW_NOW.run, "function", "the Review now button is live");
    assert.equal(document.body.children.length, before + 1);
    assert.equal(document.body.children[before].className, "engine-activity");
  } finally {
    REVIEW_NOW.run = null;
    ENGINE.port = null;
  }
});

/* --- the strings --------------------------------------------------------------------- */

/** Every word `EngineError::kind` can send, read out of the Rust rather than listed here:
 *  a new failure kind with no sentence would otherwise reach the reader as a key. */
function failureKinds() {
  const source = readFileSync(join(app, "src-tauri/src/engine.rs"), "utf8");
  const start = source.indexOf("pub fn kind(&self) -> &'static str {");
  assert.ok(start > 0, "engine.rs no longer has EngineError::kind");
  const body = source.slice(start, source.indexOf("\n    }\n", start));
  return [...body.matchAll(/=>\s*"([A-Za-z]+)"/g)].map((match) => match[1]);
}

test("every failure the shell can report has a sentence in both languages", () => {
  // The two kinds that do not follow `engine.error.<kind>`, each because the word means
  // two things: "not found" is either nothing anywhere or a file that cannot be run, and
  // "busy" is about this app rather than about the engine.
  const otherwise = {
    notFound: ["menu.engineMissing", "engine.error.notExecutable"],
    busy: ["engine.busy"],
  };
  const kinds = failureKinds();
  assert.ok(kinds.length >= 4, `only found ${kinds.length} failure kinds in engine.rs`);
  for (const kind of kinds) {
    for (const key of otherwise[kind] ?? [`engine.error.${kind}`]) {
      for (const language of Str.LANGUAGES) {
        assert.notEqual(Str.tIn(language, key), key, `${language} has no ${key} (kind ${kind})`);
      }
    }
  }
});

test("every key this block asks for is in both tables", () => {
  const source = readFileSync(join(app, "src/ui/engine-section.js"), "utf8");
  const keys = [...source.matchAll(/\bt\(\s*"([^"]+)"/g)].map((match) => match[1]);
  assert.ok(keys.length > 15, `only found ${keys.length} keys in the block`);
  for (const language of Str.LANGUAGES) {
    for (const key of keys) {
      assert.notEqual(Str.tIn(language, key), key, `${language} has no ${key}`);
    }
  }
});

test("the block draws in Chinese without falling back to a key", async () => {
  Str.setLang("zh-Hans");
  try {
    fakePort({ status: FOUND });
    const block = engineSection(state("0.3.1"));
    await settled();
    const text = block.textContent;
    assert.ok(!/engine\./.test(text), `a key reached the page: ${text}`);
    assert.ok(!/settings\./.test(text), `a key reached the page: ${text}`);
    assert.match(text, /版本 0\.4\.0/);
  } finally {
    Str.setLang("en");
  }
});
