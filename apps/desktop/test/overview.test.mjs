/* What the Overview derives, and the rules it must not break.
 *
 * These are the requirements the Swift `ChartTests` guarded, written the way this stack
 * wants them. They are about the data, not about the marks: a test that asserted a
 * `BarMark`'s existence guarded SwiftUI and is not here.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { readPayload } from "../src/store/payload.js";
import {
  RANGES,
  axis,
  buckets,
  bucketOf,
  cards,
  firstDay,
  grainOf,
  heat,
  heuristicTokens,
  lastDayOf,
  mondayOf,
  outcomes,
  projectColour,
  runs,
  weekAxis,
} from "../src/store/overview.js";

const NOW = new Date(2026, 8, 21, 12, 0, 0); // Monday 21 September 2026, local

function payload({ usage = [], activity = [], outcomes: out = [], commits = [], sessions = [] } = {}) {
  return readPayload({
    usage: { columns: Object.keys(usage[0] ?? { day: "" }), rows: usage.map(Object.values) },
    activity: {
      columns: Object.keys(activity[0] ?? { day: "" }),
      rows: activity.map(Object.values),
    },
    outcomes: { columns: Object.keys(out[0] ?? { project: "" }), rows: out.map(Object.values) },
    commits: { columns: Object.keys(commits[0] ?? { day: "" }), rows: commits.map(Object.values) },
    sessions,
  });
}

/* --- the bucket rule -----------------------------------------------------------------
 *
 * Days up to sixty, weeks from ninety out. It is written in `RANGES` and everything else
 * reads it from there, so these tests are of the rule and not of a copy of it.
 */

test("the picker offers seven ranges, shortest first, ending in all", () => {
  assert.deepEqual(
    RANGES.map((one) => one.key),
    ["1d", "7d", "30d", "60d", "90d", "365d", "all"]
  );
  assert.deepEqual(
    RANGES.map((one) => one.days),
    [1, 7, 30, 60, 90, 365, null]
  );
});

test("a bucket is a day up to sixty days and a week beyond it", () => {
  assert.deepEqual(
    RANGES.map((one) => [one.key, grainOf(one.key)]),
    [
      ["1d", "day"],
      ["7d", "day"],
      ["30d", "day"],
      ["60d", "day"],
      ["90d", "week"],
      ["365d", "week"],
      ["all", "week"],
    ]
  );
});

test("a range this build does not have falls back to the default rather than throwing", () => {
  assert.equal(grainOf("8w"), "day", "the old eight-week key is not a range any more");
  assert.equal(firstDay("8w", NOW), firstDay("30d", NOW));
});

test("a day belongs to itself, and a week to the Monday it starts on", () => {
  assert.equal(bucketOf("2026-09-23", "day"), "2026-09-23");
  assert.equal(bucketOf("2026-09-23", "week"), "2026-09-21");
  // The last day a bucket covers, which is what filters the cards when one is clicked.
  assert.equal(lastDayOf("2026-09-23", "day"), "2026-09-23");
  assert.equal(lastDayOf("2026-09-21", "week"), "2026-09-27");
});

test("a day lands in the ISO week that starts on its Monday", () => {
  assert.equal(mondayOf("2026-09-21"), "2026-09-21", "a Monday is its own week");
  assert.equal(mondayOf("2026-09-27"), "2026-09-21", "a Sunday belongs to the week before");
  assert.equal(mondayOf("2026-09-22"), "2026-09-21");
});

/* --- how far back each range looks, at a month boundary ------------------------------
 *
 * Every range's day arithmetic, asked on a day chosen so that each answer crosses at
 * least one month end and one of them crosses a year end. Counting days by subtracting
 * numbers from a date string is how an off-by-a-month gets in, and a range whose first day
 * is a month out silently drops or invents a month of work.
 */

const FIRST_OF_MARCH = new Date(2026, 2, 1, 9, 0, 0); // Sunday 1 March 2026, local

