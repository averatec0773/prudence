/* What the Overview reads, derived from the views and nothing else.
 *
 * The rule this file exists to keep, restated because this is where it would first be
 * broken: a bucket is a **sum of view columns**, a share is a **ratio of two columns of
 * one row**. A median, a threshold or an attribution is a view in
 * `src/prudence/store/app_views.py`, never a function here.
 *
 * Two things that look like arithmetic and are not:
 *
 * - **A hole is a hole.** A week whose thirty-day mark has not arrived has not measured
 *   zero; it has not measured. The series is cut into runs so nothing can join across
 *   one, and a zero is never invented to fill it.
 * - **Every share carries its denominator.** The chart prints `n`, because a screenshot
 *   has no pointer and a share without the number it is over cannot be checked.
 */

import { emptyBuckets, known } from "../design/purposes.js";
import { daysBefore, localDay, sessionsBetween, startOfLocalDay } from "./payload.js";

/** @typedef {"8w"|"90d"|"all"} RangeKey */

/** The three the picker offers, and how far back each looks. `all` has no first day. */
export const RANGES = /** @type {const} */ ([
  { key: "8w", label: "range.eightWeeks", days: 56 },
  { key: "90d", label: "range.ninetyDays", days: 90 },
  { key: "all", label: "range.all", days: null },
]);

export function rangeOf(key) {
  return RANGES.find((range) => range.key === key) ?? RANGES[0];
}

/** The first local day a range includes, or null for "all". */
export function firstDay(key, now = new Date()) {
  const range = rangeOf(key);
  if (range.days === null) return null;
  return daysBefore(localDay(now), range.days - 1);
}

/** The Monday of the ISO week a `yyyy-MM-dd` day falls in, as a `yyyy-MM-dd` day. */
export function mondayOf(day) {
  const date = startOfLocalDay(day);
  if (!date) return day;
  // `getDay()` is 0 for Sunday; ISO weeks start on Monday.
  const weekday = (date.getDay() + 6) % 7;
  date.setDate(date.getDate() - weekday);
  return localDay(date);
}

/**
 * Every ISO week in the range, oldest first, whether or not anything happened in it.
 *
 * **This is the x axis of every weekly chart, and both Overview charts share it**, so a
 * week sits at the same place in each and the two can be read against one another. It is
 * an ordinal axis over a complete list, not a date scale: the slots are equal width.
 *
 * The completeness is the point. A week with no row used to produce no slot at all, so a
 * line ran straight from one side of a four-week silence to the other and nobody could
 * see the silence. Here the week exists, the value is missing, and the chart draws the
 * hole it actually is.
 *
 * For "all" the axis starts at the earliest week anything was recorded in, taken across
 * usage, outcomes and commits together so that the two charts still agree.
 */
export function axisWeeks(data, { range = "8w", now = new Date() } = {}) {
  const from = firstDay(range, now) ?? earliestRecordedDay(data);
  if (!from) return [];
  const last = mondayOf(localDay(now));
  const out = [];
  let cursor = mondayOf(from);
  // A guard, not a rule: a store with a nonsense future date should not spin here.
  for (let i = 0; cursor <= last && i < 520; i += 1) {
    out.push(cursor);
    const next = startOfLocalDay(cursor);
    next.setDate(next.getDate() + 7);
    cursor = localDay(next);
  }
  return out;
}

/** The earliest local day any of the three weekly sources recorded. */
function earliestRecordedDay(data) {
  let earliest = null;
  const consider = (value) => {
    const day = String(value).slice(0, 10);
    if (day && (earliest === null || day < earliest)) earliest = day;
  };
  for (const row of data.usage) consider(row.day);
  for (const row of data.commits ?? []) consider(row.day);
  for (const row of data.outcomes ?? []) consider(row.week_start);
  return earliest;
}

/** Monday first, which is how the heat strip's seven rows read. */
export const WEEKDAYS = /** @type {const} */ (["mon", "tue", "wed", "thu", "fri", "sat", "sun"]);

function inRange(day, from) {
  return from === null || String(day) >= from;
}

function matchesProject(row, project) {
  return project === null || row.project === project;
}

