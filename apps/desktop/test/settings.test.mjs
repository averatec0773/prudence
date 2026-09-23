/* The Settings screen: four tabs of controls. Which repositories are recorded was a fifth
 * and is a screen of its own now, with its own suite: `test/repositories.test.mjs`.
 *
 * What these guard, in order: that the four tabs are there and only one is open, that the
 * prose the founder asked to have taken off the screen is gone, that **every control
 * writes through the shell** rather than drawing a switch that does nothing, that a
 * control is set from the shell's answer and not from what was asked for, that the Model
 * tab shows a variable name and never a key, that the About tab's links go through the
 * shell by name, and that the whole thing draws in Chinese with no English prose left.
 *
 * The screen is exercised against the small DOM in `test/dom.mjs`, for the reason given
 * there: `node --test` has no browser, and a shim of the handful of operations
 * `design/dom.js` uses makes "a screen returns one element and appends nothing to the
 * page" a checkable rule. The shell is a fake port, which is the only way to press a
 * control that would otherwise open a file picker or register a login item.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { installDom } from "./dom.mjs";

installDom();

const here = dirname(fileURLToPath(import.meta.url));
const app = join(here, "..");
const FIXTURE = join(app, "fixtures/store.db");

import * as Str from "../src/text/strings.js";
// `any`, deliberately, as in the other screen tests: the tree this returns is the shim's
// and asking it for `find` is the whole point of the shim.
const { SETTINGS, TABS, settings } = /** @type {any} */ (
  await import("../src/ui/settings.js")
);
const { ENGINE } = /** @type {any} */ (await import("../src/ui/engine-section.js"));
const { MODEL_ANSWER } = /** @type {any} */ (
  await import("../src/store/asked.js")
);

for (const language of Str.LANGUAGES) {
  Str.load(
    language,
    JSON.parse(readFileSync(join(app, `src/text/strings.${language}.json`), "utf8"))
  );
}
Str.setLang("en");

/** The fixture's own rows, read with `sqlite3` so the test depends on no driver. */
function fixture(sql) {
  const out = execFileSync("sqlite3", ["-json", FIXTURE, sql], { encoding: "utf8" }).trim();
  return out ? JSON.parse(out) : [];
}

const STATUS = fixture("SELECT * FROM app_status;")[0];

const MODEL = {
  backend: "anthropic",
  modelId: "claude-sonnet-5",
  keyVariable: "ANTHROPIC_API_KEY (not set)",
  maxTokens: "1024",
  language: "system (now en, English; model prose only)",
  languageKey: "system",
  explain: "off (review.explain)",
  configPath: "/tmp/a copy/config.toml",
};

const INFO = {
  version: "0.5.0",
  database: "/tmp/a copy/prudence.db",
  supported_contract: [2, 3],
  language: null,
  settings: {
    language: "system",
    appearance: "system",
    ingestEveryMinutes: 0,
    openAtLogin: false,
    loginError: null,
  },
  platform: [
    ["platform", "macos"],
    ["NSAppKitVersionNumber", "2565.1"],
  ],
};

/** Let every queued promise callback run. The Model tab draws first and fills when the
 *  engine answers, so there is always one turn between the two. A batch is a chain of
 *  already-resolved promises, so one turn drains the whole of it. */
const settled = () => new Promise(setImmediate);

function fakePort(overrides = {}) {
  // The engine's answer is remembered against the store it was taken for
  // (`store/asked.js`), and every test here draws the same fixture: without this the
  // second test would be handed the first one's answer, and a test of a refusal would be
  // handed the answer from before it.
  MODEL_ANSWER.forget();
  const asked = {
    language: [],
    appearance: [],
    login: [],
    interval: [],
    modelLanguage: [],
    links: [],
  };
  let now = { ...INFO.settings, ...(overrides.settings ?? {}) };
  const answer = () => Promise.resolve(now);
  SETTINGS.port = {
    read: answer,
    language: (code) => {
      asked.language.push(code);
      now = { ...now, language: code };
      return answer();
    },
    appearance: (code) => {
      asked.appearance.push(code);
      now = { ...now, appearance: code };
      return answer();
    },
    openAtLogin: (on) => {
      asked.login.push(on);
      // The system is allowed to refuse, and the test that matters is the one where it
      // does: `overrides.loginRefuses` keeps the answer false whatever was asked.
      now = overrides.loginRefuses
        ? { ...now, openAtLogin: false, loginError: "no login item for a copy outside /Applications" }
        : { ...now, openAtLogin: on };
      return answer();
    },
    timedIngest: (minutes) => {
      asked.interval.push(minutes);
      now = { ...now, ingestEveryMinutes: minutes };
      return answer();
    },
    model: () => Promise.resolve(overrides.model ?? MODEL),
    modelLanguage: (code) => {
      asked.modelLanguage.push(code);
      return Promise.resolve({ ...MODEL, languageKey: code });
    },
    link: (name) => {
      asked.links.push(name);
      return Promise.resolve();
    },
  };
  asked.settings = () => now;
  return asked;
}

