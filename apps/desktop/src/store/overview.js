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
 * Tokens by purpose, summed into the ISO week each local day falls in.
 *
 * Weeks with no row at all are **left out**, not filled with zeros: the chart's job is
 * to show what was measured. Weeks are returned oldest first.
 */
export function weeks(data, { project = null, range = "8w", now = new Date() } = {}) {
  const from = firstDay(range, now);
  /** @type {Map<string, {week: string, byPurpose: Record<string, number>, total: number}>} */
  const found = new Map();

  for (const row of data.usage) {
    if (!inRange(row.day, from)) continue;
    if (!matchesProject(row, project)) continue;
    const week = mondayOf(String(row.day));
    let bucket = found.get(week);
    if (!bucket) {
      bucket = { week, byPurpose: emptyBuckets(), total: 0 };
      found.set(week, bucket);
    }
    const tokens = Number(row.total_tokens) || 0;
    bucket.byPurpose[known(String(row.purpose))] += tokens;
    bucket.total += tokens;
  }

  return [...found.values()].sort((a, b) => a.week.localeCompare(b.week));
}

/**
 * What became of each week's work, per project, cut into runs at every hole.
 *
 * `alive_30d / measured_30d` and `reworked / lines` are both ratios of two columns of
 * one row, which is the widest arithmetic allowed here. A week whose thirty-day mark
 * has not arrived has `measured_30d = 0`: that is a **hole**, and the run ends there.
 */
export function outcomes(data, { project = null, range = "8w", now = new Date() } = {}) {
  const from = firstDay(range, now);
  /** @type {Map<string, any[]>} */
  const byProject = new Map();

  for (const row of data.outcomes) {
    if (from !== null && String(row.week_start).slice(0, 10) < from) continue;
    if (!matchesProject(row, project)) continue;
    const name = String(row.project ?? row.repo_key ?? "");
    if (!byProject.has(name)) byProject.set(name, []);
    byProject.get(name).push(row);
  }

  return [...byProject.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([name, rows]) => {
      rows.sort((a, b) => String(a.week_start).localeCompare(String(b.week_start)));
      const points = rows.map((row) => {
        const measured = Number(row.measured_30d) || 0;
        const lines = Number(row.lines) || 0;
        return {
          week: String(row.week_start).slice(0, 10),
          // Null, not zero: nothing measured is not "none survived".
          alive: measured > 0 ? Number(row.alive_30d) / measured : null,
          measured30d: measured,
          rework: lines > 0 ? Number(row.reworked) / lines : null,
          lines,
          coverage: row.coverage === null || row.coverage === undefined ? null : Number(row.coverage),
        };
      });
      return { project: name, points, runs: { alive: runs(points, "alive"), rework: runs(points, "rework") } };
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
  const from = firstDay(range, now) ?? earliestDay(data);
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

function earliestDay(data) {
  let earliest = null;
  for (const row of data.usage) {
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
