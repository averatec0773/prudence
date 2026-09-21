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
  cards,
  firstDay,
  heat,
  mondayOf,
  outcomes,
  projectColour,
  runs,
  weeks,
} from "../src/store/overview.js";

const NOW = new Date(2026, 8, 21, 12, 0, 0); // Monday 21 September 2026, local

function payload({ usage = [], outcomes: out = [], commits = [], sessions = [] } = {}) {
  return readPayload({
    usage: { columns: Object.keys(usage[0] ?? { day: "" }), rows: usage.map(Object.values) },
    outcomes: { columns: Object.keys(out[0] ?? { project: "" }), rows: out.map(Object.values) },
    commits: { columns: Object.keys(commits[0] ?? { day: "" }), rows: commits.map(Object.values) },
    sessions,
  });
}

/* --- weeks -------------------------------------------------------------------------- */

test("a day lands in the ISO week that starts on its Monday", () => {
  assert.equal(mondayOf("2026-09-21"), "2026-09-21", "a Monday is its own week");
  assert.equal(mondayOf("2026-09-27"), "2026-09-21", "a Sunday belongs to the week before");
  assert.equal(mondayOf("2026-09-22"), "2026-09-21");
});

test("weeks come out oldest first, in the fixed purpose order", () => {
  const data = payload({
    usage: [
      { day: "2026-09-21", project: "a", purpose: "research", total_tokens: 10, active_minutes: 1 },
      { day: "2026-09-14", project: "a", purpose: "development", total_tokens: 20, active_minutes: 2 },
      { day: "2026-09-15", project: "a", purpose: "development", total_tokens: 5, active_minutes: 1 },
    ],
  });
  const out = weeks(data, { range: "8w", now: NOW });
  assert.deepEqual(out.map((w) => w.week), ["2026-09-14", "2026-09-21"]);
  assert.equal(out[0].total, 25, "the two days of one week are summed");
  assert.deepEqual(Object.keys(out[0].byPurpose).slice(0, 2), ["development", "research"]);
});

test("a week outside the range is not in the answer", () => {
  const data = payload({
    usage: [
      { day: "2026-01-05", project: "a", purpose: "development", total_tokens: 99, active_minutes: 1 },
      { day: "2026-09-21", project: "a", purpose: "development", total_tokens: 1, active_minutes: 1 },
    ],
  });
  assert.equal(weeks(data, { range: "8w", now: NOW }).length, 1);
  assert.equal(weeks(data, { range: "all", now: NOW }).length, 2);
});

test("the ranges look back as far as they say", () => {
  assert.equal(firstDay("8w", NOW), "2026-07-28", "eight weeks is 56 days inclusive");
  assert.equal(firstDay("90d", NOW), "2026-06-24");
  assert.equal(firstDay("all", NOW), null);
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
  const out = cards(data, { range: "8w", now: NOW });
  assert.equal(out.commits, 3, "the January commit is outside eight weeks");
  assert.equal(out.fact, 2);
  assert.equal(out.inferred, 1);
});

/* Nil rather than zero: a Claude Code version that writes no usage fields is not zero
   hours, it is no measurement. */
test("no active time measured is a dash, not a zero", () => {
  const empty = payload({ commits: [{ day: "2026-09-21", project: "a", commits: 1, commits_fact: 1, commits_inferred: 0 }] });
  assert.equal(cards(empty, { range: "8w", now: NOW }).hours, null);
});

test("a project filter applies to every figure on the screen", () => {
  const data = payload({
    usage: [
      { day: "2026-09-21", project: "a", purpose: "development", total_tokens: 10, active_minutes: 60 },
      { day: "2026-09-21", project: "b", purpose: "development", total_tokens: 90, active_minutes: 120 },
    ],
    commits: [
      { day: "2026-09-21", project: "a", commits: 1, commits_fact: 1, commits_inferred: 0 },
      { day: "2026-09-21", project: "b", commits: 5, commits_fact: 5, commits_inferred: 0 },
    ],
  });
  const onlyA = cards(data, { project: "a", range: "8w", now: NOW });
  assert.equal(onlyA.commits, 1);
  assert.equal(onlyA.hours, 1);
  assert.equal(weeks(data, { project: "a", range: "8w", now: NOW })[0].total, 10);
});

/* --- the heat strip --------------------------------------------------------------------- */

test("the heat strip has seven rows, Monday first, and contiguous weeks", () => {
  const data = payload({
    usage: [{ day: "2026-09-16", project: "a", purpose: "development", total_tokens: 1, active_minutes: 90 }],
  });
  const strip = heat(data, { range: "8w", now: NOW });
  assert.ok(strip.weeks.length >= 8);
  for (const column of strip.weeks) assert.equal(column.days.length, 7);
  // Wednesday 16 September is the third row of its column.
  const column = strip.weeks.find((c) => c.week === "2026-09-14");
  assert.equal(column.days[2].day, "2026-09-16");
  assert.equal(column.days[2].hours, 1.5);
  for (let i = 1; i < strip.weeks.length; i += 1) {
    const before = new Date(strip.weeks[i - 1].week);
    const after = new Date(strip.weeks[i].week);
    assert.equal((after - before) / 86400000, 7, "the columns are consecutive weeks");
  }
});

test("a day with no row is missing, not a measured zero", () => {
  const data = payload({
    usage: [{ day: "2026-09-16", project: "a", purpose: "development", total_tokens: 1, active_minutes: 90 }],
  });
  const strip = heat(data, { range: "8w", now: NOW });
  const column = strip.weeks.find((c) => c.week === "2026-09-14");
  assert.equal(column.days[0].hours, null, "Monday had no row");
  assert.equal(column.days[2].hours, 1.5);
});

test("the cells add up to the view's own active minutes", () => {
  const data = payload({
    usage: [
      { day: "2026-09-16", project: "a", purpose: "development", total_tokens: 1, active_minutes: 30 },
      { day: "2026-09-16", project: "a", purpose: "research", total_tokens: 1, active_minutes: 30 },
      { day: "2026-09-17", project: "a", purpose: "development", total_tokens: 1, active_minutes: 15 },
    ],
  });
  const strip = heat(data, { range: "8w", now: NOW });
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
