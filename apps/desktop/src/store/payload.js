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

import { emptyBuckets, known } from "../design/purposes.js";

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
    usage: rowsOf(source.usage),
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
 * Never a sum of `app_usage_by_purpose_day.sessions`: that column is per purpose per
 * day, so summing it counts one session once for every day and purpose it touched.
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
 * The last seven local days, which is `prudence usage --last 7d`'s window.
 *
 * Not the ISO week: the dropdown is a rolling seven days, and the Overview chart's ISO
 * weeks are a different question asked of the same view.
 *
 * Every figure here is a sum of one view column. An unrecognised purpose folds into
 * `unknown` (`design/purposes.js`) rather than being dropped, so the shares still sum to
 * a hundred when the engine grows a label this build has not heard of.
 */
export function lastSevenDays(data, now = new Date()) {
  const end = localDay(now);
  const start = daysBefore(end, 6);
  const byPurpose = emptyBuckets();
  let total = 0;
  let minutes = 0;

  for (const row of data.usage) {
    const day = String(row.day);
    if (day < start || day > end) continue;
    const tokens = Number(row.total_tokens) || 0;
    byPurpose[known(String(row.purpose))] += tokens;
    total += tokens;
    minutes += Number(row.active_minutes) || 0;
  }

  return {
    start,
    end,
    byPurpose,
    total,
    hours: minutes / 60,
    sessions: sessionsBetween(data.sessions, start, end),
  };
}

/**
 * The week's shares, in the fixed purpose order, leaving out what measured nothing.
 * Each share is a ratio of two sums of the same column, which is the widest arithmetic
 * this layer is allowed.
 */
export function purposeShares(week) {
  if (!week.total) return [];
  return Object.entries(week.byPurpose)
    .filter(([, tokens]) => tokens > 0)
    .map(([purpose, tokens]) => ({ purpose, tokens, share: tokens / week.total }))
    .sort((a, b) => {
      const order = Object.keys(week.byPurpose);
      return order.indexOf(a.purpose) - order.indexOf(b.purpose);
    });
}