/** Draw the screen, with the shell's answer carried in `info` the way `window.js` does. */
function screenFor(overrides = {}, info = INFO, asked = null) {
  const data = { status: STATUS, sessions: [], ...overrides };
  const merged = asked ? { ...info, settings: asked.settings() } : info;
  let tree = null;
  const state = {
    data,
    info: merged,
    project: null,
    range: "30d",
    bucket: null,
    ingesting: false,
    onBucket() {},
    onProject() {},
    // The General tab redraws from the shell's answer. The test redraws in place, which
    // is what `window.js` does, so an assertion after a press reads the new tree.
    redraw() {
      tree = settings(state);
    },
  };
  tree = settings(state);
  return {
    get tree() {
      return tree;
    },
    state,
  };
}

/** Open a tab by pressing its own button, which is the only way the app opens one. */
function open(screen, key) {
  // `openTab` is module state, on purpose (see `ui/settings.js`), so a test that wants a
  // particular tab has to say so rather than assuming the one the last test left open.
  const label = Str.t(TABS.find((tab) => tab.key === key).label);
  const button = screen.tree.findAll(".tab").find((node) => node.textContent === label);
  assert.ok(button, `no ${key} tab`);
  button.fire("click");
  return screen;
}

/** Everything visible: the open pane and the strip above it. */
function visible(screen) {
  const strip = screen.tree.find(".tabs");
  const panes = screen.tree.findAll(".tab-pane").filter((pane) => !pane.hidden);
  return [strip, ...panes].map((node) => node.textContent).join("");
}

/** Every control in the open pane. */
function controls(screen) {
  return screen.tree
    .findAll(".tab-pane")
    .filter((pane) => !pane.hidden)
    .flatMap((pane) => pane.findAll("button"));
}

/* --- the shape of the screen --------------------------------------------------------- */

test("the screen returns one element and appends nothing to the page", () => {
  const screen = screenFor();
  assert.equal(screen.tree.localName, "div");
  assert.ok(screen.tree.className.split(/\s+/).includes("screen-body"));
});

test("four tabs, left to right, and exactly one of them open", () => {
  fakePort();
  const screen = screenFor();
  assert.deepEqual(
    screen.tree.findAll(".tab").map((node) => node.textContent),
    ["General", "Engine", "Model", "About"]
  );
  const shown = screen.tree.findAll(".tab-pane").filter((pane) => !pane.hidden);
  assert.equal(shown.length, 1, "one pane at a time");
  assert.deepEqual(
    screen.tree.findAll(".tab").map((node) => node.getAttribute("aria-selected")),
    ["true", "false", "false", "false"]
  );
});

/* The founder's own words: "I do not need the what-is-recorded and never-recorded prose
   there". One link in About is what is left of it. */
test("the record's prose is off the screen and one link is left in its place", () => {
  const asked = fakePort();
  const screen = screenFor({}, INFO, asked);
  const everything = screen.tree.textContent;
  for (const gone of [
    "This app uploads nothing",
    "Your sessions' own files are archived unchanged",
    "check your employer's policy",
    "This screen reads the store and changes nothing",
  ]) {
    assert.equal(everything.includes(gone), false, `the prose is still on the screen: ${gone}`);
  }

  open(screen, "about");
  const link = controls(screen).find((node) => node.textContent === Str.t("settings.about.recorded"));
  assert.ok(link, "About has no link to what is recorded");
  link.fire("click");
  assert.deepEqual(asked.links, ["recorded"]);
});