test("every range's first day is counted inclusively, across a month boundary", () => {
  assert.equal(firstDay("1d", FIRST_OF_MARCH), "2026-03-01", "one day is today itself");
  assert.equal(firstDay("7d", FIRST_OF_MARCH), "2026-02-23");
  // 2026 is not a leap year, so February has 28 days: thirty days back inclusive is
  // 1 March minus 29, which is 31 January.
  assert.equal(firstDay("30d", FIRST_OF_MARCH), "2026-01-31");
  assert.equal(firstDay("60d", FIRST_OF_MARCH), "2026-01-01");
  assert.equal(firstDay("90d", FIRST_OF_MARCH), "2025-12-02");
  assert.equal(firstDay("365d", FIRST_OF_MARCH), "2025-03-02");
  assert.equal(firstDay("all", FIRST_OF_MARCH), null, "all has no first day");
});

test("a leap day is a day like any other", () => {
  const firstOfMarch2024 = new Date(2024, 2, 1, 9, 0, 0);
  // February 2024 has 29 days, so the same thirty-day range reaches one day further into
  // January than it does in 2026.
  assert.equal(firstDay("30d", firstOfMarch2024), "2024-02-01");
  assert.equal(firstDay("365d", firstOfMarch2024), "2023-03-03");
});

test("a daily axis has one slot per day, first day to today", () => {
  const data = payload();
  for (const [range, slots] of /** @type {[string, number][]} */ ([
    ["1d", 1],
    ["7d", 7],
    ["30d", 30],
    ["60d", 60],
  ])) {
    const out = axis(data, { range, now: FIRST_OF_MARCH });
    assert.equal(out.length, slots, `${range} should be ${slots} days`);
    assert.equal(out[0], firstDay(range, FIRST_OF_MARCH));
    assert.equal(out[out.length - 1], "2026-03-01", `${range} should end today`);
  }
});

/* One day is a real question, and the answer is one bar. An empty chart would be the app
   refusing to draw what it was asked for. */
test("one day is one bucket and never an empty chart", () => {
  const data = payload({
    usage: [
      { day: "2026-09-21", project: "a", bucket: "change", total_tokens: 40 },
      { day: "2026-09-20", project: "a", bucket: "change", total_tokens: 99 },
    ],
  });
  const out = buckets(data, { range: "1d", now: NOW });
  assert.equal(out.length, 1);
  assert.equal(out[0].bucket, "2026-09-21");
  assert.equal(out[0].measured, true);
  assert.equal(out[0].total, 40, "yesterday is not in a one-day range");
});

test("a weekly axis has one slot per ISO week the range touches", () => {
  const data = payload();
  // 90 days back from Sunday 1 March 2026 is 2 December 2025, whose Monday is 1 December.
  // 1 December to 23 February inclusive is thirteen Mondays, and today's own week makes
  // fourteen slots.
  const ninety = axis(data, { range: "90d", now: FIRST_OF_MARCH });
  assert.equal(ninety[0], "2025-12-01");
  assert.equal(ninety[ninety.length - 1], "2026-02-23", "1 March is a Sunday");
  assert.equal(ninety.length, 13);

  const year = axis(data, { range: "365d", now: FIRST_OF_MARCH });
  assert.equal(year[0], mondayOf(firstDay("365d", FIRST_OF_MARCH)));
  assert.equal(year.length, 53);
});

/* --- buckets -------------------------------------------------------------------------- */

