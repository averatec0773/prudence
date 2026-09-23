/* The engine block on the Settings screen's Engine tab, and the wiring.
 *
 * Everything here is driven through a fake port, which is the only way to exercise the
 * states that matter: nothing found, a file found and refused, an install that fails. A
 * machine in each of those states is not something a test can arrange, and a test that
 * only ever sees the happy one would pass on a build where every failure draws a blank
 * area.
 *
 * Running the engine is the toolbar's now, and its tests are `test/activity.test.mjs`.
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
// `any`, deliberately: the tree the block returns is the shim's, and asking it for
// `find` is the whole point of the shim.
const { ENGINE, engineSection } = /** @type {any} */ (
  await import("../src/ui/engine-section.js")
);
const { REVIEW_NOW } = /** @type {any} */ (await import("../src/ui/review.js"));
const { wireWindow } = /** @type {any} */ (await import("../src/ui/wiring.js"));

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
 * @param {{ status?: any, choose?: any, install?: any }} answers
 */
function fakePort(answers = {}) {
  const asked = {
    status: 0,
    choose: 0,
    forget: 0,
    installs: [],
    links: [],
    progress: null,
    stopped: false,
  };
  ENGINE.port = {
    status: () => {
      asked.status += 1;
      const answer = answers.status;
      return Promise.resolve(typeof answer === "function" ? answer(asked.status) : answer);
    },
    choose: () => {
      asked.choose += 1;
      return Promise.resolve(answers.choose ?? { cancelled: true });
    },
    forget: () => {
      asked.forget += 1;
      return Promise.resolve();
    },
    install: (upgrade) => {
      asked.installs.push(upgrade);
      const answer = answers.install;
      return Promise.resolve(typeof answer === "function" ? answer(upgrade) : (answer ?? { ok: true }));
    },
    // The stream of lines uv is printing. A test hands the handler back so it can be
    // called, which is how "the status area follows the process" is asserted without a
    // process.
    onInstallProgress: (handler) => {
      asked.progress = handler;
      return Promise.resolve(() => {
        asked.stopped = true;
      });
    },
    link: (name) => {
      asked.links.push(name);
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
  // Installing is the primary action of a machine with no engine; the other two are ways
  // of finding one that is already there.
  assert.deepEqual(labels, [
    Str.t("engine.install.install"),
    Str.t("common.tryAgain"),
    Str.t("common.choose"),
  ]);
  // No ingest or review for an engine that is not there: a button that cannot work is
  // worse than no button.
  assert.ok(!labels.includes(Str.t("menu.ingestNow")));
  assert.ok(!labels.includes(Str.t("menu.reviewNow")));
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

/* Verified before it is trusted. The reader chose a file and the shell would not keep it;
   redrawing the block without a word would leave them looking at what they tried to
   change with nothing said about their choice. */
test("a file the shell refuses is reported, not swallowed", async () => {
  const asked = fakePort({
    status: FOUND,
    choose: { path: "/Applications/Calculator.app", errorKind: "notFound" },
  });
  const block = engineSection(state("0.4.0"));
  await settled();
  block.findAll("button").find((n) => n.textContent === Str.t("common.choose")).fire("click");
  await settled();

  assert.equal(asked.status, 2, "the block is drawn again from the shell's answer");
  // In the block the reader was changing, in the area under its actions, and in the block
  // as it was drawn again: a line written into the old one would be seen by nobody.
  const area = block.find(".engine-install");
  assert.equal(area.hidden, false, "the refusal is not on the block");
  assert.equal(
    area.find(".engine-said").textContent,
    Str.t("engine.rejected", Str.t("engine.error.notExecutable"))
  );
});

/* --- the install button ---------------------------------------------------------------
 *
 * `prudence-core` is not on PyPI yet, so the ordinary outcome today is a failure and the
 * manual route. That is the state these tests spend most of their lines on, because it is
 * the one a reader will actually meet.
 */

test("with no engine the primary action installs, and with one it offers an update", async () => {
  const missing = fakePort({ status: { found: false, errorKind: "notFound" } });
  const without = engineSection(state("0.4.0"));
  await settled();
  const install = without
    .findAll("button")
    .find((node) => node.textContent === Str.t("engine.install.install"));
  assert.ok(install, "no Install button where there is no engine");
  assert.ok(install.className.split(/\s+/).includes("primary"), "installing is the primary action");
  install.fire("click");
  await settled();
  assert.deepEqual(missing.installs, [false], "the button asked for an install, not an upgrade");

  const present = fakePort({ status: { found: true, path: "/x/prudence", version: "0.4.0" } });
  const with_ = engineSection(state("0.4.0"));
  await settled();
  const update = with_
    .findAll("button")
    .find((node) => node.textContent === Str.t("engine.install.update"));
  assert.ok(update, "no Update button where the engine is there");
  assert.equal(update.className.trim(), "btn", "updating is a secondary action");
  update.fire("click");
  await settled();
  assert.deepEqual(present.installs, [true]);
});

test("uv's lines appear while it is still printing them, and the stream is closed after", async () => {
  let finish;
  const asked = fakePort({
    status: { found: false, errorKind: "notFound" },
    install: () => new Promise((resolve) => { finish = resolve; }),
  });
  const block = engineSection(state("0.4.0"));
  await settled();
  block.findAll("button").find((n) => n.textContent === Str.t("engine.install.install")).fire("click");
  await settled();

  const area = block.find(".engine-install");
  assert.ok(area, "no area to report into");
  assert.equal(area.hidden, false);
  assert.ok(area.textContent.includes(Str.t("engine.install.running")));

  assert.equal(typeof asked.progress, "function", "nothing subscribed to uv's output");
  asked.progress(["Resolved 12 packages", "Prepared 3 packages"]);
  assert.ok(area.textContent.includes("Prepared 3 packages"), area.textContent);

  finish({ ok: true });
  await settled();
  assert.ok(asked.stopped, "the stream was left open after the install finished");
});

test("a failure shows the engine's own output and the two commands to run by hand", async () => {
  const manual = ["curl -LsSf https://astral.sh/uv/install.sh | sh", 'uv tool install --python 3.12 "prudence-core[mcp,model]"'];
  const asked = fakePort({
    status: { found: false, errorKind: "notFound" },
    install: () => Promise.resolve({
      ok: false,
      errorKind: "failed",
      lines: ["error: Distribution `prudence-core` not found in the package registry"],
      manual,
    }),
  });
  const block = engineSection(state("0.4.0"));
  await settled();
  block.findAll("button").find((n) => n.textContent === Str.t("engine.install.install")).fire("click");
  await settled();

  const area = block.find(".engine-install");
  assert.ok(area.textContent.includes(Str.t("engine.install.failed")));
  assert.ok(area.textContent.includes("not found in the package registry"), area.textContent);
  for (const command of manual) {
    assert.ok(area.textContent.includes(command), `the manual route is missing ${command}`);
  }
  // The commands are there to be copied, and the window turns selection off everywhere
  // else; the README link is the other half of the way out.
  assert.ok(area.find(".is-copyable"), "the commands cannot be selected");
  area.findAll("button").find((n) => n.textContent === Str.t("engine.install.readme")).fire("click");
  assert.deepEqual(asked.links, ["install"], "the link is the README's install section");
});

test("uv missing altogether says so, and still gives the way out", async () => {
  fakePort({
    status: { found: false, errorKind: "notFound" },
    install: () => Promise.resolve({ ok: false, errorKind: "noUv", lines: [], manual: ["a", "b"] }),
  });
  const block = engineSection(state("0.4.0"));
  await settled();
  block.findAll("button").find((n) => n.textContent === Str.t("engine.install.install")).fire("click");
  await settled();
  const area = block.find(".engine-install");
  assert.ok(area.textContent.includes(Str.t("engine.install.noUv")));
  assert.ok(area.textContent.includes(Str.t("engine.install.manual")));
});

/* --- the wiring ---------------------------------------------------------------------- */

test("the wiring fills in every port, the Review seam, and puts the run report on the page", async () => {
  const { SETTINGS } = /** @type {any} */ (await import("../src/ui/settings.js"));
  const { REPOSITORIES } = /** @type {any} */ (await import("../src/ui/repositories.js"));
  const { ACTIVITY } = /** @type {any} */ (await import("../src/ui/activity.js"));
  const before = document.body.children.length;
  try {
    wireWindow();
    assert.equal(typeof REVIEW_NOW.readiness, "function", "the readiness line has no engine behind it");
    // Every port, because `wiring.js` is the only file under `src/ui/` that may call the
    // bridge and a port left null is a screen full of controls that do nothing.
    assert.ok(ENGINE.port, "the engine block has no shell behind it");
    assert.ok(SETTINGS.port, "the settings tabs have no shell behind them");
    for (const name of ["read", "language", "appearance", "openAtLogin", "timedIngest", "model", "modelLanguage", "link"]) {
      assert.equal(typeof SETTINGS.port[name], "function", `the settings port has no ${name}`);
    }
    for (const name of ["status", "choose", "forget", "install", "onInstallProgress", "link"]) {
      assert.equal(typeof ENGINE.port[name], "function", `the engine port has no ${name}`);
    }
    for (const name of ["scan", "level"]) {
      assert.equal(typeof REPOSITORIES.port[name], "function", `the repositories port has no ${name}`);
    }
    for (const name of ["read", "onActivity", "onProgress", "run"]) {
      assert.equal(typeof ACTIVITY.port[name], "function", `the toolbar's port has no ${name}`);
    }
    assert.equal(document.body.children.length, before + 1);
    assert.equal(document.body.children[before].className, "run-report");
  } finally {
    REVIEW_NOW.readiness = null;
    ENGINE.port = null;
    SETTINGS.port = null;
    REPOSITORIES.port = null;
    ACTIVITY.port = null;
  }
});

/* --- the strings --------------------------------------------------------------------- */

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

/* Replacing the executable under an ingest that is using it is not something to offer,
 * wherever the ingest was started. Install and Update follow the shell's own answer about
 * what is running; Choose, Clear and Try again start nothing and stay. */
test("a run going anywhere disables Update, and its end brings it back", async () => {
  const { ACTIVITY, take } = /** @type {any} */ (await import("../src/ui/activity.js"));
  fakePort({ status: FOUND });
  const block = /** @type {any} */ (engineSection(state("0.4.0")));
  await settled();
  const labels = () =>
    block.findAll("button").map((node) => [node.textContent, Boolean(node.disabled)]);

  assert.deepEqual(labels().filter(([, off]) => off), [], "something was disabled before any run");

  try {
    take({ running: "ingest", outside: true });
    const during = labels();
    assert.ok(
      during.some(([label, off]) => label === Str.t("engine.install.update") && off),
      `Update was not disabled during a run: ${JSON.stringify(during)}`
    );
    assert.ok(
      during.some(([label, off]) => label === Str.t("common.choose") && !off),
      "Choose was disabled, though it starts no run and is the way out"
    );

    take({ running: null, outside: false });
    assert.deepEqual(labels().filter(([, off]) => off), [], "Update never came back after the run");
  } finally {
    ACTIVITY.now = { running: null, outside: false, progress: null, outcome: null };
    ACTIVITY.mounts.clear();
  }
});
