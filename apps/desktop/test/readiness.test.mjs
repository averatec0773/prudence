/* When the engine is asked whether a review is ready.
 *
 * ## The defect this file is the guard for
 *
 * Asking is a subprocess. The first version of the readiness line asked on every draw, and
 * every draw includes the ones the store watcher causes: the engine opens the store
 * read-write, SQLite checkpoints the write-ahead log as the last connection closes, that
 * changes the length and modification time of `prudence.db` and `prudence.db-wal`, and
 * those two files are exactly what `watcher.rs` fingerprints. Ask, announce, redraw, ask.
 * Against a copy of the founder's store the app ran `prudence status` 270 times in three
 * minutes with no ingest running at all.
 *
 * Nothing in the suite caught it, because every page test drives a fake port and no test
 * joins "a render asks the engine" to "asking the engine moves the store". So the guard is
 * not "the panel draws a line": it is **a surface may not ask the engine again for a store
 * it has already asked about**, which is a property of the decision and can be tested
 * without a watcher.
 *
 *     pnpm test
 */

import { test } from "node:test";
import assert from "node:assert/strict";

const { readiness, storeStamp, forget } = /** @type {any} */ (
  await import("../src/store/readiness.js")
);

const settled = () => new Promise(setImmediate);

function store(over = {}) {
  return {
    status: { last_ingest_at: "2026-09-22T02:45:00Z" },
    reviews: [{ id: 7 }],
    ...over,
  };
}

test("the same store is asked about once, however many times it is drawn", async () => {
  forget();
  let asks = 0;
  const ask = () => {
    asks += 1;
    return Promise.resolve({ ready: true });
  };

  const data = store();
  const answers = await Promise.all([
    readiness(data, ask),
    readiness(data, ask),
    // A fresh object with the same contents is the same store: the payload is rebuilt on
    // every draw, so identity is not the question.
    readiness(store(), ask),
  ]);
  await settled();

  assert.equal(asks, 1, `the engine was asked ${asks} times for one store`);
  for (const answer of answers) assert.deepEqual(answer, { ready: true });
});

test("an ingest or a review is a new store, and is asked about again", async () => {
  forget();
  let asks = 0;
  const ask = () => {
    asks += 1;
    return Promise.resolve({ ready: asks > 1 });
  };

  await readiness(store(), ask);
  // A later ingest.
  await readiness(store({ status: { last_ingest_at: "2026-09-22T09:10:00Z" } }), ask);
  // And a review that has just been written.
  const after = await readiness(store({ reviews: [{ id: 8 }] }), ask);

  assert.equal(asks, 3, "the answer did not follow the store");
  assert.deepEqual(after, { ready: true });
});

/* A failure is not an answer to remember: the next draw has to be able to try again. The
   rejection still reaches the caller, because a swallowed one is a line that never appears
   and never says why. */
test("a refusal is not remembered, and is not swallowed either", async () => {
  forget();
  let asks = 0;
  const ask = () => {
    asks += 1;
    return asks === 1 ? Promise.reject(new Error("notFound")) : Promise.resolve({ ready: false });
  };

  await assert.rejects(() => readiness(store(), ask), /notFound/);
  await settled();
  assert.deepEqual(await readiness(store(), ask), { ready: false });
  assert.equal(asks, 2);
});

/* The stamp is what the engine wrote, never the file: the file moves when the engine
   merely reads it, which is the whole defect above. */
test("the stamp is the store's own evidence of a change", () => {
  assert.equal(storeStamp(store()), "2026-09-22T02:45:00Z|7");
  assert.equal(storeStamp({}), "|");
  assert.equal(storeStamp(null), "|");
  assert.notEqual(storeStamp(store()), storeStamp(store({ reviews: [] })));
});
