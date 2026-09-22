/* The Settings screen, and the reader under it.
 *
 * These guard requirements, not shapes. In order: what a session is (one row of
 * `app_session_list`, never a sum of the per-purpose column), that the groups add up to
 * the engine's own total, that a level this build has not heard of still draws, that the
 * screen is honest about being read-only rather than drawing a control, that the promise
 * about what is never recorded is on it in full including the one exception to it, and
 * that every figure on it is a column of `app_status` printed as it is.
 *
 * The screen is exercised against the small DOM in `test/dom.mjs`, for the reason given
 * there: `node --test` has no browser, and a shim of the handful of operations
 * `design/dom.js` uses makes "a screen returns one element and appends nothing to the
 * page" a checkable rule.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { installDom } from "./dom.mjs";

installDom();

/* Every command the engine registers, read from its source rather than listed here.
 *
 * Two assertions used to check that the screen quoted "prudence enable" and both passed
 * while that command did not exist: enabling is `prudence init --enable`. A test that asks
 * whether a screen mentions a command name cannot tell a real one from an invented one,
 * so this asks the engine.
 *
 * Read on first use rather than at module load, because `app` is defined below this.
 */
let engineCommands = null;

function engineRegisters(command) {
  if (engineCommands === null) {
    // Relative to this repository, not to one machine: the first version hardcoded an
    // absolute path under my home directory, which exists nowhere else.
    const source = readFileSync(join(app, "../../src/prudence/cli/__init__.py"), "utf8");
    engineCommands = new Set([...source.matchAll(/add_command\((\w+)/g)].map((m) => m[1]));
    assert.ok(engineCommands.size > 5, "the engine's command registry could not be read");
  }
  return engineCommands.has(command);
}

/** Every `prudence <word>` the screen quotes. */
function quotedCommands(text) {
  return [...text.matchAll(/`prudence ([a-z-]+)/g)].map((m) => m[1]);
}

const here = dirname(fileURLToPath(import.meta.url));
const app = join(here, "..");
const FIXTURE = join(app, "fixtures/store.db");

import * as Str from "../src/text/strings.js";
import { recorded } from "../src/store/settings.js";
// `any`, deliberately, as in the other screen tests: the tree this returns is the shim's
// and asking it for `find` is the whole point of the shim.
const { settings } = /** @type {any} */ (await import("../src/ui/settings.js"));

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
const SESSIONS = fixture("SELECT * FROM app_session_list;");

const INFO = {
  version: "0.5.0",
  database: "/tmp/a copy/prudence.db",
  supported_contract: [2, 3],
  language: null,
  platform: [
    ["platform", "macos"],
    ["NSAppKitVersionNumber", "2565.1"],
  ],
};

function screenFor(overrides = {}, info = INFO) {
  const data = { status: STATUS, sessions: SESSIONS, ...overrides };
  return settings({ data, info, project: null, range: "8w", week: null, onWeek() {}, redraw() {} });
}

/* The cards this file owns.
 *
 * `ui/engine-section.js` is another piece of work placed on this screen, and it draws
 * buttons and prints a version of its own. A test of this file must not assert on what
 * that module draws, or the two pieces cannot be finished independently: the read-only
 * assertion below would fail the moment the engine's actions arrive, which is exactly
 * when it should still pass.
 */
function ownCards(screen) {
  return screen.children.filter(
    (node) => !node.className.split(/\s+/).includes("engine-section")
  );
}

function ownText(screen) {
  return ownCards(screen)
    .map((node) => node.textContent)
    .join("");
}

/* --- the reader ---------------------------------------------------------------------- */

test("a session is one row of the session list, counted per project and level", () => {
  const { rows } = recorded({
    sessions: [
      { project: "alpha", capture_level: "full" },
      { project: "alpha", capture_level: "full" },
      { project: "alpha", capture_level: "metadata-only" },
      { project: "beta", capture_level: "full" },
    ],
  });
  assert.deepEqual(rows, [
    { project: "alpha", level: "full", sessions: 2 },
    { project: "alpha", level: "metadata-only", sessions: 1 },
    { project: "beta", level: "full", sessions: 1 },
  ]);
});

/* A repository whose level was changed has sessions at both, and folding them into one
   row would print a level the older half of the work was never recorded at. */
test("one project at two levels is two rows, not one", () => {
  const { rows } = recorded({
    sessions: [
      { project: "alpha", capture_level: "metadata-only" },
      { project: "alpha", capture_level: "full" },
    ],
  });
  assert.equal(rows.length, 2);
  assert.deepEqual(
    rows.map((row) => row.level),
    ["full", "metadata-only"]
  );
});

test("a session with no project or no level is counted, never dropped", () => {
  const { rows, sessions } = recorded({
    sessions: [{ project: null, capture_level: null }, { project: "alpha", capture_level: "full" }],
  });
  assert.equal(sessions, 2);
  assert.deepEqual(rows[0], { project: "", level: "", sessions: 1 });
});

test("no rows is no rows, and never a thrown error", () => {
  assert.deepEqual(recorded({ sessions: [] }), { rows: [], sessions: 0 });
  assert.deepEqual(recorded(/** @type {any} */ ({})), { rows: [], sessions: 0 });
});

/* The point of the reader. `app_usage_by_purpose_day.sessions` is per purpose per day, so
   summing it counts one session once for every day and purpose it touched; the groups
   here are rows of `app_session_list` and have to agree with the engine's own total. */
test("the groups add up to app_status.sessions on the engine's own store", () => {
  assert.ok(SESSIONS.length > 0, "no rows in app_session_list; regenerate the fixture");
  const { rows, sessions } = recorded({ sessions: SESSIONS });
  assert.equal(sessions, Number(STATUS.sessions));
  assert.equal(
    rows.reduce((total, row) => total + row.sessions, 0),
    Number(STATUS.sessions)
  );
  // And the projects the rows cover are the projects the engine counted.
  const projects = new Set(rows.map((row) => row.project));
  assert.equal(projects.size, Number(STATUS.projects));
});

/* --- the screen ---------------------------------------------------------------------- */

test("the screen returns one element and appends nothing to the page", () => {
  const screen = screenFor();
  assert.equal(screen.localName, "div");
  assert.equal(screen.className, "screen-body");
});

test("every figure on the screen is a column of app_status, printed as it is", () => {
  const text = ownText(screenFor());
  for (const column of [
    "sessions",
    "projects",
    "parser_version",
    "purpose_rule_version",
    "commit_fact_version",
    "attribution_fact_version",
    "outcome_fact_version",
    "observation_fact_version",
    "hook_fact_version",
    "app_contract_version",
    "engine_version",
  ]) {
    assert.ok(
      text.includes(String(STATUS[column])),
      `${column} (${STATUS[column]}) is not on the screen`
    );
  }
  // And the per-project counts are the reader's groups, not something else.
  for (const row of recorded({ sessions: SESSIONS }).rows) {
    assert.ok(text.includes(row.project), `project ${row.project} is missing`);
    assert.ok(text.includes(String(row.sessions)), `${row.project}'s count is missing`);
  }
});

test("the store's path is the one the shell opened, and says how it was found", () => {
  const text = ownText(screenFor());
  assert.ok(text.includes(INFO.database), "the path the shell reported is not on the screen");
  assert.ok(text.includes("PRUDENCE_DATA_DIR"), "the screen does not say how the path was found");
});

/* A version is an identifier, not a quantity. `1,248` would be a version number nobody
   has, and the grouping would only appear once a fact version reached four digits. */
test("a version number is printed ungrouped", () => {
  const text = ownText(screenFor({ status: { ...STATUS, parser_version: 1234 } }));
  assert.ok(text.includes("1234"), "the version is missing");
  assert.equal(text.includes("1,234"), false, "the version was grouped like a quantity");
});

/* Contract 3 added no column to `app_status`, but an engine older than one of these facts
   writes no value for it, and a dash would say "this ran and produced nothing". */
test("a step with no version is left out rather than shown as a dash", () => {
  const without = { ...STATUS, hook_fact_version: null };
  const text = ownText(screenFor({ status: without }));
  assert.equal(text.includes(Str.t("settings.version.hook")), false, "the empty step is drawn");
  assert.ok(text.includes(Str.t("settings.version.parser")), "the steps that ran are missing");
});

/* The whole point of the screen being read-only. The Swift app drew a switch here; this
   build has no command that would persist one, so it says where the change is made. */
test("the screen draws no control and says where a setting is changed instead", () => {
  const screen = screenFor();
  for (const tag of ["input", "select", "button"]) {
    const drawn = ownCards(screen).flatMap((card) => card.findAll(tag));
    assert.deepEqual(
      drawn.map((node) => node.localName),
      [],
      `this screen draws a ${tag}, which nothing in this build can act on`
    );
  }
  const text = ownText(screen);
  const quoted = quotedCommands(text);
  assert.ok(quoted.length > 0, "the screen names no command at all");
  for (const command of quoted) {
    assert.ok(
      engineRegisters(command),
      `the screen tells the reader to run \`prudence ${command}\`, which the engine does not register`
    );
  }
  assert.ok(text.includes("prudence init --enable"), "the screen does not say how a level is set");
  assert.ok(text.includes("prudence forget"), "the screen does not say how a record is removed");
});

test("the capture level a store holds is named, and an unknown one falls back to the engine's token", () => {
  const known = ownText(
    screenFor({
      sessions: [
        { project: "alpha", capture_level: "full" },
        { project: "beta", capture_level: "metadata-only" },
      ],
    })
  );
  assert.ok(known.includes(Str.t("settings.level.full")));
  assert.ok(known.includes(Str.t("settings.level.metadataOnly")));

  const future = ownText(
    screenFor({ sessions: [{ project: "alpha", capture_level: "shape-only" }] })
  );
  assert.ok(future.includes("shape-only"), "an unrecognised level is not printed at all");
  assert.equal(future.includes("settings.level."), false, "a missing key leaked onto the screen");
});

test("a store with nothing recorded says nothing is recorded, and how to start", () => {
  const text = ownText(screenFor({ sessions: [] }));
  assert.ok(text.includes(Str.t("settings.recorded.empty.title")));
  assert.ok(text.includes("prudence init"), "the empty state does not say how to enable one");
});

/* The promise is the reason this screen exists at all, and the exception to it is part of
   the promise: `prudence review --explain` does send a review's figures to a model. A
   screen that printed "nothing is uploaded" and stopped would be wrong. */
test("the record's promise is on the screen, exception included", () => {
  const text = ownText(screenFor());
  for (const key of [
    "settings.never.archive",
    "settings.never.derived",
    "settings.never.metadataOnly",
    "settings.never.upload",
    "settings.never.model",
    "settings.never.employer",
  ]) {
    assert.ok(text.includes(Str.t(key)), `${key} is not on the screen`);
  }
});

test("the language in force is shown with where it came from", () => {
  const followed = ownText(screenFor({}, { ...INFO, language: null }));
  assert.ok(followed.includes("English"), "the language in force is not named");
  assert.ok(followed.includes(Str.t("settings.language.fromSystem")));

  const forced = ownText(screenFor({}, { ...INFO, language: "en" }));
  assert.ok(forced.includes("PRUDENCE_FORCE_LANGUAGE"), "a forced language does not say so");
});

test("the about block names this build, the engine that wrote the store, and the project", () => {
  const text = ownText(screenFor());
  assert.ok(text.includes(INFO.version), "the app's own version is missing");
  assert.ok(text.includes(String(STATUS.engine_version)), "the engine's version is missing");
  assert.ok(text.includes("github.com/averatec0773/prudence"), "the project is missing");
  assert.ok(text.includes("NSAppKitVersionNumber"), "the platform the shell described is missing");
});

/* A store the shell could not read at all still draws the screen: the promise, the
   paths and the about block do not depend on a row, and this is the screen a reader
   opens **because** something is wrong. */
test("a store with no status row still draws, and says the figures are not read", () => {
  const screen = screenFor({ status: null, sessions: [] });
  const text = ownText(screen);
  assert.ok(text.includes(Str.t("settings.store.unread")), "nothing says the store was not read");
  assert.ok(text.includes(INFO.database), "the path is missing");
  assert.ok(text.includes(Str.t("settings.never.upload")), "the promise is missing");
  assert.equal(text.includes("undefined"), false, text);
  assert.equal(text.includes("null"), false, text);
});

test("no shell info at all draws rather than throwing", () => {
  const text = ownText(screenFor({}, undefined));
  assert.ok(text.includes(Str.t("settings.recorded")), "the screen did not draw");
  assert.equal(text.includes("undefined"), false, text);
});

test("the method is stated on every card that prints a figure", () => {
  const screen = screenFor();
  const methods = ownCards(screen)
    .flatMap((card) => card.findAll(".method"))
    .map((node) => node.textContent);
  assert.ok(methods.length >= 3, `only ${methods.length} cards state their method`);
  // Principle 3: the view and column names are behind the disclosure, and they name the
  // views a reader would go and check.
  assert.ok(methods.some((text) => text.includes("app_session_list")));
  assert.ok(methods.some((text) => text.includes("app_status")));
});

test("the whole screen draws in Chinese with no English prose left in it", () => {
  Str.setLang("zh-Hans");
  const text = ownText(screenFor());
  assert.ok(text.includes("记录了什么"), "the first card's title is not in Chinese");
  assert.ok(text.includes("永远不会记录的东西"), "the promise is not in Chinese");
  for (const key of ["settings.recorded.note", "settings.never.upload", "settings.store.note"]) {
    assert.equal(
      text.includes(Str.tIn("en", key)),
      false,
      `the English of ${key} is still on the screen`
    );
  }
  // The technical tokens stay as they are: a command, a variable and a path are not
  // translated, and a reader has to be able to type them.
  assert.ok(text.includes("prudence init --enable"), "the command was translated");
  for (const command of quotedCommands(text)) {
    assert.ok(engineRegisters(command), `the Chinese quotes a command that does not exist: ${command}`);
  }
  assert.ok(text.includes("PRUDENCE_DATA_DIR"), "the variable was translated");
  assert.ok(text.includes(INFO.database), "the path was translated");
  Str.setLang("en");
});
