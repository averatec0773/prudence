/* The four buckets a reply of the model lands in, in the one order every surface uses.
 *
 * The engine's own list is `BUCKETS` in `src/prudence/store/buckets.py`, and it is the
 * source: `test/buckets.test.mjs` reads that file and asserts the two agree. A reply is
 * `change` when it wrote a file, `run` when it ran a command or a tool that acts, `read`
 * when it only looked, and `talk` when it did none of those; one reply is one bucket.
 *
 * **The order is fixed and is never sorted by size.** It is the engine's precedence order,
 * which is also the order `prudence usage` prints, so a chart and the CLI list the four
 * the same way, and two screenshots a week apart stack their colours the same way.
 *
 * "Bucket" also names a day or a week on the Overview's time axis (`store/overview.js`),
 * which predates these. In code the time slot keeps that name and these four are always
 * `BUCKETS` and `byBucket`; the reader sees neither word.
 */

/** @typedef {"change"|"run"|"read"|"talk"} Bucket */

/** @type {readonly Bucket[]} */
export const BUCKETS = Object.freeze(["change", "run", "read", "talk"]);

/**
 * Whether a label is one of the four, or null for one this build has never heard of.
 *
 * There is no "other" to fold into: the engine gives every reply one of these four or
 * none, and a reply with none is `app_status.coverage_gap_tokens`, not a row. A fifth
 * would be a new bucket rule, and the test that pins this list to the engine's fails
 * first. Until then its tokens stay in a total and are drawn in no colour, so the four
 * shares visibly fall short rather than quietly absorbing it.
 *
 * @param {string} key
 * @returns {Bucket | null}
 */
export function known(key) {
  return BUCKETS.includes(/** @type {Bucket} */ (key)) ? /** @type {Bucket} */ (key) : null;
}

/** Zero for each of the four, so a sum never has to test for absence. */
export function emptyMix() {
  /** @type {Record<Bucket, number>} */
  const out = /** @type {any} */ ({});
  for (const bucket of BUCKETS) out[bucket] = 0;
  return out;
}

/** The colour a bucket is drawn in. The values are in `tokens.css`; colour is identity. */
export function bucketColour(bucket) {
  return `var(--b-${bucket})`;
}
