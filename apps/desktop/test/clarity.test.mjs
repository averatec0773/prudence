/* What a reader who has never seen the app is told, and where.
 *
 * Every rule here is a defect found by rendering the screens against the founder's own
 * store on 2026-09-22 and reading what came out. They are statements about the words on
 * the screen, so they are asserted against a rendered screen and not against a string
 * table: a caption is only wrong in the place it is used.
 *
 * The DOM is the shim in `dom.mjs`, with `querySelector` added for the heat strip. Five
 * methods and not a dependency, on the same reasoning as the rest of the suite.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { installDom } from "./dom.mjs";
import * as Str from "../src/text/strings.js";

const here = dirname(fileURLToPath(import.meta.url));
const app = join(here, "..");

installDom();
// `heatStrip` reaches for `querySelector("title")` on a mark it has just built. The shim
// has no selectors; this is enough of one for a node's own children.
const madeNS = document.createElementNS;
/** @type {any} */ (document).createElementNS = (ns, tag) => {
  const node = /** @type {any} */ (madeNS(ns, tag));
  node.querySelector = (want) =>
    node.children.find((child) => String(child.localName) === String(want)) ?? null;
  return node;
};

for (const language of Str.LANGUAGES) {
  Str.load(
    language,
    JSON.parse(readFileSync(join(app, `src/text/strings.${language}.json`), "utf8"))
  );
}
Str.setLang("en");

const { overview } = await import("../src/ui/overview.js");
const { observations } = await import("../src/ui/observations.js");
const { reviewLine } = await import("../src/text/sentences.js");
const { readPayload } = await import("../src/store/payload.js");

/** Everything a node and its descendants say, in order. */
function words(node) {
  const out = [];
  const walk = (one) => {
    if (one.own) out.push(String(one.own));
    for (const child of one.children ?? []) walk(child);
  };
  walk(node);
  return out;
}

/* --- the Overview's tokens chart --------------------------------------------------- */