test("time slots come out oldest first, each with its tokens per bucket", () => {
  const data = payload({
    usage: [
      { day: "2026-09-21", project: "a", bucket: "read", total_tokens: 10, heuristic_tokens: 4 },
      { day: "2026-09-14", project: "a", bucket: "change", total_tokens: 20, heuristic_tokens: 0 },
      { day: "2026-09-15", project: "a", bucket: "change", total_tokens: 5, heuristic_tokens: 0 },
    ],
  });
  const out = buckets(data, { range: "90d", now: NOW });
  // Every week the range touches, not only the ones with rows: a week with nothing in it
  // is a slot rather than an absence (delivery A review, ruling 1).
  assert.deepEqual(out.map((w) => w.bucket).slice(-2), ["2026-09-14", "2026-09-21"]);
  assert.deepEqual(
    out.filter((w) => w.measured).map((w) => w.bucket),
    ["2026-09-14", "2026-09-21"]
  );
  const fourteenth = out.find((w) => w.bucket === "2026-09-14");
  assert.equal(fourteenth.total, 25, "the two days of one week are summed");
  // The values, not the key order of `byBucket`: that order is `emptyMix()` whatever the
  // data is, so asserting it could not fail. The order the legend and the table walk is
  // `BUCKETS`, which `buckets.test.mjs` pins against the engine.
  assert.equal(fourteenth.byBucket.change, 25);
  assert.equal(fourteenth.byBucket.read, 0);
  const twentyFirst = out.find((w) => w.bucket === "2026-09-21");
  assert.equal(twentyFirst.byBucket.read, 10);
  assert.equal(twentyFirst.byBucket.change, 0);
  // The part of the range resting on the engine's name heuristic, summed from its own
  // column, which is what the chart's quiet caption says.
  assert.deepEqual(heuristicTokens(out), { tokens: 4, share: 4 / 35 });
  assert.deepEqual(heuristicTokens(out.slice(0, -1)), { tokens: 0, share: 0 });
});

/* The same rows under a daily range are two separate days, not one week. This is the
   bucket rule doing its work, and it is what a reader on "7 days" is asking for. */
test("the same two days are one weekly bucket and two daily ones", () => {
  const data = payload({
    usage: [
      { day: "2026-09-20", project: "a", bucket: "change", total_tokens: 20 },
      { day: "2026-09-21", project: "a", bucket: "change", total_tokens: 5 },
    ],
  });
  const daily = buckets(data, { range: "7d", now: NOW }).filter((one) => one.measured);
  assert.deepEqual(
    daily.map((one) => [one.bucket, one.total]),
    [
      ["2026-09-20", 20],
      ["2026-09-21", 5],
    ]
  );

  // 20 September 2026 is a Sunday, so weekly it belongs to the week before 21 September.
  const weekly = buckets(data, { range: "90d", now: NOW }).filter((one) => one.measured);
  assert.deepEqual(
    weekly.map((one) => [one.bucket, one.total]),
    [
      ["2026-09-14", 20],
      ["2026-09-21", 5],
    ]
  );
});

test("a bucket outside the range is not in the answer", () => {
  const data = payload({
    usage: [
      { day: "2026-01-05", project: "a", bucket: "change", total_tokens: 99 },
      { day: "2026-09-21", project: "a", bucket: "change", total_tokens: 1 },
    ],
  });
  // The January row is outside a thirty-day range, so no slot is drawn for it at all;
  // the axis starts where the range does, not where the data does.
  const month = buckets(data, { range: "30d", now: NOW });
  assert.equal(month.length, 30, "thirty slots for thirty days");
  assert.deepEqual(month.filter((w) => w.measured).map((w) => w.bucket), ["2026-09-21"]);

  // "All" reaches back to the January row, so the axis spans every week between the two
  // and the silent weeks in the middle are slots, not an absence.
  const all = buckets(data, { range: "all", now: NOW });
  assert.equal(all[0].bucket, "2026-01-05");
  assert.equal(all[all.length - 1].bucket, "2026-09-21");
  assert.deepEqual(all.filter((w) => w.measured).map((w) => w.bucket), ["2026-01-05", "2026-09-21"]);
  assert.equal(all.length, 38, "every week between the two, inclusive");
});

/* --- the outcomes axis ----------------------------------------------------------------
 *
 * `app_outcomes_by_week` has one row per project per week and there is no daily view, so
 * re-bucketing it into days would be the app inventing a figure. The chart stays weekly
 * under every range and the card's note says so.
 */

