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

/** A day offset back from a moment, as the engine writes one. */
function dayBefore(now, offset) {
  const date = new Date(now.getTime());
  date.setDate(date.getDate() - offset);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(
    date.getDate()
  ).padStart(2, "0")}`;
}

/** The Monday of a `yyyy-MM-dd` day. */
function mondayOf(day) {
  const [y, m, d] = day.split("-").map(Number);
  const date = new Date(y, m - 1, d);
  date.setDate(date.getDate() - ((date.getDay() + 6) % 7));
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(
    date.getDate()
  ).padStart(2, "0")}`;
}

function overviewFor(range, now, { days = [1], weeks = 0, guessed = 0 } = {}) {
  const outcomeRows = [];
  for (let week = 0; week < weeks; week += 1) {
    outcomeRows.push([
      "p",
      mondayOf(dayBefore(now, 7 * week + 7)),
      10,
      7,
      100,
      20,
      0.8,
    ]);
  }
  const data = readPayload({
    usage: {
      columns: ["day", "project", "repo_key", "bucket", "total_tokens", "heuristic_tokens", "sessions"],
      rows: days.flatMap((offset) => [
        [dayBefore(now, offset), "p", "root:p", "change", 600, guessed, 1],
        [dayBefore(now, offset), "p", "root:p", "talk", 400, 0, 1],
      ]),
    },
    activity: {
      columns: ["day", "project", "repo_key", "active_minutes", "sessions", "measured_sessions"],
      rows: days.map((offset) => [dayBefore(now, offset), "p", "root:p", 60, 1, 1]),
    },
    commits: { columns: ["day", "project", "commits", "commits_fact", "commits_inferred"], rows: [] },
    sessions: [],
    outcomes: {
      columns: ["project", "week_start", "measured_30d", "alive_30d", "lines", "reworked", "coverage"],
      rows: outcomeRows,
    },
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
  const dailyTitle = daily.findIndex((line) => line === "Tokens by what each reply did, per day");
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
    weekly.includes("Tokens by what each reply did, per week"),
    "the 365-day range no longer draws a weekly chart"
  );
  assert.ok(
    weekly.some((line) => line.startsWith("What each week's tokens")),
    "the weekly chart lost its weekly note"
  );
});

/**
 * The per-day totals are behind the disclosure, not a paragraph under the chart.
 *
 * The chart's caption was printed: at thirty days, thirty dates and figures in a run of
 * grey text between the bars and their legend, which the audit of 2026-09-22 read as the
 * noisiest thing on the card. The same figures are the table behind "How this is
 * measured", so the caption is kept for a screen reader and hidden from the page.
 */
test("the tokens chart prints no paragraph of totals, and its table carries them", () => {
  const screen = overviewFor("30d", new Date(2026, 8, 21, 12, 0, 0), { days: [1, 2, 3] });
  const chart = screen.findAll("svg").find((node) => node.getAttribute("class") === "bars");
  assert.ok(chart, "no tokens chart");
  const caption = screen
    .findAll("figcaption")
    .find((node) => node.textContent.includes("Sep 20, 2026"));
  assert.ok(caption, "the chart lost its caption altogether");
  assert.equal(caption.className, "sr", "the per-day totals are printed under the chart");

  const drawer = screen
    .findAll(".method")
    .find((node) => node.find("summary").textContent.includes("in a table"));
  drawer.fire("toggle");
  const cells = drawer.findAll("td").map((node) => node.textContent);
  assert.ok(cells.includes("Sep 20, 2026"), `the table has no row per day: ${cells.slice(0, 6)}`);
  const heads = drawer.findAll("th").map((node) => node.textContent);
  assert.deepEqual(heads.slice(1, 3), ["change", "talk"], "the table's columns are not the buckets");
});

/**
 * Tokens whose bucket rests on a guess from a tool's name are said, quietly, when there are
 * any, and nothing is said when there are none.
 */
test("the heuristic caption appears only when some tokens were bucketed by name", () => {
  const now = new Date(2026, 8, 21, 12, 0, 0);
  const guessed = words(overviewFor("30d", now, { days: [1], guessed: 250 }));
  const line = guessed.find((one) => one.includes("guessed from a tool's name"));
  assert.ok(line, "the guessed tokens are not mentioned");
  assert.match(line, /^250 tokens here \(25%\)/, line);

  const none = words(overviewFor("30d", now, { days: [1], guessed: 0 }));
  assert.equal(
    none.some((one) => one.includes("guessed from a tool's name")),
    false,
    "a caption about nothing being guessed"
  );
});

/**
 * The window is on the screen, above everything it frames.
 *
 * It was stated once, in grey, in the window's own head, and three captions said "in
 * range" rather than naming it, so a reader who had scrolled past the first card had lost
 * the time frame of every figure under it.
 */
test("the Overview says what it is over, in a sentence, above the figures", () => {
  const now = new Date(2026, 8, 21, 12, 0, 0);
  const said = words(overviewFor("30d", now));
  const summary = said.findIndex((line) => line.startsWith("All projects, last 30 days:"));
  assert.ok(summary >= 0, `the screen states no window: ${said.slice(0, 4)}`);
  assert.equal(summary, 0, "something is said before the frame everything below is read in");
  assert.match(said[summary], /\d+ sessions/, "the summary carries none of the figures");

  // And nothing on the screen says "in range" any more, in either language.
  for (const line of said) assert.doesNotMatch(line, /in range/i, line);
});

