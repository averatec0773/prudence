/* When the engine is asked whether a review is ready, and the answer it last gave.
 *
 * ## The loop this exists to stop
 *
 * Asking is a **subprocess**: `prudence status --json`. A surface that asks on every draw
 * asks on every store change, because the store watcher redraws every page when the store
 * moves. That closes a circle, and it closed on 2026-09-22 against a copy of the founder's
 * store: the engine opens the store read-write, SQLite checkpoints the write-ahead log
 * when the last connection closes, the checkpoint changes the length and the modification
 * time of `prudence.db` and `prudence.db-wal`, and those two files are exactly what
 * `watcher.rs` fingerprints. One ask, one announcement, one redraw, one ask. The app ran
 * `prudence status` 270 times in three minutes with nothing else happening at all.
 *
 * ## The rule
 *
 * The answer is a function of what the engine has recorded, so it is remembered against
 * the store's own evidence of that: the last ingest's timestamp and the newest review's
 * id. A redraw that carries the same two is a redraw of the same store, and the remembered
 * answer is handed back without asking anything. An ingest or a review moves one of them
 * and the next draw asks again, which is what "it follows the store" means.
 *
 * A failure is not remembered: the memo is dropped so the next draw tries again, and the
 * rejection still reaches the caller rather than being swallowed here.
 */

/** The store the remembered answer was taken against. */
let at = /** @type {string | null} */ (null);
/** The answer, or the promise of one still in flight. */
let asked = /** @type {Promise<any> | null} */ (null);

/**
 * The store's own evidence that anything a review depends on has changed.
 *
 * Not a fingerprint of the file: the file moves when the engine merely reads it, which is
 * the whole defect above. These are two values the engine writes.
 *
 * @param {any} data the payload from `store/payload.js`
 * @returns {string}
 */
export function storeStamp(data) {
  const ingest = data?.status?.last_ingest_at ?? "";
  const review = data?.reviews?.[0]?.id ?? "";
  return `${ingest}|${review}`;
}

/**
 * The engine's readiness answer for this store, asking for it at most once.
 *
 * @param {any} data the payload the surface is drawing
 * @param {() => Promise<any>} ask what the surface's port does to reach the engine
 * @returns {Promise<any>}
 */
export function readiness(data, ask) {
  const stamp = storeStamp(data);
  if (asked && at === stamp) return asked;
  at = stamp;
  const answer = Promise.resolve(ask());
  asked = answer;
  answer.catch(() => {
    // Only if nothing else has asked since: a later draw's answer is not this one's to
    // throw away.
    if (asked === answer) {
      at = null;
      asked = null;
    }
  });
  return answer;
}

/** Forget what was asked. For a test, and for nothing else: the app has one store. */
export function forget() {
  at = null;
  asked = null;
}