test("the outcomes axis is weekly under a daily range too", () => {
  const data = payload();
  for (const range of ["1d", "7d", "30d", "60d", "90d"]) {
    const weeks = weekAxis(data, { range, now: NOW });
    assert.ok(weeks.length >= 1, `${range} should still have a week`);
    for (const week of weeks) {
      assert.equal(mondayOf(week), week, `${range}: ${week} is not a Monday`);
    }
  }
  // A one-day range is the week that day falls in, which is one slot and not none.
  assert.deepEqual(weekAxis(data, { range: "1d", now: NOW }), ["2026-09-21"]);
});

/* --- a hole is a hole ---------------------------------------------------------------- */

test("a nil cuts the series into two runs", () => {
  const points = [
    { week: "1", alive: 0.5 },
    { week: "2", alive: null },
    { week: "3", alive: 0.7 },
  ];
  const out = runs(points, "alive");
  assert.equal(out.length, 2);
  assert.deepEqual(out.map((run) => run.length), [1, 1]);
});

test("leading and trailing holes are not runs of their own", () => {
  const points = [
    { week: "1", alive: null },
    { week: "2", alive: 0.5 },
    { week: "3", alive: null },
  ];
  assert.deepEqual(runs(points, "alive").map((r) => r.length), [1]);
});

test("nothing measured is no runs at all", () => {
  assert.deepEqual(runs([{ week: "1", alive: null }], "alive"), []);
});

test("one measured week between two holes is its own run", () => {
  const points = [
    { week: "1", alive: null },
    { week: "2", alive: 0.42 },
    { week: "3", alive: null },
    { week: "4", alive: 0.6 },
  ];
  const out = runs(points, "alive");
  assert.equal(out.length, 2);
  assert.equal(out[0][0].alive, 0.42);
});

/* A week whose thirty-day mark has not arrived has `measured_30d = 0`. That is a hole,
   and it must not become a share of zero. */
test("a week that measured nothing is a hole, never a zero", () => {
  const data = payload({
    outcomes: [
      { project: "a", week_start: "2026-09-07", measured_30d: 4, alive_30d: 2, lines: 100, reworked: 10, coverage: 0.9 },
      { project: "a", week_start: "2026-09-14", measured_30d: 0, alive_30d: 0, lines: 0, reworked: 0, coverage: null },
    ],
  });
  const [series] = outcomes(data, { range: "all", now: NOW });
  assert.equal(series.points[0].alive, 0.5);
  assert.equal(series.points[1].alive, null, "not 0");
  assert.equal(series.points[1].rework, null, "not 0");
  assert.equal(series.runs.alive.length, 1, "the run ends at the hole");
});

test("every share is printed over its own denominator", () => {
  const data = payload({
    outcomes: [
      { project: "a", week_start: "2026-09-07", measured_30d: 7, alive_30d: 3, lines: 40, reworked: 8, coverage: 0.8 },
    ],
  });
  const [series] = outcomes(data, { range: "all", now: NOW });
  assert.equal(series.points[0].measured30d, 7);
  assert.equal(series.points[0].lines, 40);
});

/* --- the cards ------------------------------------------------------------------------ */

test("commits come from the view that counts a commit once", () => {
  const data = payload({
    commits: [
      { day: "2026-09-21", project: "a", commits: 3, commits_fact: 2, commits_inferred: 1 },
      { day: "2026-01-01", project: "a", commits: 9, commits_fact: 9, commits_inferred: 0 },
    ],
  });
  const out = cards(data, { range: "30d", now: NOW });
  assert.equal(out.commits, 3, "the January commit is outside thirty days");
  assert.equal(out.fact, 2);
  assert.equal(out.inferred, 1);
});

/* Clicking a bar filters the cards to that bucket. A day is one day; a week is the seven
   days it covers, which is what `lastDayOf` decides. */
