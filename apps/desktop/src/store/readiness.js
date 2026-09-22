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
 * The answer is remembered against the store's own evidence of a change, which is
 * `store/asked.js`: that file holds the rule, the stamp and the measurements, and was
 * generalised out of this one when the Settings screen turned out to be asking the engine
 * two more questions the same way. This file is the readiness question's own memo and
 * nothing else.
 */

import { memo, storeStamp } from "./asked.js";

const answer = memo();

/**
 * The engine's readiness answer for this store, asking for it at most once.
 *
 * @param {any} data the payload the surface is drawing
 * @param {() => Promise<any>} ask what the surface's port does to reach the engine
 * @returns {Promise<any>}
 */
export function readiness(data, ask) {
  return answer.ask(data, ask);
}

/** Forget what was asked. For a test, and for nothing else: the app has one store. */
export function forget() {
  answer.forget();
}

export { storeStamp };