test("no tab opens on a placeholder", () => {
  fakePort();
  const screen = screenFor();
  assert.equal(screen.tree.textContent.includes("Not built yet"), false);
  assert.equal(screen.tree.textContent.includes("arrives with"), false);
});

/* --- General ------------------------------------------------------------------------- */

test("every control on General writes through the shell", () => {
  const asked = fakePort();
  const screen = open(screenFor({}, INFO, asked), "general");

  const press = (label) => {
    const button = controls(screen).find((node) => node.textContent === label);
    assert.ok(button, `no control labelled ${label}`);
    button.fire("click");
  };

  press("简体中文");
  press(Str.t("settings.appearance.dark"));
  press(Str.t("settings.choice.on"));
  press(Str.t("settings.interval.30m"));

  assert.deepEqual(asked.language, ["zh-Hans"]);
  assert.deepEqual(asked.appearance, ["dark"]);
  assert.deepEqual(asked.login, [true]);
  assert.deepEqual(asked.interval, [30]);
});

/* A key a screen asks for and no table carries is drawn as itself: the timed ingest's Off
   read `settings.interval.off` on the General tab until 2026-09-22. Nothing asserted it,
   because `strings.test.mjs` compares the two tables with each other and not with the
   screens, so the guard is here: no label on this screen may look like a key. */
test("no control on General is labelled with a catalogue key", () => {
  fakePort();
  const screen = open(screenFor(), "general");
  for (const label of controls(screen).map((node) => node.textContent)) {
    assert.equal(/^[a-z]+(\.[A-Za-z0-9]+)+$/.test(label), false, `${label} is a key, not a word`);
  }
});

test("the four settings offer exactly the choices the shell will accept", () => {
  fakePort();
  const screen = open(screenFor(), "general");
  const labels = controls(screen).map((node) => node.textContent);
  for (const wanted of [
    Str.t("settings.choice.system"),
    "English",
    "简体中文",
    Str.t("settings.appearance.light"),
    Str.t("settings.appearance.dark"),
    Str.t("settings.choice.on"),
    Str.t("settings.choice.off"),
    Str.t("settings.interval.15m"),
    Str.t("settings.interval.30m"),
    Str.t("settings.interval.1h"),
    Str.t("settings.interval.6h"),
  ]) {
    assert.ok(labels.includes(wanted), `General does not offer ${wanted}`);
  }
});

/* A control is ticked from what the shell answered, never from what was asked for. */
test("a control shows what is in force, not what was chosen", () => {
  const asked = fakePort({ settings: { ingestEveryMinutes: 60 } });
  const screen = open(screenFor({}, INFO, asked), "general");
  const ticked = controls(screen)
    .filter((node) => node.getAttribute("aria-checked") === "true")
    .map((node) => node.textContent);
  assert.ok(ticked.includes(Str.t("settings.interval.1h")), `ticked: ${ticked}`);
  // And nothing else in that control is ticked: the interval's other four choices,
  // including its own Off, are not. ("Off" appears twice on this tab, and open-at-login's
  // own Off is legitimately ticked, so the count is what says the interval has one.)
  const intervals = [
    Str.t("settings.interval.15m"),
    Str.t("settings.interval.30m"),
    Str.t("settings.interval.1h"),
    Str.t("settings.interval.6h"),
  ];
  assert.deepEqual(
    ticked.filter((label) => intervals.includes(label)),
    [Str.t("settings.interval.1h")]
  );
});

/* macOS can refuse a login item for a copy that is not where it expects one. A switch
   that ticks itself on a refusal is a switch that lies about the state of the machine. */
test("a login item the system refused is not shown as on, and the reason is printed", () => {
  const asked = fakePort({ loginRefuses: true });
  const screen = open(screenFor({}, INFO, asked), "general");
  controls(screen).find((node) => node.textContent === Str.t("settings.choice.on")).fire("click");

  const after = open(screenFor({}, INFO, asked), "general");
  const ticked = controls(after)
    .filter((node) => node.getAttribute("aria-checked") === "true")
    .map((node) => node.textContent);
  assert.ok(ticked.includes(Str.t("settings.choice.off")), "the refused login item ticked itself on");
  assert.ok(visible(after).includes(Str.t("settings.openAtLogin.refused")));
  assert.ok(visible(after).includes("outside /Applications"), "the system's own reason is missing");
});