test("a chosen bucket filters the cards to exactly the days it covers", () => {
  const data = payload({
    commits: [
      { day: "2026-09-21", project: "a", commits: 1, commits_fact: 1, commits_inferred: 0 },
      { day: "2026-09-23", project: "a", commits: 4, commits_fact: 4, commits_inferred: 0 },
    ],
  });
  const later = new Date(2026, 8, 27, 12, 0, 0); // Sunday 27 September 2026
  const oneDay = cards(data, { range: "30d", bucket: "2026-09-21", now: later });
  assert.equal(oneDay.commits, 1, "a daily bucket is one day");
  const oneWeek = cards(data, { range: "90d", bucket: "2026-09-21", now: later });
  assert.equal(oneWeek.commits, 5, "a weekly bucket is its seven days");
});

/* Nil rather than zero: a Claude Code version that writes no usage fields is not zero
   hours, it is no measurement. */
test("no active time measured is a dash, not a zero", () => {
  const empty = payload({ commits: [{ day: "2026-09-21", project: "a", commits: 1, commits_fact: 1, commits_inferred: 0 }] });
  assert.equal(cards(empty, { range: "30d", now: NOW }).hours, null);
});

test("a project filter applies to every figure on the screen", () => {
  const data = payload({
    usage: [
      { day: "2026-09-21", project: "a", bucket: "change", total_tokens: 10 },
      { day: "2026-09-21", project: "b", bucket: "change", total_tokens: 90 },
    ],
    activity: [
      { day: "2026-09-21", project: "a", active_minutes: 60, measured_sessions: 1 },
      { day: "2026-09-21", project: "b", active_minutes: 120, measured_sessions: 1 },
    ],
    commits: [
      { day: "2026-09-21", project: "a", commits: 1, commits_fact: 1, commits_inferred: 0 },
      { day: "2026-09-21", project: "b", commits: 5, commits_fact: 5, commits_inferred: 0 },
    ],
  });
  const onlyA = cards(data, { project: "a", range: "30d", now: NOW });
  assert.equal(onlyA.commits, 1);
  assert.equal(onlyA.hours, 1);
  const dayOfA = buckets(data, { project: "a", range: "30d", now: NOW }).find(
    (one) => one.bucket === "2026-09-21"
  );
  assert.equal(dayOfA.total, 10);
});

/* Hours are a session's, not a reply's, so they come from the activity view and never
   from the bucket view: a day whose sessions spent no tokens still has its hours, and a
   day with tokens and no activity row has none. The purpose view carried both, which is
   why this used to be one read. */
test("the hours come from the activity view and nothing else", () => {
  const data = payload({
    usage: [{ day: "2026-09-20", project: "a", bucket: "change", total_tokens: 10 }],
    activity: [{ day: "2026-09-21", project: "a", active_minutes: 45, measured_sessions: 1 }],
  });
  assert.equal(cards(data, { range: "7d", now: NOW }).hours, 0.75);
  assert.equal(cards(data, { range: "7d", bucket: "2026-09-20", now: NOW }).hours, null);
  const strip = heat(data, { range: "7d", now: NOW });
  const cells = strip.weeks.flatMap((column) => column.days);
  assert.equal(cells.find((cell) => cell.day === "2026-09-21").hours, 0.75);
  assert.equal(cells.find((cell) => cell.day === "2026-09-20").hours, null);
});

/* --- the heat strip --------------------------------------------------------------------- */

test("the heat strip has seven rows, Monday first, and contiguous weeks", () => {
  const data = payload({
    activity: [{ day: "2026-09-16", project: "a", active_minutes: 90 }],
  });
  const strip = heat(data, { range: "90d", now: NOW });
  assert.ok(strip.weeks.length >= 8);
  for (const column of strip.weeks) assert.equal(column.days.length, 7);
  // Wednesday 16 September is the third row of its column.
  const column = strip.weeks.find((c) => c.week === "2026-09-14");
  assert.equal(column.days[2].day, "2026-09-16");
  assert.equal(column.days[2].hours, 1.5);
  for (let i = 1; i < strip.weeks.length; i += 1) {
    const before = new Date(strip.weeks[i - 1].week);
    const after = new Date(strip.weeks[i].week);
    assert.equal((after.getTime() - before.getTime()) / 86400000, 7, "the columns are consecutive weeks");
  }
});