function overviewFor(range, now) {
  const day = (offset) => {
    const date = new Date(now.getTime());
    date.setDate(date.getDate() - offset);
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(
      date.getDate()
    ).padStart(2, "0")}`;
  };
  const data = readPayload({
    usage: {
      columns: ["day", "project", "repo_key", "purpose", "total_tokens", "active_minutes", "measured_sessions", "sessions"],
      rows: [[day(1), "p", "root:p", "development", 1000, 60, 1, 1]],
    },
    commits: { columns: ["day", "project", "commits", "commits_fact", "commits_inferred"], rows: [] },
    sessions: [],
    outcomes: { columns: ["project", "week_start"], rows: [] },
    observations: { columns: [], rows: [] },
    reviews: { columns: [], rows: [] },
    projects: [{ key: "root:p", name: "p" }],
  });
  return /** @type {any} */ (
    overview(/** @type {any} */ ({ data, project: null, range, bucket: null, onBucket() {} }))
  );
}

/**
 * A chart drawn per day must not be described per week.
 *
 * The title switched on the grain and the note and the method did not, so a chart with
 * one bar per day carried "What each week's tokens went on" under it and "summed into the
 * ISO week each local day falls in" behind its disclosure. Two of the three sentences
 * about the picture were about a different picture.
 */
test("a daily tokens chart is described in days, and a weekly one in weeks", () => {
  const now = new Date(2026, 8, 21, 12, 0, 0);

  const daily = words(overviewFor("30d", now));
  const dailyTitle = daily.findIndex((line) => line === "Tokens by purpose, per day");
  assert.ok(dailyTitle >= 0, "the 30-day range no longer draws a daily chart");
  // The three sentences that belong to that chart: its note, and the two in its
  // disclosure. None of them may name a week.
  const aboutTheChart = daily
    .slice(dailyTitle)
    .filter((line) => line.startsWith("What each") || line.startsWith("Summed from"));
  assert.ok(aboutTheChart.length >= 2, `nothing describes the chart: ${aboutTheChart}`);
  for (const line of aboutTheChart) {
    assert.doesNotMatch(line, /\bweek/i, `a per-day chart is described per week: ${line}`);
  }

  const weekly = words(overviewFor("365d", now));
  assert.ok(
    weekly.includes("Tokens by purpose, per week"),
    "the 365-day range no longer draws a weekly chart"
  );
  assert.ok(
    weekly.some((line) => line.startsWith("What each week's tokens")),
    "the weekly chart lost its weekly note"
  );
});

/* --- the Observations screen ------------------------------------------------------- */

function observationRow(over = {}) {
  return {
    repo_key: "root:p",
    project: "p",
    pooled: 0,
    fact: "compactions",
    threshold_text: "compactions > 0",
    threshold_op: ">",
    threshold_value: 0,
    outcome: "alive_head",
    direction: "lower",
    with_n: 16,
    without_n: 33,
    with_value: 0.73,
    without_value: 0.93,
    coverage: 0.92,
    fact_commits: 642,
    inferred_commits: 25,
    fact_version: 1,
    observation_id: 1,
    sentence: "",
    ...over,
  };
}

function observationsFor(rows) {
  return /** @type {any} */ (
    observations({
      data: { observations: rows, status: { observation_fact_version: 1 }, contract: 3 },
      info: null,
      project: null,
      range: "30d",
      bucket: null,
      onBucket() {},
      redraw() {},
    })
  );
}

/**
 * The definition comes before the thing it defines.
 *
 * "An observation splits your own sessions in two at one threshold" was the last line on
 * the page, under every card, so a reader meeting the word for the first time found out
 * what it meant after scrolling past everything it explains.
 */
test("what an observation is, is said above the first card and not under the last", () => {
  const said = words(observationsFor([observationRow()]));
  const definition = said.findIndex((line) => line.startsWith("An observation splits"));
  const firstCard = said.findIndex((line) => line === "compacted context");
  assert.ok(definition >= 0, "the screen no longer says what an observation is");
  assert.ok(firstCard >= 0, "the screen drew no card");
  assert.ok(
    definition < firstCard,
    "the definition of an observation is below the first card that uses it"
  );
});

/** An empty screen has to say what is missing, which needs the word explaining too. */
test("the empty Observations screen still says what an observation is", () => {
  const said = words(observationsFor([]));
  assert.ok(
    said.some((line) => line.startsWith("An observation splits")),
    "'no observations yet' with nothing saying what one is"
  );
});

/**
 * The words on a card are glossed somewhere on the screen.
 *
 * "still at head" is a git word, and "coverage 93%, method: 642 fact, 25 inferred" is
 * three terms in eight words. None of them was explained anywhere on this screen.
 */
test("at head, coverage, fact and inferred are all explained on the screen that uses them", () => {
  const said = words(observationsFor([observationRow()])).join("\n");
  assert.match(said, /Still at head is the share/, "'at head' is used and never explained");
  assert.match(said, /Coverage is the mean share/, "'coverage' is printed and never explained");
  assert.match(said, /inferred means it matched by timing/, "'inferred' is printed and never explained");
});

/* --- one figure, one format -------------------------------------------------------- */

/**
 * A review is dated the same way wherever it is named.
 *
 * The Review screen's head built the line with the reader's own date format and the
 * panel built the same line with a raw `yyyy-MM-dd` slice, so one review was "Sep 7, 2026
 * to Sep 21, 2026" in the window and "2026-09-07 to 2026-09-21" in the panel.
 */
test("a review's dates are the reader's, wherever the review is named", () => {
  const line = reviewLine(
    { id: 1, range_start: "2026-09-07T00:00:00", range_end: "2026-09-21T00:00:00", project: "p" },
    "en"
  );
  assert.doesNotMatch(line, /\d{4}-\d{2}-\d{2}/, `a raw stored date reached the reader: ${line}`);
  assert.match(line, /Sep 7, 2026/);
  assert.match(line, /Sep 21, 2026/);
});

/**
 * The panel's second block is a rolling seven days, so it must not be captioned with a
 * word that names a calendar week.
 *
 * `store/payload.js`'s `lastSevenDays` counts from today backwards, which is what
 * `prudence usage --last 7d` counts; the Overview's chart buckets by ISO week, which is a
 * different question. The panel said "This week" over the first of the two.
 */
test("the panel's rolling seven days is not captioned as a calendar week", () => {
  const panelSource = readFileSync(join(app, "src/ui/panel.js"), "utf8");
  assert.match(
    panelSource,
    /block\(t\("menu\.lastSevenDays"\), weekBlock\(data\)\)/,
    "the panel's seven-day block is captioned with something else again"
  );
  for (const language of Str.LANGUAGES) {
    Str.setLang(language);
    assert.doesNotMatch(
      Str.t("menu.lastSevenDays"),
      /this week|本周/i,
      `the seven-day caption names a calendar week in ${language}`
    );
  }
  Str.setLang("en");
});
