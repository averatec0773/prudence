/* The purposes, in the one order every surface uses.
 *
 * The engine's own list is `PURPOSES` in `src/prudence/facts/purpose.py`, and it is the
 * source: these are its labels, and `test/purposes.test.mjs` reads that file and asserts
 * the two agree. Before this module the list existed in four places with no tie between
 * them, and the three that rendered it disagreed about what to do with a label they did
 * not recognise.
 *
 * **The order is fixed and is never sorted by size.** A chart whose colours move is a
 * chart two screenshots taken a week apart cannot be compared across.
 */

/** @typedef {"development"|"research"|"debugging"|"conversation"|"mixed"|"unknown"} Purpose */

/** @type {readonly Purpose[]} */
export const PURPOSES = Object.freeze([
  "development",
  "research",
  "debugging",
  "conversation",
  "mixed",
  "unknown",
]);

/**
 * What a purpose this build has never heard of becomes.
 *
 * One answer, in one place, because the three call sites used to give three. It folds
 * into `unknown`, which the interface shows as "other" and draws in grey. It is never
 * dropped: a token that went somewhere has to appear in the total, or the shares stop
 * summing to a hundred and nothing says why. It is never given a colour of its own
 * either, because a colour the reader has no legend for is noise.
 *
 * @param {string} key
 * @returns {Purpose}
 */
export function known(key) {
  return /** @type {Purpose} */ (PURPOSES.includes(/** @type {Purpose} */ (key)) ? key : "unknown");
}

/** A zeroed bucket with every purpose present, so a sum never has to test for absence. */
export function emptyBuckets() {
  /** @type {Record<string, number>} */
  const out = {};
  for (const purpose of PURPOSES) out[purpose] = 0;
  return out;
}