test("a day with no row is missing, not a measured zero", () => {
  const data = payload({
    activity: [{ day: "2026-09-16", project: "a", active_minutes: 90 }],
  });
  const strip = heat(data, { range: "90d", now: NOW });
  const column = strip.weeks.find((c) => c.week === "2026-09-14");
  assert.equal(column.days[0].hours, null, "Monday had no row");
  assert.equal(column.days[2].hours, 1.5);
});

test("the cells add up to the view's own active minutes", () => {
  const data = payload({
    activity: [
      { day: "2026-09-16", project: "a", active_minutes: 30 },
      { day: "2026-09-16", project: "b", active_minutes: 30 },
      { day: "2026-09-17", project: "a", active_minutes: 15 },
    ],
  });
  const strip = heat(data, { range: "90d", now: NOW });
  const total = strip.weeks
    .flatMap((c) => c.days)
    .reduce((sum, cell) => sum + (cell.hours ?? 0), 0);
  assert.ok(Math.abs(total - 75 / 60) < 1e-9, `${total}`);
});

/* --- the project scale --------------------------------------------------------------- */

test("a project keeps its colour whatever order it arrives in", () => {
  const all = ["zulu", "alpha", "mike"];
  assert.equal(projectColour("alpha", all), projectColour("alpha", [...all].reverse()));
  assert.equal(projectColour("alpha", all), "var(--proj-0)", "sorted, so alpha is first");
  assert.equal(projectColour("mike", all), "var(--proj-1)");
  assert.equal(projectColour("zulu", all), "var(--proj-2)");
});

test("the scale wraps rather than running out", () => {
  const many = Array.from({ length: 9 }, (_, i) => `p${i}`);
  assert.equal(projectColour("p6", many), projectColour("p0", many));
});


test("the coverage series is cut where coverage is missing, not where alive is", () => {
  // A week can have a measured thirty-day mark and no coverage at all: the view's
  // `coverage` is `AVG(b.coverage)` and is null when every counted commit arrived without
  // one. Reusing the alive runs there drew the pale line straight over the hole.
  const rows = [
    { project: "alpha", week_start: "2026-08-31", measured_30d: 10, alive_30d: 9, lines: 10, reworked: 1, coverage: 0.9 },
    { project: "alpha", week_start: "2026-09-07", measured_30d: 10, alive_30d: 8, lines: 10, reworked: 1, coverage: null },
    { project: "alpha", week_start: "2026-09-14", measured_30d: 10, alive_30d: 7, lines: 10, reworked: 1, coverage: 0.4 },
  ];
  const [one] = outcomes(payload({ outcomes: rows }), { range: "all" });

  assert.equal(one.runs.alive.length, 1, "alive was measured every week, so one run");
  assert.equal(one.runs.coverage.length, 2, "coverage has a hole, so two runs");
  assert.deepEqual(
    one.runs.coverage.map((run) => run.map((point) => point.week)),
    [["2026-08-31"], ["2026-09-14"]]
  );
});

test("a project with no usage row still gets its own colour", () => {
  // `data.projects` comes from `app_session_list`. A repository with counted commits and
  // no session is not in it, and `indexOf` returning -1 used to hand it
  // the first project's colour, so the legend showed two names under one swatch.
  const known = ["alpha", "beta"];
  assert.notEqual(projectColour("gamma", [...known, "gamma"]), projectColour("alpha", [...known, "gamma"]));
  // And the colour a project gets does not depend on which others are present.
  assert.equal(projectColour("beta", ["alpha", "beta"]), projectColour("beta", ["alpha", "beta", "gamma"]));
});