/** Each figure carries its unit, and the two words the engine lends the screen are glossed
 *  on the screen that uses them rather than left to be guessed. */
test("the three figures carry their units, and sitting, fact and inferred are glossed", () => {
  const said = words(overviewFor("30d", new Date(2026, 8, 21, 12, 0, 0))).join("\n");
  assert.match(said, /[\d.]+ active hours/, "the hours figure carries no unit");
  assert.match(said, /a sitting is one stretch of a session/i, "'sitting' is used and never explained");
  assert.match(said, /fact means the engine matched it/i, "'fact' is printed and never explained");
  assert.match(said, /inferred means it matched it by timing/i, "'inferred' is never explained");
});

/**
 * One question per card.
 *
 * "What became of each week's work" was three cards' worth in one: two charts with
 * different line styles, a legend whose first entry was not a project, a seventy-word note,
 * a method and a table.
 */
test("what became of the work is two cards, each with its own question", () => {
  const now = new Date(2026, 8, 21, 12, 0, 0);
  const screen = overviewFor("365d", now, { days: [1, 8, 15], weeks: 4 });
  const titles = screen.findAll("h2").map((node) => node.textContent);
  assert.ok(titles.includes("Still there after 30 days"), titles.join(" / "));
  assert.ok(titles.includes("Rewritten later"), titles.join(" / "));
  assert.equal(
    titles.includes("What became of each week's work"),
    false,
    "the two questions are still one card"
  );
  // The coverage is a band behind the lines, not a swatch in a row of projects, where it
  // read as a project of its own.
  const legends = screen.findAll(".legend");
  assert.ok(
    legends.some((legend) => legend.findAll(".band").length === 1),
    "the coverage is not drawn as the band it is"
  );
  for (const legend of legends) {
    assert.equal(
      legend.textContent.includes("pale wide"),
      false,
      "the coverage is still a legend entry pretending to be a project"
    );
  }
});

/**
 * The tables are behind the disclosure, and are not built until it is opened.
 *
 * They exist so a figure can be checked without a pointer, which is right; being open by
 * default is what made the screen unreadable. At 365 days they were about 210 rows and
 * 2,158 of the page's nodes, above and below the charts a reader had come for.
 */
test("at 365 days every table is behind a closed drawer and is built only when it is opened", () => {
  const now = new Date(2026, 8, 21, 12, 0, 0);
  const screen = overviewFor("365d", now, { days: [1, 8, 15, 40, 120], weeks: 6 });

  assert.deepEqual(screen.findAll("table"), [], "a full table is on the screen at first draw");
  const drawers = screen.findAll(".method");
  const withTables = drawers.filter((node) =>
    node.find("summary").textContent.includes("in a table")
  );
  assert.equal(withTables.length, 3, `three cards carry a table: ${drawers.length} drawers`);
  for (const drawer of withTables) {
    assert.match(
      drawer.find("summary").textContent,
      /\d+ rows behind it/,
      "the drawer does not say how much is in it"
    );
  }

  let nodes = 0;
  for (const _ of screen.walk()) nodes += 1;

  for (const drawer of withTables) drawer.fire("toggle");
  let opened = 0;
  for (const _ of screen.walk()) opened += 1;

  assert.equal(screen.findAll("table").length, 3, "opening the drawer produced no table");
  assert.ok(opened > nodes, "the tables were built at first draw after all");
  // Opening them twice does not build them twice.
  for (const drawer of withTables) drawer.fire("toggle");
  let again = 0;
  for (const _ of screen.walk()) again += 1;
  assert.equal(again, opened, "the table was built a second time");
});

/**
 * The heat strip has an axis.
 *
 * Seven rows and N columns of squares, with the day only inside each cell's `title`: a
 * pointer could read it and a screenshot could not, and nothing said which row was Monday.
 */
test("the heat strip names its rows and its months, in the reader's language", () => {
  const now = new Date(2026, 8, 21, 12, 0, 0);
  for (const language of Str.LANGUAGES) {
    Str.setLang(language);
    try {
      const screen = overviewFor("90d", now, { days: [1, 20, 50] });
      const strip = screen
        .findAll("svg")
        .find((node) => node.getAttribute("class") === "heat");
      assert.ok(strip, `${language}: no heat strip`);
      const labels = strip.children
        .filter((node) => node.localName === "text")
        .map((node) => node.textContent);
      for (const key of ["weekday.mon", "weekday.sun"]) {
        assert.ok(labels.includes(Str.t(key)), `${language}: ${key} is not on the strip: ${labels}`);
      }
      // Ninety days is three or four months, and each is named once under the first column
      // it starts in.
      const months = labels.filter((one) => !Object.values(WEEKDAY_NAMES(language)).includes(one));
      assert.ok(months.length >= 3, `${language}: the months are not under the strip: ${labels}`);
      assert.equal(new Set(months).size, months.length, `${language}: a month is named twice`);
    } finally {
      Str.setLang("en");
    }
  }
});

/** The seven names, in whichever language is in force. */
function WEEKDAY_NAMES(language) {
  return Object.fromEntries(
    ["mon", "tue", "wed", "thu", "fri", "sat", "sun"].map((key) => [
      key,
      Str.tIn(language, `weekday.${key}`),
    ])
  );
}

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
