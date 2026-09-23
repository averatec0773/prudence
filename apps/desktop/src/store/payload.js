/* The store's answer, as the pages read it.
 *
 * The shell sends one JSON payload per page load: `src-tauri/src/store.rs` selects from
 * the `app_*` views and nothing else. This module turns it into rows and answers the two
 * questions the panel asks of it. It replaces the mockups' `derive.js`, which was written
 * against frozen demo data and carried sixteen unreachable exports, one of which invented
 * an unweighted mean of per-week coverage and claimed in its comment to match
 * `reviews/build.outcome_totals`, which averages per commit. That is gone.
 *
 * **The rule this module exists to keep** (`DESIGN.md`, "the app owns no numbers"): a
 * bucket is a **sum of view columns**, a share is a **ratio of two columns of one row**,
 * and nothing else happens here. A median, a threshold or an attribution is a view in
 * `src/prudence/store/app_views.py`.
 */

import { BUCKETS, emptyMix, known } from "../design/buckets.js";

/** @typedef {{ columns: string[], rows: (string|number|null)[][] }} Block */

/**
 * Every block the shell sends, as arrays of objects.
 *
 * The shell sends `{columns, rows}` for the wide views and arrays of objects for the
 * narrow ones; this is the one place that difference is absorbed, so no page has to know
 * which is which.
 *
 * @param {any} value
 * @returns {Record<string, any>[]}
 */
export function rowsOf(value) {
  if (Array.isArray(value)) return value;
  if (value && Array.isArray(value.rows) && Array.isArray(value.columns)) {
    const { columns, rows } = /** @type {Block} */ (value);
    return rows.map((row) => Object.fromEntries(columns.map((name, i) => [name, row[i]])));
  }
  return [];
}

/**
 * A column the engine stores as JSON text.
 *
 * `app_review.sections` and `.numbers` are JSON documents in a TEXT column, so they
 * arrive as strings. The mockups' version called `.forEach` on them, which throws; it
 * was never reached because no screen used it yet, and the review screen would have
 * found it the hard way. Parsed once, here, where the payload is read.
 *
 * A column that will not parse is **null**, not an empty array: a review whose sections
 * cannot be read is a review the screen must say it cannot read, not one that looks
 * empty.
 */
function jsonColumn(value) {
  if (value === null || value === undefined) return null;
  if (typeof value !== "string") return value;
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

/**
 * @param {any} payload the shell's `store_read` answer
 */
export function readPayload(payload) {
  const source = payload ?? {};
  return {
    /** `app_status`, one row, or null when the store had none. */
    status: /** @type {Record<string, any>|null} */ (source.status ?? null),
    /** `app_usage_by_bucket_day`: tokens per local day, project and bucket. */
    usage: rowsOf(source.usage),
    /** `app_activity_by_day`: active minutes and sessions per local day and project. */
    activity: rowsOf(source.activity),
    commits: rowsOf(source.commits),
    sessions: rowsOf(source.sessions),
    outcomes: rowsOf(source.outcomes),
    observations: rowsOf(source.observations),
    reviews: rowsOf(source.reviews).map((review) => ({
      ...review,
      sections: jsonColumn(review.sections),
      numbers: jsonColumn(review.numbers),
    })),
    projects: rowsOf(source.projects),
    contract: source.app_contract_version ?? null,
    /** Which answer this is. The shell moves it only when a figure moves; `store/drawn.js`
     *  is what reads it, and says why a page must not redraw without one. */
    revision: typeof source.revision === "number" ? source.revision : null,
  };
}

/* --- local days -------------------------------------------------------------------- */

/** `2026-09-21` for a `Date`, in local time, which is the day the engine means. */
export function localDay(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function startOfLocalDay(day) {
  const [year, month, date] = String(day).split("-").map(Number);
  return new Date(year, month - 1, date);
}

export function daysBefore(day, n) {
  const date = startOfLocalDay(day);
  date.setDate(date.getDate() - n);
  return localDay(date);
}

/**
 * Sessions started inside a window of local days, as **rows of `app_session_list`**.
 *
 * Never a sum of `app_usage_by_bucket_day.sessions`: that column is per bucket per day,
 * so summing it counts one session once for every day and bucket it touched.
 */
export function sessionsBetween(sessions, fromDay, toDay) {
  const start = startOfLocalDay(fromDay).getTime();
  const end = startOfLocalDay(toDay).getTime() + 86_400_000;
  return sessions.filter((row) => {
    const at = Date.parse(String(row.started_at));
    return Number.isFinite(at) && at >= start && at < end;
  }).length;
}

/**
 * What happened today: sessions started and commits counted, both for the machine's
 * own today rather than for the last day the data happens to have a row for.
 */
export function today(data, now = new Date()) {
  const day = localDay(now);
  const commits = data.commits
    .filter((row) => row.day === day)
    .reduce((sum, row) => sum + (Number(row.commits) || 0), 0);
  return { day, sessions: sessionsBetween(data.sessions, day, day), commits };
}

/**
 * The last `days` local days: today and the `days - 1` before it.
 *
 * Not the ISO week: this is a rolling window, and the Overview chart's ISO weeks are a
 * different question asked of the same view. Not quite `prudence usage --last 7d` either
 * when `days` is 7, which counts back 168 hours from this moment in UTC: a view of local
 * days cannot draw a line through the middle of one, so this starts at local midnight and
 * the two can differ by the replies of part of one day.
 *
 * Tokens are sums of one column of `app_usage_by_bucket_day`, and hours of one column of
 * `app_activity_by_day`, because active time belongs to a session and one session's
 * replies sit in several buckets. A bucket this build does not know stays in the total
 * and in no share (`design/buckets.js`).
 *
 * The panel's range block (`ui/panel.js`) asks this for each of its four choices; `days`
 * is 1 for "Today", which is one local day and not a window at all.
 */
export function daysWindow(data, days, now = new Date()) {
  const end = localDay(now);
  const start = days <= 1 ? end : daysBefore(end, days - 1);
  const byBucket = emptyMix();
  let total = 0;
  let minutes = 0;

  for (const row of data.usage) {
    const day = String(row.day);
    if (day < start || day > end) continue;
    const tokens = Number(row.total_tokens) || 0;
    const bucket = known(String(row.bucket));
    if (bucket) byBucket[bucket] += tokens;
    total += tokens;
  }
  for (const row of data.activity ?? []) {
    const day = String(row.day);
    if (day < start || day > end) continue;
    minutes += Number(row.active_minutes) || 0;
  }

  return {
    start,
    end,
    byBucket,
    total,
    hours: minutes / 60,
    sessions: sessionsBetween(data.sessions, start, end),
  };
}

/** The seven-day case of `daysWindow`, kept under its own name: it is what "Last 7 days"
 *  always meant here before the panel's range choice existed, and it is still the
 *  default the picker opens on. */
export function lastSevenDays(data, now = new Date()) {
  return daysWindow(data, 7, now);
}

/**
 * The seven days' shares, in the fixed bucket order, leaving out what measured nothing.
 * Each share is a ratio of two sums of the same column, which is the widest arithmetic
 * this layer is allowed.
 */
export function bucketShares(week) {
  if (!week.total) return [];
  return BUCKETS.filter((bucket) => week.byBucket[bucket] > 0).map((bucket) => ({
    bucket,
    tokens: week.byBucket[bucket],
    share: week.byBucket[bucket] / week.total,
  }));
}