/**
 * The three figures above the charts.
 *
 * Each comes from the view that counts the thing once: sessions from
 * `app_session_list`, hours from `app_usage_by_purpose_day.active_minutes`, and commits
 * from `app_commits_by_day`, which is the view that exists precisely because summing
 * `app_session_list` double counts a commit credited to two sessions.
 */
export function cards(data, { project = null, range = "8w", week = null, now = new Date() } = {}) {
  const from = week ?? firstDay(range, now);
  const to = week ? lastDayOfWeek(week) : localDay(now);

  let minutes = 0;
  let measuredSessions = 0;
  for (const row of data.usage) {
    if (!inRange(row.day, from) || String(row.day) > to) continue;
    if (!matchesProject(row, project)) continue;
    minutes += Number(row.active_minutes) || 0;
    measuredSessions += Number(row.measured_sessions) || 0;
  }

  let commits = 0;
  let fact = 0;
  let inferred = 0;
  for (const row of data.commits) {
    if (!inRange(row.day, from) || String(row.day) > to) continue;
    if (!matchesProject(row, project)) continue;
    commits += Number(row.commits) || 0;
    fact += Number(row.commits_fact) || 0;
    inferred += Number(row.commits_inferred) || 0;
  }

  const sessions = data.sessions.filter((row) => matchesProject(row, project));
  return {
    from,
    to,
    sessions: from === null ? sessions.length : sessionsBetween(sessions, from, to),
    // Nil rather than zero where nothing measured: a Claude Code version that writes no
    // usage fields is not zero hours, it is no measurement.
    hours: measuredSessions > 0 || minutes > 0 ? minutes / 60 : null,
    commits,
    fact,
    inferred,
  };
}

function lastDayOfWeek(monday) {
  const date = startOfLocalDay(monday);
  date.setDate(date.getDate() + 6);
  return localDay(date);
}

/**
 * Tokens by purpose, summed into the ISO week each local day falls in, over the whole
 * range's axis.
 *
 * Every week in the range is here, in order. A week the store has no row for carries
 * `measured: false`, and the chart draws an **empty slot** rather than a zero-height bar:
 * nothing was recorded is not the same statement as nothing was spent, and the two must
 * not look alike.
 */
export function weeks(data, { project = null, range = "8w", now = new Date() } = {}) {
  const axis = axisWeeks(data, { range, now });
  /** @type {Map<string, {week: string, byPurpose: Record<string, number>, total: number, measured: boolean}>} */
  const found = new Map(
    axis.map((week) => [week, { week, byPurpose: emptyBuckets(), total: 0, measured: false }])
  );

  for (const row of data.usage) {
    if (!matchesProject(row, project)) continue;
    const week = mondayOf(String(row.day));
    const bucket = found.get(week);
    // Outside the axis, which is the range's own test now that the axis defines it.
    if (!bucket) continue;
    const tokens = Number(row.total_tokens) || 0;
    bucket.byPurpose[known(String(row.purpose))] += tokens;
    bucket.total += tokens;
    bucket.measured = true;
  }

  return axis.map((week) => /** @type {any} */ (found.get(week)));
}

/**
 * What became of each week's work, per project, cut into runs at every hole.
 *
 * `alive_30d / measured_30d` and `reworked / lines` are both ratios of two columns of
 * one row, which is the widest arithmetic allowed here. A week whose thirty-day mark
 * has not arrived has `measured_30d = 0`: that is a **hole**, and the run ends there.
 */