test("no shell behind the page draws a sentence rather than controls that do nothing", () => {
  SETTINGS.port = null;
  const screen = open(screenFor(), "general");
  assert.ok(visible(screen).includes(Str.t("settings.noShell")));
  assert.deepEqual(controls(screen), []);
});

/* --- Engine ---------------------------------------------------------------------------
 *
 * The block itself is `ui/engine-section.js` and has its own suite. What this file owns is
 * that the tab places it, and that the store's own provenance is on the same tab.
 */

test("the Engine tab carries the engine block and where the store is", () => {
  fakePort();
  ENGINE.port = null;
  const screen = screenFor();
  open(screen, "engine");
  const pane = screen.tree.findAll(".tab-pane").filter((one) => !one.hidden)[0];
  assert.ok(pane.find(".engine-section"), "the engine block is not on the Engine tab");
  const text = pane.textContent;
  assert.ok(text.includes(INFO.database), "the store's path is not on the Engine tab");
  assert.ok(text.includes("PRUDENCE_DATA_DIR"), "nothing says how the path was found");
  assert.ok(text.includes(String(STATUS.app_contract_version)), "the contract is missing");
});

test("a version number is printed ungrouped, and a step that never ran is left out", () => {
  fakePort();
  const grouped = screenFor({ status: { ...STATUS, parser_version: 1234 } });
  open(grouped, "engine");
  assert.ok(visible(grouped).includes("1234"));
  assert.equal(visible(grouped).includes("1,234"), false, "a version was grouped like a quantity");

  const without = screenFor({ status: { ...STATUS, hook_fact_version: null } });
  open(without, "engine");
  assert.equal(
    visible(without).includes(Str.t("settings.version.hook")),
    false,
    "a step with no version was drawn"
  );
  assert.ok(visible(without).includes(Str.t("settings.version.parser")));
});

/* --- Model ---------------------------------------------------------------------------- */

test("the Model tab prints what the engine said, and the key as a name only", async () => {
  fakePort();
  const screen = screenFor();
  open(screen, "model");
  await settled();
  const text = visible(screen);
  for (const value of [MODEL.backend, MODEL.modelId, MODEL.maxTokens, MODEL.explain, MODEL.configPath]) {
    assert.ok(text.includes(value), `${value} is not on the Model tab`);
  }
  assert.ok(text.includes("ANTHROPIC_API_KEY"), "the key's variable name is missing");
  assert.ok(text.includes("(not set)"), "whether the key is set is missing");
  // The promise of the tab: nothing here is a key, and the app says it calls no model.
  assert.ok(text.includes(Str.t("settings.model.note")));
});

test("the prose language is the engine's setting, written with the engine's own command", async () => {
  const asked = fakePort();
  const screen = screenFor();
  open(screen, "model");
  await settled();
  const ticked = controls(screen)
    .filter((node) => node.getAttribute("aria-checked") === "true")
    .map((node) => node.textContent);
  assert.ok(ticked.includes(Str.t("settings.choice.system")), `ticked: ${ticked}`);

  controls(screen).find((node) => node.textContent === "简体中文").fire("click");
  await settled();
  assert.deepEqual(asked.modelLanguage, ["zh-Hans"]);
});

test("an engine that cannot be asked says so rather than drawing an empty tab", async () => {
  fakePort();
  SETTINGS.port.model = () => Promise.reject(new Error("notFound"));
  const screen = screenFor();
  open(screen, "model");
  await settled();
  assert.ok(visible(screen).includes(Str.t("settings.model.unread")));
});

/* --- how often the engine is asked ------------------------------------------------------
 *
 * The Model pane asks the engine a question of its own, and every pane is built whichever
 * tab is open. The screen is redrawn on every store change, and an ingest announces itself
 * to the store watcher about eight times as it works, so leaving the window on Settings
 * during one 230-second run cost fourteen extra processes when the repositories were still
 * a tab here. Measured on 2026-09-22 with `PRUDENCE_PRESS="Engine > Ingest now"`.
 *
 * The rule is `store/asked.js`'s: ask once per store, remember the answer against what the
 * engine wrote, ask again when that moves.
 */

/** What an ingest does to the pages: the same store, announced again and again. */
function announce(screen, times) {
  for (let i = 0; i < times; i += 1) screen.state.redraw();
}

