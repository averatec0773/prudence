/* The shell's payload, as the pages read it.
 *
 * These are the two questions the panel asks of the store, and the one trap the audit
 * found waiting for the review screen.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import {
  lastSevenDays,
  localDay,
  purposeShares,
  readPayload,
  rowsOf,
  sessionsBetween,
  today,
} from "../src/store/payload.js";

/** The shell sends wide views as `{columns, rows}` and narrow ones as objects. */
test("both payload shapes become rows", () => {
  assert.deepEqual(rowsOf({ columns: ["a", "b"], rows: [[1, 2]] }), [{ a: 1, b: 2 }]);
  assert.deepEqual(rowsOf([{ a: 1 }]), [{ a: 1 }]);
  assert.deepEqual(rowsOf(null), []);
  assert.deepEqual(rowsOf(undefined), []);
});

/* `app_review.sections` is a JSON document in a TEXT column, so it arrives as a string.
   The mockups called `.forEach` on it. */
test("a review's JSON columns are parsed once, and a broken one is null", () => {
  const payload = readPayload({
    reviews: [
      { id: 1, sections: '[{"kind":"did"}]', numbers: "{}" },
      { id: 2, sections: "not json", numbers: null },
    ],
  });
  assert.deepEqual(payload.reviews[0].sections, [{ kind: "did" }]);
  assert.deepEqual(payload.reviews[0].numbers, {});
  // Null, not an empty array: a review whose sections cannot be read is one the screen
  // has to say it cannot read, not one that looks empty.
  assert.equal(payload.reviews[1].sections, null);
  assert.equal(payload.reviews[1].numbers, null);
});

/* Sessions are rows of `app_session_list`, never a sum of
   `app_usage_by_purpose_day.sessions`, which is per purpose per day. */
test("sessions in a window are counted as rows, in local time", () => {
  // Built from local times, because the window is in local days: the engine stamps in
  // UTC and a UTC midnight is the previous local day for anyone west of Greenwich.
  const at = (y, m, d, h) => ({ started_at: new Date(y, m - 1, d, h).toISOString() });
  const sessions = [at(2026, 9, 21, 9), at(2026, 9, 15, 9), at(2026, 9, 1, 9)];

  assert.equal(sessionsBetween(sessions, "2026-09-01", "2026-09-21"), 3);
  assert.equal(sessionsBetween(sessions, "2026-09-15", "2026-09-21"), 2);
  assert.equal(sessionsBetween(sessions, "2026-09-22", "2026-09-22"), 0);
});

/* The window is inclusive of both ends, in local days. The boundary is worth its own
   test because it is where an off-by-one would live and nobody would see it. */
test("the window includes both of its own days", () => {
  const justAfterMidnight = { started_at: new Date(2026, 8, 15, 0, 1).toISOString() };
  const justBeforeMidnight = { started_at: new Date(2026, 8, 21, 23, 59).toISOString() };
  const sessions = [justAfterMidnight, justBeforeMidnight];
  assert.equal(sessionsBetween(sessions, "2026-09-15", "2026-09-21"), 2);
  assert.equal(sessionsBetween(sessions, "2026-09-16", "2026-09-21"), 1);
  assert.equal(sessionsBetween(sessions, "2026-09-15", "2026-09-20"), 1);
});

test("today is the machine's today, not the last day with a row", () => {
  const now = new Date(2026, 8, 21, 10, 0, 0);
  const data = readPayload({
    commits: { columns: ["day", "commits"], rows: [["2026-09-15", 4]] },
    sessions: [],
  });
  const answer = today(data, now);
  assert.equal(answer.day, localDay(now));
  assert.equal(answer.commits, 0, "a commit on an older day is not today's");
});

/* An unrecognised purpose folds into `unknown` and stays in the total, so the shares
   still sum to a hundred when the engine grows a label this build has not heard of. */
test("a purpose this build does not know still counts", () => {
  const now = new Date(2026, 8, 21, 10, 0, 0);
  const data = readPayload({
    usage: {
      columns: ["day", "purpose", "total_tokens", "active_minutes"],
      rows: [
        ["2026-09-21", "development", 800, 30],
        ["2026-09-21", "something_new", 200, 10],
      ],
    },
    sessions: [],
  });
  const week = lastSevenDays(data, now);
  assert.equal(week.total, 1000);
  assert.equal(week.byPurpose.unknown, 200);
  const shares = purposeShares(week);
  const sum = shares.reduce((total, part) => total + part.share, 0);
  assert.ok(Math.abs(sum - 1) < 1e-9, `the shares sum to ${sum}, not 1`);
});

test("a week with nothing measured has no shares rather than shares of zero", () => {
  const data = readPayload({ usage: { columns: ["day"], rows: [] }, sessions: [] });
  const week = lastSevenDays(data, new Date(2026, 8, 21));
  assert.equal(week.total, 0);
  assert.deepEqual(purposeShares(week), []);
});
