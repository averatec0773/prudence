/* The Repositories screen, and the reader behind its two figures.
 *
 * The screen answers the founder's question: "why are only three repositories recorded?"
 * So what is asserted is that the answer is on it (recording is opt-in, and the two groups
 * are told apart), that every figure is the engine's own (the scan's fields, and the two
 * sums of view columns beside them), that a recorded row sets the window's one project
 * filter, and that changing a level goes through the shell and redraws from **the
 * engine's answer** rather than from the click.
 *
 * Most of these moved here from `test/settings.test.mjs` with the screen itself, which was
 * a tab of Settings until 2026-09-23.
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
// `any`, deliberately, as in the other screen tests: the tree this returns is the shim's.
const { BATCH, REPOSITORIES, repositories, sourcesOf } = /** @type {any} */ (
  await import("../src/ui/repositories.js")
);
const { REPOSITORY_SCAN } = /** @type {any} */ (await import("../src/store/asked.js"));
const { aliveOf, projectOf, scanCounts, tokensOf } = await import("../src/store/repositories.js");
const { readPayload } = await import("../src/store/payload.js");

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

const settled = () => new Promise(setImmediate);

/** What the engine says when it will not enable a repository, in its own words. */
const REFUSAL = "prudence init: no repository called root:2c3f8baf in the scan";

/**
 * The scan `prudence init --scan --json` prints, trimmed to the shapes the screen has to
 * draw: enabled at a level, enabled at the other, never enabled, gone from disk, and the
 * group of sessions that belong to no repository.
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

/**
 * What the store holds about the two recorded repositories: beatos has tokens in three
 * buckets and two measured weeks; averatec-career has tokens and no week whose thirty days
 * are up. offeros is not recorded and has neither.
 */
const DATA = readPayload({
  status: { last_ingest_at: "2026-09-22T10:00:00Z" },
  usage: {
    columns: ["day", "repo_key", "project", "bucket", "total_tokens"],
    rows: [
      ["2026-09-01", "root:df32e8a9", "beatos", "change", 600],
      ["2026-09-02", "root:df32e8a9", "beatos", "run", 300],
      ["2026-09-02", "root:df32e8a9", "beatos", "read", 100],
      ["2026-09-03", "root:742d2192", "averatec-career", "talk", 200],
    ],
  },
  outcomes: {
    columns: ["repo_key", "project", "week_start", "measured_30d", "alive_30d"],
    rows: [
      ["root:df32e8a9", "beatos", "2026-08-03", 40, 30],
      ["root:df32e8a9", "beatos", "2026-08-10", 60, 50],
      ["root:742d2192", "averatec-career", "2026-09-14", 0, 0],
    ],
  },
  projects: [
    { key: "root:742d2192", name: "averatec-career" },
    { key: "root:df32e8a9", name: "beatos" },
  ],
});

/**
 * A shell that answers whatever the test says, and records what it was asked. The engine's
 * answer, not the click's: a level change moves the row itself and hands the whole scan
 * back, which is what the real command does.
 */
