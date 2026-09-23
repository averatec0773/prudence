/* The shell's payload, as the pages read it.
 *
 * These are the two questions the panel asks of the store, and the one trap the audit
 * found waiting for the review screen.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import {
  daysWindow,
  lastSevenDays,
  localDay,
  bucketShares,
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
   `app_usage_by_bucket_day.sessions`, which is per bucket per day. */
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

/* The seven days the panel shows: tokens from the bucket view, summed per bucket over the
   seven local days that end today, and hours from the activity view. The purpose view
   carried both until contract 4; the bucket view carries no time, because active time
   belongs to a session and one session's replies sit in several buckets. */
test("the last seven days are the bucket view's tokens and the activity view's hours", () => {
  const now = new Date(2026, 8, 21, 10, 0, 0);
  const data = readPayload({
    usage: {
      columns: ["day", "project", "bucket", "total_tokens", "heuristic_tokens"],
      rows: [
        ["2026-09-21", "a", "change", 400, 0],
        ["2026-09-20", "a", "run", 330, 30],
        ["2026-09-15", "b", "read", 200, 0],
        ["2026-09-15", "b", "talk", 70, 0],
        // Seven days back is 15 September, so this one is outside the window.
        ["2026-09-14", "a", "change", 9999, 0],
      ],
    },
    activity: {
      columns: ["day", "project", "active_minutes", "sessions", "measured_sessions"],
      rows: [
        ["2026-09-21", "a", 90, 1, 1],
        ["2026-09-15", "b", 30, 1, 1],
        ["2026-09-14", "a", 600, 1, 1],
      ],
    },
    sessions: [],
  });
  const week = lastSevenDays(data, now);
  assert.equal(week.start, "2026-09-15");
  assert.equal(week.total, 1000);
  assert.deepEqual(week.byBucket, { change: 400, run: 330, read: 200, talk: 70 });
  assert.equal(week.hours, 2, "the hours are the activity view's, over the same seven days");
  assert.deepEqual(
    bucketShares(week).map((part) => [part.bucket, part.share]),
    [
      ["change", 0.4],
      ["run", 0.33],
      ["read", 0.2],
      ["talk", 0.07],
    ]
  );
});

/* A bucket this build has not heard of stays in the total and is drawn in no colour, so
   the four shares fall visibly short of a hundred rather than absorbing it. */
test("a bucket this build does not know stays in the total and in no share", () => {
  const now = new Date(2026, 8, 21, 10, 0, 0);
  const data = readPayload({
    usage: {
      columns: ["day", "bucket", "total_tokens"],
      rows: [
        ["2026-09-21", "change", 800],
        ["2026-09-21", "something_new", 200],
      ],
    },
    sessions: [],
  });
  const week = lastSevenDays(data, now);
  assert.equal(week.total, 1000);
  assert.deepEqual(
    bucketShares(week).map((part) => [part.bucket, part.share]),
    [["change", 0.8]]
  );
});

test("a week with nothing measured has no shares rather than shares of zero", () => {
  const data = readPayload({ usage: { columns: ["day"], rows: [] }, sessions: [] });
  const week = lastSevenDays(data, new Date(2026, 8, 21));
  assert.equal(week.total, 0);
  assert.equal(week.hours, 0);
  assert.deepEqual(bucketShares(week), []);
});

/* `daysWindow` generalises `lastSevenDays`: the panel's range choice asks it for Today
   (one local day) and for 30 and 90 local days too, on the same rule. */
test("lastSevenDays is daysWindow's seven-day case", () => {
  const now = new Date(2026, 8, 21, 10, 0, 0);
  const data = readPayload({
    usage: {
      columns: ["day", "bucket", "total_tokens"],
      rows: [
        ["2026-09-21", "change", 400],
        ["2026-09-15", "read", 200],
      ],
    },
    sessions: [],
  });
  assert.deepEqual(lastSevenDays(data, now), daysWindow(data, 7, now));
});

/* "Today" is one local day, not a six-day-wide window collapsed to a point: the row from
   yesterday must not leak in. */
test("a one-day window is today alone", () => {
  const now = new Date(2026, 8, 21, 10, 0, 0);
  const data = readPayload({
    usage: {
      columns: ["day", "bucket", "total_tokens"],
      rows: [
        ["2026-09-21", "change", 400],
        ["2026-09-20", "run", 9999],
      ],
    },
    sessions: [],
  });
  const day = daysWindow(data, 1, now);
  assert.equal(day.start, "2026-09-21");
  assert.equal(day.end, "2026-09-21");
  assert.equal(day.total, 400);
});

/* The 30-day and 90-day cases the panel's picker offers, over the same fixture shape as
   the seven-day test above: local days summed by the bucket view, local days summed by
   the activity view for hours, sessions counted as rows in the same window. */
test("the 30-day and 90-day windows sum the same way the seven-day one always did", () => {
  const now = new Date(2026, 8, 21, 10, 0, 0);
  const data = readPayload({
    usage: {
      columns: ["day", "bucket", "total_tokens"],
      rows: [
        ["2026-09-21", "change", 400],
        // 30 days back from 21 September is 23 August; 90 days back is 24 June.
        ["2026-08-25", "run", 300],
        ["2026-07-01", "read", 200],
        ["2026-06-01", "talk", 9999], // outside even the 90-day window
      ],
    },
    activity: {
      columns: ["day", "active_minutes"],
      rows: [
        ["2026-09-21", 60],
        ["2026-08-25", 30],
      ],
    },
    sessions: [],
  });

  const thirty = daysWindow(data, 30, now);
  assert.equal(thirty.start, "2026-08-23");
  assert.equal(thirty.total, 700);
  assert.deepEqual(thirty.byBucket, { change: 400, run: 300, read: 0, talk: 0 });
  assert.equal(thirty.hours, 1.5);

  const ninety = daysWindow(data, 90, now);
  assert.equal(ninety.start, "2026-06-24");
  assert.equal(ninety.total, 900);
  assert.deepEqual(ninety.byBucket, { change: 400, run: 300, read: 200, talk: 0 });
});
