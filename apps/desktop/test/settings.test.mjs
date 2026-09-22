/* The Settings screen: five tabs of controls.
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
const { SETTINGS, TABS, settings, sourcesOf } = /** @type {any} */ (
  await import("../src/ui/settings.js")
);
const { ENGINE } = /** @type {any} */ (await import("../src/ui/engine-section.js"));
const { MODEL_ANSWER, REPOSITORY_SCAN } = /** @type {any} */ (
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

/** What the engine says when it will not enable a repository, in its own words. English
 *  on a Chinese interface, like every other message from something that is not this app. */
const REFUSAL = "prudence init: no repository called root:2c3f8baf in the scan";

/**
 * A shell that answers whatever the test says, and records what it was asked.
 *
 * Every setter answers with the settings block **as the shell has it**, which is what lets
 * "a refused login item does not tick itself" be a test rather than a hope.
 */
/**
 * The scan `prudence init --scan --json` prints, trimmed to the four shapes the tab has
 * to draw: enabled at a level, enabled at the other, never enabled, gone from disk, and
 * the group of sessions that belong to no repository.
 */
const SCAN = [
  {
    path: "/Users/someone/code/beatos",
    repoKey: "root:df32e8a9",
    sessions: 65,
    firstAt: "2026-05-14T18:02:11.855000+00:00",
    lastAt: "2026-08-06T05:06:51.273000+00:00",
    enabled: true,
    level: "full",
    exists: true,
  },
  {
    path: "/Users/someone/code/averatec-career",
    repoKey: "root:742d2192",
    sessions: 50,
    firstAt: "2026-05-15T16:38:17.649000+00:00",
    lastAt: "2026-09-19T06:57:00.425000+00:00",
    enabled: true,
    level: "metadata-only",
    exists: true,
  },
  {
    path: "/Users/someone/code/offeros",
    repoKey: "root:2c3f8baf",
    sessions: 23,
    firstAt: "2026-07-14T23:12:11.815000+00:00",
    lastAt: "2026-08-18T01:31:25.008000+00:00",
    enabled: false,
    level: null,
    exists: true,
  },
  {
    path: "/Users/someone/code/moved-away",
    repoKey: "root:9e202fea",
    sessions: 11,
    firstAt: "2026-05-07T23:46:49.382000+00:00",
    lastAt: "2026-09-08T18:59:28.507000+00:00",
    enabled: false,
    level: null,
    exists: false,
  },
  {
    path: null,
    repoKey: "no repository",
    sessions: 115,
    firstAt: "2026-04-22T21:12:03.542000+00:00",
    lastAt: "2026-09-22T06:46:17.434000+00:00",
    enabled: false,
    level: null,
    exists: false,
  },
];

function fakePort(overrides = {}) {
  // The two engine answers are remembered against the store they were taken for
  // (`store/asked.js`), and every test here draws the same fixture: without this the
  // second test would be handed the first one's scan, and a test of a refusal would be
  // handed the answer from before it.
  MODEL_ANSWER.forget();
  REPOSITORY_SCAN.forget();
  const asked = {
    language: [],
    appearance: [],
    login: [],
    interval: [],
    modelLanguage: [],
    links: [],
    levels: [],
    // How many times the whole list was read. A batch runs one command per repository and
    // then asks **once**, which is a thing to assert rather than to hope for.
    scans: 0,
  };
  let now = { ...INFO.settings, ...(overrides.settings ?? {}) };
  let scan = overrides.scan ?? SCAN.map((row) => ({ ...row }));
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
    repositories: () => {
      asked.scans += 1;
      return Promise.resolve(scan);
    },
    // The engine's answer, not the click's: the fake moves the row itself and hands the
    // whole scan back, which is what the real command does.
    repositoryLevel: (key, level) => {
      asked.levels.push([key, level]);
      if (overrides.levelRefuses) return Promise.reject(new Error("failed"));
      // `refuseCall: 2` refuses the second command of a batch and no other, which is the
      // only way to ask what a run does when the engine stops half way through one.
      if (overrides.refuseCall && asked.levels.length === overrides.refuseCall) {
        return Promise.reject(new Error(REFUSAL));
      }
      scan = scan.map((row) =>
        row.repoKey === key
          ? { ...row, enabled: level !== "off", level: level === "off" ? null : level }
          : row
      );
      return Promise.resolve(scan);
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
    onBucket() {},
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

test("five tabs, left to right, and exactly one of them open", () => {
  fakePort();
  const screen = screenFor();
  assert.deepEqual(
    screen.tree.findAll(".tab").map((node) => node.textContent),
    ["General", "Engine", "Model", "Repositories", "About"]
  );
  const shown = screen.tree.findAll(".tab-pane").filter((pane) => !pane.hidden);
  assert.equal(shown.length, 1, "one pane at a time");
  assert.deepEqual(
    screen.tree.findAll(".tab").map((node) => node.getAttribute("aria-selected")),
    ["true", "false", "false", "false", "false"]
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

/* --- Repositories -----------------------------------------------------------------------
 *
 * The tab answers the founder's question: "why are only three repositories recorded?"
 * So what is asserted is that the answer is on it (recording is opt-in, and the two lists
 * are told apart), that every figure is the engine's own, and that changing one goes
 * through the shell and redraws from **the engine's answer** rather than from the click.
 */

async function repositoriesTab(overrides = {}) {
  const asked = fakePort(overrides);
  const screen = screenFor({}, INFO, asked);
  open(screen, "repositories");
  await settled();
  return { screen, asked };
}

/** One row, found again from the tree each time: every press redraws the list, so a node
 *  held across a press is a node that is no longer on the screen. */
function rowFor(screen, text) {
  return screen.tree.findAll("tr").find((node) => node.textContent.includes(text));
}

/** Tick the box on each of these rows, one press at a time, as a reader would. */
function choose(screen, names) {
  for (const name of names) rowFor(screen, name).find(".tick").fire("change");
}

/** The bar at the foot of the card, or nothing when no row is ticked. */
function bar(screen) {
  return screen.tree.find(".repo-actions");
}

function pressInBar(screen, label) {
  const button = bar(screen)
    .findAll("button")
    .find((node) => node.textContent === label);
  assert.ok(button, `the action bar offers no ${label}`);
  button.fire("click");
}

test("the tab says recording is opt-in, and tells the two lists apart", async () => {
  const { screen } = await repositoriesTab();
  const text = visible(screen);
  assert.ok(text.includes(Str.t("settings.repositories.note")), "the opt-in sentence is missing");
  assert.ok(text.includes(Str.t("settings.repositories.recorded")), "no recorded block");
  assert.ok(text.includes(Str.t("settings.repositories.found")), "no found-not-recorded block");
  // Both blocks are drawn, and the rows are in the right one.
  const blocks = screen.tree.findAll(".repo-table");
  assert.equal(blocks.length, 2, "the list was not split");
  assert.ok(blocks[0].textContent.includes("beatos"));
  assert.ok(blocks[1].textContent.includes("offeros"));
  assert.equal(blocks[0].textContent.includes("offeros"), false, "a row is in the wrong block");
});

test("every figure on a row is the engine's own", async () => {
  const { screen } = await repositoriesTab();
  const row = rowFor(screen, "beatos");
  assert.ok(row, "the row is not on the tab");
  const text = row.textContent;
  assert.ok(text.includes("beatos"), "the name is missing");
  // The path is drawn from its end and carried whole on the title: see the layout tests.
  assert.equal(row.find(".repo-path").getAttribute("title"), "/Users/someone/code/beatos");
  assert.ok(text.includes("65"), "the session count is missing");
  // The engine's dates, as the reader's language writes a day.
  assert.ok(text.includes("2026"), `the dates are missing: ${text}`);
  // And the control is set from the engine's level.
  const ticked = row
    .findAll("button")
    .filter((node) => node.getAttribute("aria-checked") === "true")
    .map((node) => node.textContent);
  assert.deepEqual(ticked, [Str.t("settings.repositories.level.full")]);
});

test("a repository that is no longer on disk says so, and is still on the list", async () => {
  const { screen } = await repositoriesTab();
  const row = screen.tree
    .findAll("tr")
    .find((node) => node.textContent.includes("moved-away"));
  assert.ok(row, "a repository that left the disk was dropped from the list");
  assert.ok(row.textContent.includes(Str.t("settings.repositories.gone")));
});

/* The sessions that belong to no repository are a count, not a row with a dead control on
   it: there is nothing to enable for them. */
test("the sessions that belong to no repository are a line and not a row", async () => {
  const { screen } = await repositoriesTab();
  const text = visible(screen);
  assert.ok(
    text.includes(Str.t("settings.repositories.unassigned", Str.plural("unit.sessions", 115, "115"))),
    `the unassigned sessions are not reported: ${text}`
  );
  const rows = screen.tree.findAll(".repo-table").flatMap((table) => table.findAll("tr"));
  assert.equal(
    rows.some((row) => row.textContent.includes("no repository")),
    false,
    "the group with no path was drawn as a repository"
  );
});

test("changing a level asks the shell with the engine's own key, and redraws from the answer", async () => {
  const { screen, asked } = await repositoriesTab();
  const row = screen.tree
    .findAll("tr")
    .find((node) => node.textContent.includes("offeros"));
  const button = row
    .findAll("button")
    .find((node) => node.textContent === Str.t("settings.repositories.level.metadataOnly.short"));
  assert.ok(button, "the row offers no metadata-only");
  button.fire("click");
  await settled();

  // The key, never the path: `prudence init --enable` refuses a path.
  assert.deepEqual(asked.levels, [["root:2c3f8baf", "metadata-only"]]);

  // And the row moved to the recorded block, because that is what the engine answered.
  const blocks = screen.tree.findAll(".repo-table");
  assert.ok(blocks[0].textContent.includes("offeros"), "the answer was not drawn");
  const ticked = screen.tree
    .findAll("tr")
    .find((node) => node.textContent.includes("offeros"))
    .findAll("button")
    .filter((node) => node.getAttribute("aria-checked") === "true")
    .map((node) => node.textContent);
  assert.deepEqual(ticked, [Str.t("settings.repositories.level.metadataOnly.short")]);
});

test("every level the tab offers is one the shell will take", async () => {
  const { screen, asked } = await repositoriesTab();
  const row = screen.tree.findAll("tr").find((node) => node.textContent.includes("beatos"));
  const labels = row.findAll("button").map((node) => node.textContent);
  assert.deepEqual(labels, [
    Str.t("settings.choice.off"),
    Str.t("settings.repositories.level.metadataOnly.short"),
    Str.t("settings.repositories.level.full"),
  ]);
  for (const label of labels) {
    screen.tree
      .findAll("tr")
      .find((node) => node.textContent.includes("beatos"))
      .findAll("button")
      .find((node) => node.textContent === label)
      .fire("click");
    await settled();
  }
  assert.deepEqual(
    asked.levels.map(([, level]) => level),
    ["off", "metadata-only", "full"]
  );
});

test("an engine that cannot be asked for its repositories says so", async () => {
  const asked = fakePort();
  SETTINGS.port.repositories = () => Promise.reject(new Error("notFound"));
  const screen = screenFor({}, INFO, asked);
  open(screen, "repositories");
  await settled();
  assert.ok(visible(screen).includes(Str.t("settings.repositories.unread")));
});

test("a change the engine refuses leaves the tab saying so rather than showing the click", async () => {
  const { screen, asked } = await repositoriesTab({ levelRefuses: true });
  const row = screen.tree.findAll("tr").find((node) => node.textContent.includes("offeros"));
  row
    .findAll("button")
    .find((node) => node.textContent === Str.t("settings.repositories.level.full"))
    .fire("click");
  await settled();
  assert.deepEqual(asked.levels, [["root:2c3f8baf", "full"]]);
  assert.ok(visible(screen).includes(Str.t("settings.repositories.unread")));
});

/* --- the row's own layout ----------------------------------------------------------------
 *
 * The founder's screenshot of this tab in Chinese: the "Sessions found" header on two
 * lines with its number against the next column, both dates on two lines, and the segment
 * labels wrapped out of their own track. The cause was an automatic table, and the fix is
 * a declared one.
 *
 * **A DOM test cannot measure a pixel.** What it can do is guard the rule: that the
 * columns are declared, that the class which stops a cell wrapping is on every cell that
 * must not wrap, that the labels are short in both languages, and that a day is ten
 * characters rather than eleven that break anywhere.
 */

test("the columns are declared, and nothing on a row but the path may wrap", async () => {
  const { screen } = await repositoriesTab();
  const table = screen.tree.find(".repo-table");
  assert.deepEqual(
    table.findAll("col").map((node) => node.className),
    ["c-pick", "c-name", "c-sessions", "c-sources", "c-when", "c-when", "c-level"],
    "the table is sizing its own columns again"
  );

  const cells = rowFor(screen, "beatos").findAll("td");
  assert.equal(cells.length, 7);
  assert.deepEqual(
    cells.map((cell) => cell.className.split(/\s+/).includes("nowrap")),
    [false, false, true, true, true, true, true],
    "a figure, a day, a source or the control is allowed to wrap"
  );

  // The path is the one value that may lose characters, and it loses them from the front:
  // every path on the machine starts `/Users/someone`, and the end is what tells two
  // checkouts of one repository apart. All of it is on the title either way.
  const where = rowFor(screen, "beatos").find(".repo-path");
  assert.equal(where.textContent, "…/code/beatos");
  assert.equal(where.getAttribute("title"), "/Users/someone/code/beatos");

  // A path with nothing to drop is drawn whole.
  const { screen: shallow } = await repositoriesTab({
    scan: [{ ...SCAN[0], path: "/code/beatos" }],
  });
  const short = rowFor(shallow, "beatos").find(".repo-path");
  assert.equal(short.textContent, "/code/beatos");
});

test("every header and every segment label is short in both languages", async () => {
  const { screen } = await repositoriesTab();
  assert.deepEqual(
    screen.tree
      .find(".repo-table")
      .findAll("th")
      .map((node) => node.textContent),
    [
      "", // the select-all box, whose name is on its aria-label and not over the column
      Str.t("scope.project"),
      Str.t("settings.repositories.column.sessions"),
      Str.t("settings.repositories.column.sources"),
      Str.t("settings.repositories.column.first"),
      Str.t("settings.repositories.column.last"),
      Str.t("settings.repositories.column.level"),
    ]
  );

  for (const language of Str.LANGUAGES) {
    for (const key of [
      "settings.repositories.column.sessions",
      "settings.repositories.column.sources",
      "settings.repositories.column.first",
      "settings.repositories.column.last",
      "settings.repositories.column.level",
    ]) {
      const header = Str.tIn(language, key);
      assert.ok(header.length <= 10, `${key} in ${language} is a header of ${header.length}`);
    }
    for (const key of [
      "settings.choice.off",
      "settings.repositories.level.metadataOnly.short",
      "settings.repositories.level.full",
    ]) {
      const label = Str.tIn(language, key);
      assert.ok(label.length <= 6, `${key} in ${language} is a segment of ${label.length}`);
    }
  }

  // Shortened to fit a column, and still saying what it means to a pointer and a reader.
  const short = rowFor(screen, "beatos")
    .findAll("button")
    .find((node) => node.textContent === Str.t("settings.repositories.level.metadataOnly.short"));
  assert.equal(short.getAttribute("title"), Str.t("settings.repositories.level.metadataOnly"));
  assert.equal(short.getAttribute("aria-label"), Str.t("settings.repositories.level.metadataOnly"));
});

test("a day is the same ten characters in both languages", async () => {
  const { screen } = await repositoriesTab();
  const cells = rowFor(screen, "beatos").findAll("td");
  assert.equal(cells[4].textContent, "2026-05-14");
  assert.equal(cells[5].textContent, "2026-08-06");

  Str.setLang("zh-Hans");
  try {
    const { screen: chinese } = await repositoriesTab();
    const inChinese = rowFor(chinese, "beatos").findAll("td");
    assert.equal(inChinese[4].textContent, "2026-05-14", "the Chinese day is not the compact one");
  } finally {
    Str.setLang("en");
  }

  // A row with no history has no day, and says so rather than printing a broken one.
  const { screen: without } = await repositoriesTab({
    scan: SCAN.map((row) => ({ ...row, firstAt: null, lastAt: "" })),
  });
  const empty = rowFor(without, "beatos").findAll("td");
  assert.equal(empty[4].textContent, Str.t("common.dash"));
  assert.equal(empty[5].textContent, Str.t("common.dash"));
});

/* --- the sources column --------------------------------------------------------------
 *
 * Recording is per repository and covers every agent that worked in it. The scan does not
 * print the list yet, so the column draws the one source Prudence reads, through the one
 * function that will read the engine's field the day it exists.
 */

test("a repository names the agents whose sessions it holds", async () => {
  assert.deepEqual(sourcesOf({}), ["claude-code"], "a row with no field has no source");
  assert.deepEqual(sourcesOf({ sources: [] }), ["claude-code"]);
  assert.deepEqual(sourcesOf({ sources: ["claude-code", "codex"] }), ["claude-code", "codex"]);

  const { screen } = await repositoriesTab();
  assert.equal(rowFor(screen, "beatos").findAll("td")[3].textContent, "Claude Code");

  // The engine's own field, the day it is written, with no change to this page.
  const { screen: later } = await repositoriesTab({
    scan: SCAN.map((row) =>
      String(row.path).includes("beatos") ? { ...row, sources: ["claude-code", "codex"] } : { ...row }
    ),
  });
  const said = rowFor(later, "beatos").findAll("td")[3].textContent;
  assert.ok(said.includes("Claude Code") && said.includes("codex"), said);
});

/* --- many at once ------------------------------------------------------------------------
 *
 * The founder's fourth reading of the screenshot: with several repositories there is no
 * way to act on many at once. So: a box per row, a select-all per group, and a bar that
 * runs the same per-repository command the row's own control runs.
 */

test("nothing is offered until a row is ticked, and then the count is the app's own", async () => {
  const { screen } = await repositoriesTab();
  assert.equal(bar(screen), null, "the bar is on the screen with nothing selected");

  choose(screen, ["beatos", "offeros"]);
  assert.ok(bar(screen), "two rows are ticked and there is nothing to do with them");
  assert.ok(
    bar(screen).textContent.includes(Str.t("settings.repositories.batch.selected", "2")),
    bar(screen).textContent
  );

  // Untick both and it goes away again.
  choose(screen, ["beatos", "offeros"]);
  assert.equal(bar(screen), null, "the bar stayed after the last row was unticked");
});

test("select-all takes the group it is in and not the other one", async () => {
  const { screen } = await repositoriesTab();
  const blocks = screen.tree.findAll(".repo-table");
  // The head's own box, which is the first tick in the block.
  blocks[1].find(".tick").fire("change");
  assert.ok(
    bar(screen).textContent.includes(Str.t("settings.repositories.batch.selected", "2")),
    "the found-not-recorded group has two rows and select-all did not take both"
  );
  assert.ok(rowFor(screen, "offeros").find(".tick").checked);
  assert.equal(rowFor(screen, "beatos").find(".tick").checked, false, "the other group was taken");
});

test("a batch runs the command once per repository, in order, and re-reads the list once", async () => {
  const { screen, asked } = await repositoriesTab();
  const before = asked.scans;
  choose(screen, ["beatos", "averatec-career", "offeros"]);
  pressInBar(screen, Str.t("settings.repositories.level.metadataOnly.short"));
  await settled();

  assert.deepEqual(asked.levels, [
    ["root:df32e8a9", "metadata-only"],
    ["root:742d2192", "metadata-only"],
    ["root:2c3f8baf", "metadata-only"],
  ]);
  assert.equal(asked.scans - before, 1, "the list was read once per command");

  // Drawn from the engine's answer: all three are in the recorded block at that level.
  const recorded = screen.tree.findAll(".repo-table")[0];
  for (const name of ["beatos", "averatec-career", "offeros"]) {
    assert.ok(recorded.textContent.includes(name), `${name} is not in the recorded block`);
  }
  const ticked = rowFor(screen, "offeros")
    .findAll("button")
    .filter((node) => node.getAttribute("aria-checked") === "true")
    .map((node) => node.textContent);
  assert.deepEqual(ticked, [Str.t("settings.repositories.level.metadataOnly.short")]);
});

test("a batch says which one it is on while it runs", async () => {
  const { screen, asked } = await repositoriesTab();
  choose(screen, ["beatos", "averatec-career", "offeros"]);

  // A command that does not answer yet, which is the only way to look at a run mid-way.
  const real = SETTINGS.port.repositoryLevel;
  let release = null;
  SETTINGS.port.repositoryLevel = (key, level) => {
    asked.levels.push([key, level]);
    return new Promise((resolve) => {
      release = resolve;
    });
  };

  pressInBar(screen, Str.t("settings.repositories.level.full"));
  await settled();
  assert.ok(
    bar(screen).textContent.includes(Str.t("settings.repositories.batch.running", "1", "3")),
    bar(screen).textContent
  );
  // And nothing may be pressed twice while it runs.
  assert.ok(rowFor(screen, "beatos").findAll("button").every((node) => node.disabled));

  release();
  await settled();
  assert.ok(
    bar(screen).textContent.includes(Str.t("settings.repositories.batch.running", "2", "3")),
    bar(screen).textContent
  );

  SETTINGS.port.repositoryLevel = real;
  release();
  await settled();
  assert.equal(
    bar(screen).textContent.includes(Str.t("settings.repositories.batch.running", "3", "3")),
    false,
    "the run finished and the counter is still on the screen"
  );
});

test("a refusal stops the batch where it is, in the engine's own words", async () => {
  const { screen, asked } = await repositoriesTab({ refuseCall: 2 });
  const before = asked.scans;
  choose(screen, ["beatos", "averatec-career", "offeros"]);
  pressInBar(screen, Str.t("settings.repositories.level.full"));
  await settled();

  // Two commands, not three: the third was never sent.
  assert.deepEqual(asked.levels, [
    ["root:df32e8a9", "full"],
    ["root:742d2192", "full"],
  ]);
  assert.equal(asked.scans - before, 1, "the list was not re-read after the refusal");

  const said = bar(screen).textContent;
  assert.ok(
    said.includes(Str.t("settings.repositories.batch.failed", "averatec-career")),
    `the sentence does not say which repository failed: ${said}`
  );
  assert.ok(said.includes(REFUSAL), `the engine's own words are missing: ${said}`);

  // The one that changed before the refusal stays changed, which is what the sentence
  // promises, and it is the engine's answer that says so.
  const ticked = rowFor(screen, "beatos")
    .findAll("button")
    .filter((node) => node.getAttribute("aria-checked") === "true")
    .map((node) => node.textContent);
  assert.deepEqual(ticked, [Str.t("settings.repositories.level.full")]);
  // And the one after it did not move.
  assert.ok(
    screen.tree.findAll(".repo-table")[1].textContent.includes("offeros"),
    "a repository the batch never reached was drawn as changed"
  );
});

/* --- how often the engine is asked ------------------------------------------------------
 *
 * Two of the five panes ask the engine a question of their own, and all five are built
 * whichever tab is open. The screen is redrawn on every store change, and an ingest
 * announces itself to the store watcher about eight times as it works, so leaving the
 * window on Settings during one 230-second run cost fourteen extra processes, each
 * `init --scan` walking every repository on the machine while the engine was busy writing
 * the store. Measured on 2026-09-22 with `PRUDENCE_PRESS="Engine > Ingest now"`.
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

  assert.equal(asked.scans, 1, `the repository scan ran ${asked.scans} times for one store`);
  assert.equal(models, 1, `the model settings were read ${models} times for one store`);
});

/* An ingest or a review is a different store, and the next draw asks about it. That is what
   makes this a memo that follows the store rather than an answer frozen at launch. */
test("a store the engine has written since is asked about again", async () => {
  const asked = fakePort();
  const screen = screenFor({}, INFO, asked);
  await settled();
  assert.equal(asked.scans, 1);

  screen.state.data = { ...screen.state.data, status: { ...STATUS, last_ingest_at: "2099-01-01T00:00:00Z" } };
  screen.state.redraw();
  await settled();
  assert.equal(asked.scans, 2, "the scan did not follow the store");
});

/* A repository turned on writes `config.toml`, which no store stamp sees. The engine's own
   answer to that command is what the next draw has to serve, or the tab would go back to
   the list from before the change. */
test("a repository changed here is remembered without asking the engine again", async () => {
  const asked = fakePort();
  const screen = open(screenFor({}, INFO, asked), "repositories");
  await settled();
  const before = asked.scans;

  const off = rowFor(screen, "offeros")
    .findAll("button")
    .find((node) => node.textContent === Str.t("settings.repositories.level.full"));
  off.fire("click");
  await settled();

  screen.state.redraw();
  await settled();
  assert.equal(asked.scans, before, "the whole list was read again for a change the app made");
  assert.ok(
    rowFor(open(screen, "repositories"), "offeros")
      .findAll("button")
      .some((node) => node.getAttribute("aria-checked") === "true"),
    "the redraw went back to the list from before the change"
  );
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
  assert.ok(screen.tree.findAll(".tab").length === 5, "the screen did not draw");
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