test("eight announcements about one store ask the engine once", async () => {
  const asked = fakePort();
  let models = 0;
  const model = SETTINGS.port.model;
  SETTINGS.port.model = () => {
    models += 1;
    return model();
  };

  const screen = screenFor({}, INFO, asked);
  await settled();
  announce(screen, 7);
  await settled();

  assert.equal(models, 1, `the model settings were read ${models} times for one store`);
});

/* An ingest or a review is a different store, and the next draw asks about it. That is what
   makes this a memo that follows the store rather than an answer frozen at launch. */
test("a store the engine has written since is asked about again", async () => {
  const asked = fakePort();
  let models = 0;
  const model = SETTINGS.port.model;
  SETTINGS.port.model = () => {
    models += 1;
    return model();
  };
  const screen = screenFor({}, INFO, asked);
  await settled();
  assert.equal(models, 1);

  screen.state.data = { ...screen.state.data, status: { ...STATUS, last_ingest_at: "2099-01-01T00:00:00Z" } };
  screen.state.redraw();
  await settled();
  assert.equal(models, 2, "the model settings did not follow the store");
});

/* --- About ----------------------------------------------------------------------------- */

test("About names this build, the engine, the licence, the machine and the developer", () => {
  const asked = fakePort();
  const screen = screenFor({}, INFO, asked);
  open(screen, "about");
  const text = visible(screen);
  assert.ok(text.includes(INFO.version), "the app's own version is missing");
  assert.ok(text.includes(String(STATUS.engine_version)), "the engine's version is missing");
  assert.ok(text.includes("Apache-2.0"), "the licence is missing");
  assert.ok(text.includes("NSAppKitVersionNumber"), "the platform the shell described is missing");
  assert.ok(text.includes("averatec0773"), "the developer is missing");
});

/* The page asks for a link **by name**; the shell owns the address. A command that took a
   URL would be a command that opens whatever it was handed. */
test("every link on About is asked for by name, and no URL is on the page", () => {
  const asked = fakePort();
  const screen = screenFor({}, INFO, asked);
  open(screen, "about");
  for (const label of [
    Str.t("settings.about.project"),
    Str.t("settings.about.developerLink"),
    Str.t("settings.about.recorded"),
  ]) {
    const button = controls(screen).find((node) => node.textContent === label);
    assert.ok(button, `About has no ${label} link`);
    button.fire("click");
  }
  assert.deepEqual(asked.links, ["project", "developer", "recorded"]);
  assert.equal(screen.tree.textContent.includes("https://"), false, "a URL is printed on the page");
});

/* --- the whole thing, in both languages ------------------------------------------------ */

test("a store with no status row still draws, and says the figures are not read", () => {
  fakePort();
  ENGINE.port = null;
  const screen = screenFor({ status: null });
  open(screen, "engine");
  const text = visible(screen);
  assert.ok(text.includes(Str.t("settings.store.unread")), "nothing says the store was not read");
  assert.ok(text.includes(INFO.database), "the path is missing");
  assert.equal(text.includes("undefined"), false, text);
  assert.equal(text.includes("null"), false, text);
});

test("no shell info at all draws rather than throwing", () => {
  fakePort();
  const screen = open(screenFor({}, undefined), "general");
  assert.ok(screen.tree.findAll(".tab").length === 4, "the screen did not draw");
  assert.equal(screen.tree.textContent.includes("undefined"), false);
});

test("every tab draws in Chinese with no English prose left in it", async () => {
  Str.setLang("zh-Hans");
  try {
    const asked = fakePort();
    for (const tab of TABS) {
      const screen = screenFor({}, INFO, asked);
      open(screen, tab.key);
      await settled();
      const text = visible(screen);
      for (const key of [
        "settings.general.note",
        "settings.store.note",
        "settings.model.note",
        "settings.about.note",
      ]) {
        assert.equal(
          text.includes(Str.tIn("en", key)),
          false,
          `${tab.key}: the English of ${key} is still on the screen`
        );
      }
    }
    // The technical tokens stay as they are: a variable, a path and a command are not
    // translated, and a reader has to be able to type them.
    const engine = screenFor({}, INFO, asked);
    open(engine, "engine");
    assert.ok(visible(engine).includes("PRUDENCE_DATA_DIR"), "the variable was translated");
    assert.ok(visible(engine).includes(INFO.database), "the path was translated");
  } finally {
    Str.setLang("en");
  }
});