export function outcomes(data, { project = null, range = "8w", now = new Date() } = {}) {
  const axis = axisWeeks(data, { range, now });
  const onAxis = new Set(axis);
  /** @type {Map<string, Map<string, any>>} */
  const byProject = new Map();

  for (const row of data.outcomes) {
    const week = mondayOf(String(row.week_start).slice(0, 10));
    if (!onAxis.has(week)) continue;
    if (!matchesProject(row, project)) continue;
    const name = String(row.project ?? row.repo_key ?? "");
    if (!byProject.has(name)) byProject.set(name, new Map());
    byProject.get(name).set(week, row);
  }

  return [...byProject.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([name, rows]) => {
      // One point per week on the shared axis, present or not. A week this project has
      // no row for is a hole, so `runs` cuts there and no line is drawn across it; before
      // the axis existed such a week produced no point at all and the line ran straight
      // through the silence.
      const points = axis.map((week) => {
        const row = rows.get(week);
        const measured = Number(row?.measured_30d) || 0;
        const lines = Number(row?.lines) || 0;
        return {
          week,
          // Null, not zero: nothing measured is not "none survived".
          alive: measured > 0 ? Number(row.alive_30d) / measured : null,
          measured30d: measured,
          rework: lines > 0 ? Number(row.reworked) / lines : null,
          lines,
          coverage:
            row?.coverage === null || row?.coverage === undefined ? null : Number(row.coverage),
        };
      });
      // Coverage is cut on **coverage**, not on alive. A week can have a measured
      // thirty-day mark and no coverage at all (`app_outcomes_by_week.coverage` is
      // `AVG(b.coverage)`, null when every counted commit came in without one), and
      // reusing the alive runs there drew the pale line straight over the hole.
      return {
        project: name,
        points,
        runs: {
          alive: runs(points, "alive"),
          rework: runs(points, "rework"),
          coverage: runs(points, "coverage"),
        },
      };
    });
}

/**
 * Consecutive measured points, as separate runs.
 *
 * Swift Charts needs one `series:` value per run so the line cannot be joined across a
 * gap; SVG needs one `<path>` per run for the same reason. The rule is the same and it
 * is the whole reason this function exists: **a hole is a hole.**
 */
export function runs(points, key) {
  const out = [];
  let current = [];
  for (const point of points) {
    if (point[key] === null) {
      if (current.length) out.push(current);
      current = [];
    } else {
      current.push(point);
    }
  }
  if (current.length) out.push(current);
  return out;
}

/**
 * Active minutes per local day, as one cell per day, seven rows Monday first.
 *
 * A day with no row in the view has **no cell value**, which is not a measured zero: the
 * view has no row for a day nothing happened on, and a grey cell that means "nothing
 * measured" is honest where a zero-valued cell would not be.
 */
export function heat(data, { project = null, range = "8w", now = new Date() } = {}) {
  const from = firstDay(range, now) ?? earliestDay(data, project);
  const to = localDay(now);
  if (!from) return { weeks: [], max: 0 };

  /** @type {Map<string, number>} */
  const minutes = new Map();
  for (const row of data.usage) {
    if (!matchesProject(row, project)) continue;
    const day = String(row.day);
    if (day < from || day > to) continue;
    minutes.set(day, (minutes.get(day) ?? 0) + (Number(row.active_minutes) || 0));
  }

  const columns = [];
  let cursor = mondayOf(from);
  while (cursor <= to) {
    const days = WEEKDAYS.map((_, index) => {
      const date = startOfLocalDay(cursor);
      date.setDate(date.getDate() + index);
      const day = localDay(date);
      const value = minutes.get(day);
      return {
        day,
        inRange: day >= from && day <= to,
        hours: value === undefined ? null : value / 60,
      };
    });
    columns.push({ week: cursor, days });
    const next = startOfLocalDay(cursor);
    next.setDate(next.getDate() + 7);
    cursor = localDay(next);
  }

  const max = Math.max(0, ...[...minutes.values()].map((value) => value / 60));
  return { weeks: columns, max };
}

function earliestDay(data, project = null) {
  let earliest = null;
  for (const row of data.usage) {
    if (!matchesProject(row, project)) continue;
    const day = String(row.day);
    if (earliest === null || day < earliest) earliest = day;
  }
  return earliest;
}

/**
 * A project's colour is its place in the **sorted** list of every project name, so it
 * does not move when the range picker changes which projects have a row.
 *
 * Past the sixth the scale repeats, which is honest about a chart that has stopped being
 * one anybody can read.
 */
export function projectColour(name, allProjects) {
  const index = [...allProjects].sort((a, b) => a.localeCompare(b)).indexOf(name);
  return `var(--proj-${(index < 0 ? 0 : index) % 6})`;
}