function fakePort(overrides = {}) {
  // The scan is remembered against the store it was taken for (`store/asked.js`), and
  // every test draws the same store.
  REPOSITORY_SCAN.forget();
  // A batch outlives the screen it started on (`BATCH`), which means it can outlive one
  // test too, unless it is put back here.
  BATCH.running = false;
  BATCH.keys = [];
  BATCH.index = 0;
  BATCH.name = null;
  BATCH.scan = null;
  BATCH.failure = null;
  BATCH.onChange = null;
  const asked = { levels: [], scans: 0, filters: [] };
  let scan = overrides.scan ?? SCAN.map((row) => ({ ...row }));
  REPOSITORIES.port = {
    scan: () => {
      asked.scans += 1;
      if (overrides.scanRefuses) return Promise.reject(new Error("notFound"));
      return Promise.resolve(scan);
    },
    level: (key, level) => {
      asked.levels.push([key, level]);
      if (overrides.levelRefuses) return Promise.reject(new Error("failed"));
      // `refuseCall: 2` refuses the second command of a batch and no other.
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
  };
  return asked;
}

/** Draw the screen the way `window.js` does, with the project filter carried in `state`
 *  and `onProject` redrawing in place. */
async function screenFor(overrides = {}, { project = null, data = DATA } = {}) {
  const asked = fakePort(overrides);
  let tree = null;
  const state = {
    data,
    info: null,
    project,
    range: "30d",
    bucket: null,
    ingesting: false,
    onBucket() {},
    onProject(next) {
      asked.filters.push(next);
      state.project = next;
      tree = repositories(state);
    },
    redraw() {
      tree = repositories(state);
    },
  };
  tree = repositories(state);
  await settled();
  return {
    get tree() {
      return tree;
    },
    state,
    asked,
  };
}

/** One row, found again from the tree each time: every press redraws the list. */
function rowFor(screen, text) {
  return screen.tree.findAll("tr").find((node) => node.textContent.includes(text));
}

/** Tick the box on each of these rows, one press at a time, as a reader would. */
function choose(screen, names) {
  for (const name of names) rowFor(screen, name).find(".tick").fire("change");
}

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

function ticked(row) {
  return row
    .findAll("button")
    .filter((node) => node.getAttribute("aria-checked") === "true")
    .map((node) => node.textContent);
}

/* --- the reader ------------------------------------------------------------------------ */

/* The two figures are sums of view columns over the repository's rows, and the fixture's
   own SQL says what those sums are. This is the rule the app rests on, asserted where it
   would first be broken. */
test("a repository's tokens and survival are the views' own sums, over all time", () => {
  const data = readPayload({
    usage: {
      columns: ["day", "repo_key", "project", "bucket", "total_tokens"],
      rows: fixture("SELECT day, repo_key, project, bucket, total_tokens FROM app_usage_by_bucket_day").map(Object.values),
    },
    outcomes: {
      columns: ["repo_key", "project", "week_start", "measured_30d", "alive_30d"],
      rows: fixture("SELECT repo_key, project, week_start, measured_30d, alive_30d FROM app_outcomes_by_week").map(Object.values),
    },
  });
  for (const { repo_key: key } of fixture("SELECT DISTINCT repo_key FROM app_usage_by_bucket_day")) {
    const sums = fixture(
      `SELECT bucket, SUM(total_tokens) AS tokens FROM app_usage_by_bucket_day WHERE repo_key = '${key}' GROUP BY bucket`
    );
    const tokens = tokensOf(data, key);
    for (const { bucket, tokens: expected } of sums) {
      assert.equal(tokens.byBucket[bucket], expected, `${key} ${bucket}`);
    }
    assert.equal(tokens.total, sums.reduce((sum, row) => sum + row.tokens, 0));

    const [outcome] = fixture(
      `SELECT SUM(alive_30d) AS alive, SUM(measured_30d) AS measured FROM app_outcomes_by_week WHERE repo_key = '${key}'`
    );
    const alive = aliveOf(data, key);
    assert.equal(alive?.alive, outcome.alive);
    assert.equal(alive?.measured, outcome.measured);
    assert.equal(alive?.share, outcome.alive / outcome.measured);
  }
});

test("a repository with nothing measured has no share, not a zero", () => {
  assert.equal(aliveOf(DATA, "root:742d2192"), null, "no week whose thirty days are up");
  assert.equal(aliveOf(DATA, "root:2c3f8baf"), null, "not recorded");
  assert.equal(tokensOf(DATA, "root:2c3f8baf").total, 0);
  assert.deepEqual(tokensOf(DATA, "root:2c3f8baf").shares, []);
});

test("the name a row filters by is the one the picker offers, and the counts are the scan's", () => {
  assert.equal(projectOf(DATA, "root:df32e8a9"), "beatos");
  assert.equal(projectOf(DATA, "root:2c3f8baf"), null);
  assert.deepEqual(scanCounts(SCAN), { recorded: 2, found: 2 });
});

/* --- the screen ------------------------------------------------------------------------ */

test("the screen returns one element, says what it counted, and that recording is opt-in", async () => {
  const screen = await screenFor();
  assert.ok(screen.tree.className.split(/\s+/).includes("screen-body"));
  const text = screen.tree.textContent;
  assert.ok(text.includes(Str.t("repositories.counts", "2", "2")), text);
  assert.ok(text.includes(Str.t("repositories.note")), "the opt-in sentence is missing");
  assert.ok(text.includes(Str.t("repositories.recorded")), "no recorded group");
  assert.ok(text.includes(Str.t("repositories.found")), "no found-not-recorded group");
  const groups = screen.tree.findAll(".repo-table");
  assert.equal(groups.length, 2, "the list was not split");
  assert.ok(groups[0].textContent.includes("beatos"));
  assert.ok(groups[1].textContent.includes("offeros"));
  assert.equal(groups[0].textContent.includes("offeros"), false, "a row is in the wrong group");
});

test("every figure on a row is the engine's own", async () => {
  const screen = await screenFor();
  const row = rowFor(screen, "beatos");
  const cells = row.findAll("td");
  assert.equal(row.find(".repo-path").getAttribute("title"), "/Users/someone/code/beatos");
  assert.equal(cells[2].textContent, "65-", "a scan without a source is not labelled as Claude Code");
  assert.equal(cells[3].textContent, "2026-05-142026-08-06", "the first and the last day");
  assert.deepEqual(ticked(row), [Str.t("repositories.level.full")]);
});

/* Four buckets in the engine's fixed order, their shares on the pointer, and nothing at
   all for a repository the store has no tokens from: a dash, not an empty track that
   would read as a measured zero. */
test("tokens are one bar in the fixed bucket order, and a dash where there are none", async () => {
  const screen = await screenFor();
  const cell = rowFor(screen, "beatos").findAll("td")[4];
  const figure = cell.find("figure");
  assert.ok(figure, "no bar for a repository with tokens");
  assert.equal(
    figure.title,
    Str.t("repositories.tokens.caption", Str.t("unit.tokens", "1.0k"), "change 60%, run 30%, read 10%")
  );
  assert.deepEqual(
    figure.findAll("rect").map((rect) => rect.getAttribute("fill")),
    ["var(--b-change)", "var(--b-run)", "var(--b-read)"]
  );
  assert.equal(rowFor(screen, "offeros").findAll("td")[4].textContent, Str.t("common.dash"));
});

test("alive at thirty days is a share over the lines it is measured over, or a dash", async () => {
  const screen = await screenFor();
  assert.equal(
    rowFor(screen, "beatos").findAll("td")[5].textContent,
    `80%${Str.t("repositories.alive.over", Str.plural("unit.lines", 100, "100"))}`
  );
  assert.equal(rowFor(screen, "averatec-career").findAll("td")[5].textContent, Str.t("common.dash"));
  assert.equal(rowFor(screen, "offeros").findAll("td")[5].textContent, Str.t("common.dash"));
});

test("a repository that is no longer on disk says so, and is still on the list", async () => {
  const screen = await screenFor();
  const row = rowFor(screen, "moved-away");
  assert.ok(row, "a repository that left the disk was dropped from the list");
  assert.ok(row.textContent.includes(Str.t("repositories.gone")));
});

test("the sessions that belong to no repository are a line and not a row", async () => {
  const screen = await screenFor();
  assert.ok(
    screen.tree.textContent.includes(
      Str.t("repositories.unassigned", Str.plural("unit.sessions", 115, "115"))
    )
  );
  const rows = screen.tree.findAll(".repo-table").flatMap((table) => table.findAll("tr"));
  assert.equal(rows.some((row) => row.textContent.includes("no repository")), false);
});

/* --- the filter ---------------------------------------------------------------------------
 *
 * A recorded repository the store has sessions from is what the project picker offers, so
 * its row is the picker here. The window's own `onProject` is what every screen reads.
 */

test("clicking a recorded row filters every screen to it, and clicking again clears it", async () => {
  const screen = await screenFor();
  rowFor(screen, "beatos").fire("click");
  // The window redraws the screen with the new filter, and the list is filled from the
  // engine's remembered answer a turn later.
  await settled();
  assert.deepEqual(screen.asked.filters, ["beatos"]);

  const chosen = rowFor(screen, "beatos");
  assert.ok(chosen.className.split(/\s+/).includes("is-filtered"), "the chosen row is not marked");
  assert.equal(chosen.find(".repo-name").getAttribute("aria-pressed"), "true");
  assert.ok(
    screen.tree.textContent.includes(Str.t("repositories.filtered", "beatos")),
    "nothing says what every screen is showing"
  );
  assert.equal(
    rowFor(screen, "averatec-career").className.split(/\s+/).includes("is-filtered"),
    false
  );

  // The name is a button, so the keyboard reaches the same thing.
  rowFor(screen, "beatos").find(".repo-name").fire("click");
  await settled();
  assert.deepEqual(screen.asked.filters, ["beatos", null]);
  assert.equal(rowFor(screen, "beatos").className.split(/\s+/).includes("is-filtered"), false);
});

test("a row that is not recorded is not a filter, and the line above clears one", async () => {
  const screen = await screenFor({}, { project: "averatec-career" });
  const offeros = rowFor(screen, "offeros");
  assert.equal(offeros.className.split(/\s+/).includes("is-pickable"), false);
  assert.equal(offeros.find(".repo-name").localName, "div", "an unrecorded name is a button");
  offeros.fire("click");
  assert.deepEqual(screen.asked.filters, [], "a row the picker does not offer set the filter");

  const clear = screen.tree
    .find(".filter-note")
    .findAll("button")
    .find((node) => node.textContent === Str.t("repositories.filter.clear"));
  clear.fire("click");
  assert.deepEqual(screen.asked.filters, [null]);
});

/* --- changing a level ------------------------------------------------------------------ */

test("changing a level asks the shell with the engine's own key, and redraws from the answer", async () => {
  const screen = await screenFor();
  rowFor(screen, "offeros")
    .findAll("button")
    .find((node) => node.textContent === Str.t("repositories.level.metadataOnly.short"))
    .fire("click");
  await settled();
  // The key, never the path: `prudence init --enable` refuses a path.
  assert.deepEqual(screen.asked.levels, [["root:2c3f8baf", "metadata-only"]]);
  assert.ok(screen.tree.findAll(".repo-table")[0].textContent.includes("offeros"));
  assert.deepEqual(ticked(rowFor(screen, "offeros")), [Str.t("repositories.level.metadataOnly.short")]);
  // And a click on a control inside a row is the control's, never the row's filter.
  assert.deepEqual(screen.asked.filters, []);
});

test("every level the screen offers is one the shell will take", async () => {
  const screen = await screenFor();
  const labels = rowFor(screen, "beatos").findAll("button").filter((node) => node.getAttribute("role") === "radio").map((node) => node.textContent);
  assert.deepEqual(labels, [
    Str.t("settings.choice.off"),
    Str.t("repositories.level.metadataOnly.short"),
    Str.t("repositories.level.full"),
  ]);
  for (const label of labels) {
    rowFor(screen, "beatos").findAll("button").find((node) => node.textContent === label).fire("click");
    await settled();
  }
  assert.deepEqual(screen.asked.levels.map(([, level]) => level), ["off", "metadata-only", "full"]);
});

test("an engine that cannot be asked for its repositories says so", async () => {
  const screen = await screenFor({ scanRefuses: true });
  assert.ok(screen.tree.textContent.includes(Str.t("repositories.unread")));
});

test("a change the engine refuses leaves the screen saying so rather than showing the click", async () => {
  const screen = await screenFor({ levelRefuses: true });
  rowFor(screen, "offeros")
    .findAll("button")
    .find((node) => node.textContent === Str.t("repositories.level.full"))
    .fire("click");
  await settled();
  assert.deepEqual(screen.asked.levels, [["root:2c3f8baf", "full"]]);
  assert.ok(screen.tree.textContent.includes(Str.t("repositories.unread")));
});

/* --- the row's own layout ----------------------------------------------------------------
 *
 * The founder's screenshot of this list in Chinese: the header on two lines with its
 * number against the next column, both dates on two lines, and the segment labels wrapped
 * out of their own track. The cause was an automatic table; the fix is a declared one. A
 * DOM test cannot measure a pixel, so what it guards is the rule.
 */

test("the columns are declared, and nothing on a row but the path may wrap", async () => {
  const screen = await screenFor();
  assert.deepEqual(
    screen.tree.find(".repo-table").findAll("col").map((node) => node.className),
    ["c-pick", "c-name", "c-sessions", "c-seen", "c-tokens", "c-alive", "c-level"],
    "the table is sizing its own columns again"
  );
  const cells = rowFor(screen, "beatos").findAll("td");
  assert.equal(cells.length, 7);
  assert.deepEqual(
    cells.map((cell) => cell.className.split(/\s+/).includes("nowrap")),
    [false, false, true, true, true, true, true],
    "a figure, a day, a bar or the control is allowed to wrap"
  );

  const where = rowFor(screen, "beatos").find(".repo-path");
  assert.equal(where.textContent, "…/code/beatos");
  assert.equal(where.getAttribute("title"), "/Users/someone/code/beatos");

  const shallow = await screenFor({ scan: [{ ...SCAN[0], path: "/code/beatos" }] });
  assert.equal(rowFor(shallow, "beatos").find(".repo-path").textContent, "/code/beatos");
});

test("every header and every segment label is short in both languages", async () => {
  const screen = await screenFor();
  assert.deepEqual(
    screen.tree.find(".repo-table").findAll("th").map((node) => node.textContent),
    [
      "",
      Str.t("scope.project"),
      Str.t("repositories.column.sessions"),
      Str.t("repositories.column.seen"),
      Str.t("repositories.column.tokens"),
      Str.t("repositories.column.alive"),
      Str.t("repositories.column.level"),
    ]
  );
  for (const language of Str.LANGUAGES) {
    for (const key of [
      "repositories.column.sessions",
      "repositories.column.seen",
      "repositories.column.tokens",
      "repositories.column.alive",
      "repositories.column.level",
    ]) {
      const header = Str.tIn(language, key);
      assert.ok(header.length <= 10, `${key} in ${language} is a header of ${header.length}`);
    }
    for (const key of ["settings.choice.off", "repositories.level.metadataOnly.short", "repositories.level.full"]) {
      const label = Str.tIn(language, key);
      assert.ok(label.length <= 6, `${key} in ${language} is a segment of ${label.length}`);
    }
  }
  const short = rowFor(screen, "beatos")
    .findAll("button")
    .find((node) => node.textContent === Str.t("repositories.level.metadataOnly.short"));
  assert.equal(short.getAttribute("title"), Str.t("repositories.level.metadataOnly"));
  assert.equal(short.getAttribute("aria-label"), Str.t("repositories.level.metadataOnly"));
});

test("a day is the same ten characters in both languages, and a dash where there is none", async () => {
  Str.setLang("zh-Hans");
  try {
    const chinese = await screenFor();
    const seen = rowFor(chinese, "beatos").findAll("td")[3];
    assert.deepEqual(seen.children.map((node) => node.textContent), ["2026-05-14", "2026-08-06"]);
  } finally {
    Str.setLang("en");
  }
  const without = await screenFor({ scan: SCAN.map((row) => ({ ...row, firstAt: null, lastAt: "" })) });
  const seen = rowFor(without, "beatos").findAll("td")[3];
  assert.deepEqual(seen.children.map((node) => node.textContent), [Str.t("common.dash"), Str.t("common.dash")]);
});

test("a repository names the agents whose sessions it holds", async () => {
  assert.deepEqual(sourcesOf({}), []);
  assert.deepEqual(sourcesOf({ sources: [] }), []);
  assert.deepEqual(sourcesOf({ sources: ["claude_code", "codex"] }), ["claude_code", "codex"]);
  const later = await screenFor({
    scan: SCAN.map((row) =>
      String(row.path).includes("beatos") ? { ...row, sources: ["claude_code", "codex"] } : { ...row }
    ),
  });
  const said = rowFor(later, "beatos").findAll("td")[2].textContent;
  assert.ok(said.includes("Claude Code") && said.includes("Codex"), said);
});

/* The level control's three segments are equal and the column fits the widest label. */
test("the level control's three segments are declared equal, and the column fits the widest label", () => {
  const css = readFileSync(join(app, "src/ui/repositories.css"), "utf8");
  const at = css.indexOf(".repo-table td .segmented button {");
  assert.notEqual(at, -1, "no rule for the level control's own buttons");
  const body = css.slice(css.indexOf("{", at) + 1, css.indexOf("}", at));
  assert.match(body, /flex:\s*1 1 0/);
  assert.match(body, /min-width:\s*0/);
  assert.match(body, /white-space:\s*nowrap/);
  assert.match(body, /text-align:\s*center/);

  const level = css.indexOf(".repo-table .c-level {");
  const width = Number((css.slice(level, css.indexOf("}", level)).match(/width:\s*(\d+)px/) ?? [])[1]);
  assert.ok(width >= 176, `the level column is ${width}px, too narrow for 元数据 x 3`);
});

/* --- many at once ------------------------------------------------------------------------ */

test("nothing is offered until a row is ticked, and then the count is the app's own", async () => {
  const screen = await screenFor();
  assert.equal(bar(screen), null);
  choose(screen, ["beatos", "offeros"]);
  assert.ok(bar(screen).textContent.includes(Str.t("repositories.batch.selected", "2")));
  choose(screen, ["beatos", "offeros"]);
  assert.equal(bar(screen), null);
});

test("select-all takes the group it is in and not the other one", async () => {
  const screen = await screenFor();
  screen.tree.findAll(".repo-table")[1].find(".tick").fire("change");
  assert.ok(bar(screen).textContent.includes(Str.t("repositories.batch.selected", "2")));
  assert.ok(rowFor(screen, "offeros").find(".tick").checked);
  assert.equal(rowFor(screen, "beatos").find(".tick").checked, false);
});

test("a batch runs the command once per repository, in order, and asks the engine no more", async () => {
  const screen = await screenFor();
  const before = screen.asked.scans;
  choose(screen, ["beatos", "averatec-career", "offeros"]);
  pressInBar(screen, Str.t("repositories.level.metadataOnly.short"));
  await settled();
  assert.deepEqual(screen.asked.levels, [
    ["root:df32e8a9", "metadata-only"],
    ["root:742d2192", "metadata-only"],
    ["root:2c3f8baf", "metadata-only"],
  ]);
  assert.equal(screen.asked.scans - before, 0, "the batch read the list on top of its own answers");
  const recorded = screen.tree.findAll(".repo-table")[0];
  for (const name of ["beatos", "averatec-career", "offeros"]) {
    assert.ok(recorded.textContent.includes(name), `${name} is not in the recorded group`);
  }
});

/** A command that does not answer yet, which is the only way to look at a run mid-way. */
function heldOpenLevel(asked, initial) {
  let working = initial.map((row) => ({ ...row }));
  const releases = [];
  REPOSITORIES.port.level = (key, level) => {
    asked.levels.push([key, level]);
    return new Promise((resolve) => {
      releases.push(() => {
        working = working.map((row) =>
          row.repoKey === key
            ? { ...row, enabled: level !== "off", level: level === "off" ? null : level }
            : row
        );
        resolve(working);
      });
    });
  };
  return releases;
}

test("a batch's bar names the repository being changed, in the engine's own count, in both languages", async () => {
  for (const language of Str.LANGUAGES) {
    Str.setLang(language);
    try {
      const screen = await screenFor();
      choose(screen, ["beatos", "averatec-career", "offeros"]);
      const releases = heldOpenLevel(screen.asked, SCAN);
      pressInBar(screen, Str.t("repositories.level.full"));
      await settled();

      const atOne = bar(screen);
      assert.ok(atOne.textContent.includes("beatos"), atOne.textContent);
      assert.ok(
        atOne.textContent.includes(Str.t("engine.progress.count", "1", "3", Str.t("engine.unit.repositories")))
      );
      assert.ok(Math.abs(parseFloat(atOne.find(".progress-fill").style.width) - 100 / 3) < 0.01);
      // No level may be pressed twice while it runs. The name is not a level: filtering the
      // window to a repository changes nothing the batch is changing.
      const levels = rowFor(screen, "beatos").findAll("button").filter((node) => node.getAttribute("role") === "radio");
      assert.equal(levels.length, 3);
      assert.ok(levels.every((node) => node.disabled));

      releases[0]();
      await settled();
      assert.ok(bar(screen).textContent.includes("averatec-career"));
      releases[1]();
      await settled();
      releases[2]();
      await settled();
      assert.equal(bar(screen).find(".progress-fill"), null, "a fill bar is still on the screen");
    } finally {
      Str.setLang("en");
    }
  }
});

test("a row shows its own new level as soon as its own change lands", async () => {
  const screen = await screenFor();
  choose(screen, ["beatos", "averatec-career"]);
  const releases = heldOpenLevel(screen.asked, SCAN);
  pressInBar(screen, Str.t("settings.choice.off"));
  await settled();
  releases[0]();
  await settled();
  assert.deepEqual(ticked(rowFor(screen, "beatos")), [Str.t("settings.choice.off")]);
  assert.deepEqual(ticked(rowFor(screen, "averatec-career")), [Str.t("repositories.level.metadataOnly.short")]);
  releases[1]();
  await settled();
  assert.deepEqual(ticked(rowFor(screen, "averatec-career")), [Str.t("settings.choice.off")]);
});

test("a second batch cannot start while one runs", async () => {
  const screen = await screenFor();
  choose(screen, ["beatos", "averatec-career"]);
  const releases = heldOpenLevel(screen.asked, SCAN);
  pressInBar(screen, Str.t("repositories.level.full"));
  await settled();
  // The shim fires a click on a disabled button the way a real browser never would, so
  // this presses `startBatch`'s own guard rather than the DOM's.
  pressInBar(screen, Str.t("settings.choice.off"));
  await settled();
  assert.equal(screen.asked.levels.length, 1, "a second batch started while the first was running");
  releases[0]();
  await settled();
  releases[1]();
  await settled();
});

test("the batch bar's progress row is reserved: present but empty until a batch runs", async () => {
  const screen = await screenFor();
  choose(screen, ["beatos"]);
  const slot = bar(screen).find(".repo-batch-progress");
  assert.ok(slot);
  assert.equal(slot.children.length, 0);
});

test("a batch keeps running when the screen it started on is torn down, and the screen it comes back to shows what it did", async () => {
  const screen = await screenFor();
  choose(screen, ["beatos", "averatec-career"]);
  const releases = heldOpenLevel(screen.asked, SCAN);
  pressInBar(screen, Str.t("settings.choice.off"));
  await settled();

  // A brand new tree, the way `window.js` rebuilds a screen on a switch.
  const torn = repositories(screen.state);
  await settled();

  releases[0]();
  await settled();
  assert.equal(screen.asked.levels.length, 2, "the batch stopped when its screen was torn down");
  const back = torn.find(".repo-actions");
  assert.ok(back, "the screen that came back shows no bar for a batch that is running");
  assert.ok(back.textContent.includes("averatec-career"));

  releases[1]();
  await settled();
  assert.equal(torn.find(".repo-actions"), null);
  const career = torn.findAll("tr").find((node) => node.textContent.includes("averatec-career"));
  assert.deepEqual(ticked(career), [Str.t("settings.choice.off")]);
});

test("a refusal stops the batch where it is, in the engine's own words", async () => {
  const screen = await screenFor({ refuseCall: 2 });
  choose(screen, ["beatos", "averatec-career", "offeros"]);
  pressInBar(screen, Str.t("repositories.level.full"));
  await settled();
  assert.deepEqual(screen.asked.levels, [
    ["root:df32e8a9", "full"],
    ["root:742d2192", "full"],
  ]);
  const said = bar(screen).textContent;
  assert.ok(said.includes(Str.t("repositories.batch.failed", "averatec-career")), said);
  assert.ok(said.includes(REFUSAL), said);
  assert.deepEqual(ticked(rowFor(screen, "beatos")), [Str.t("repositories.level.full")]);
  assert.ok(screen.tree.findAll(".repo-table")[1].textContent.includes("offeros"));
});

/* --- how often the engine is asked --------------------------------------------------------
 *
 * The screen is redrawn on every store change, and an ingest announces itself several
 * times as it works; `init --scan` walks every repository on the machine. The rule is
 * `store/asked.js`'s: ask once per store, remember the answer against what the engine
 * wrote, ask again when that moves.
 */

test("eight announcements about one store ask the engine once", async () => {
  const screen = await screenFor();
  for (let i = 0; i < 7; i += 1) screen.state.redraw();
  await settled();
  assert.equal(screen.asked.scans, 1, `the scan ran ${screen.asked.scans} times for one store`);
});

test("a store the engine has written since is asked about again", async () => {
  const screen = await screenFor();
  screen.state.data = { ...DATA, status: { last_ingest_at: "2099-01-01T00:00:00Z" } };
  screen.state.redraw();
  await settled();
  assert.equal(screen.asked.scans, 2, "the scan did not follow the store");
});

test("a repository changed here is remembered without asking the engine again", async () => {
  const screen = await screenFor();
  const before = screen.asked.scans;
  rowFor(screen, "offeros")
    .findAll("button")
    .find((node) => node.textContent === Str.t("repositories.level.full"))
    .fire("click");
  await settled();
  screen.state.redraw();
  await settled();
  assert.equal(screen.asked.scans, before, "the whole list was read again for a change the app made");
  assert.deepEqual(ticked(rowFor(screen, "offeros")), [Str.t("repositories.level.full")]);
});

/* --- both languages ---------------------------------------------------------------------- */

test("the screen draws in Chinese with no key and no English prose left in it", async () => {
  Str.setLang("zh-Hans");
  try {
    const screen = await screenFor({}, { project: "beatos" });
    const text = screen.tree.textContent;
    assert.doesNotMatch(text, /\b(repositories|settings|engine|common|unit)\.[a-zA-Z.]+/, text);
    for (const english of ["Recorded", "Found, not recorded", "Sessions", "Level", "recorded,"]) {
      assert.equal(text.includes(english), false, `English left on the screen: ${english}`);
    }
    assert.ok(text.includes(Str.t("repositories.counts", "2", "2")));
  } finally {
    Str.setLang("en");
  }
});
