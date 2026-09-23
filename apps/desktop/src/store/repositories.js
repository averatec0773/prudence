/* What the Repositories screen prints about each repository, from the views and nothing
 * else.
 *
 * The list itself is the engine's scan (`prudence init --scan --json`), which is not the
 * store: it is the one thing that knows about the repositories the store has never heard
 * of. The two figures beside each row are the store's, keyed by the scan's own `repoKey`,
 * which is the same `repo_key` every `app_*` view carries.
 *
 * The arithmetic is the same two moves `payload.js` allows and no others: a total is a
 * **sum of one view column** over the repository's rows, and a share is the **ratio of two
 * such sums**. All time, because the screen is about the repository and not about a window.
 */

import { emptyMix, known } from "../design/buckets.js";
import { bucketShares } from "./payload.js";

/**
 * Tokens by what each reply did, over every day the store has for this repository.
 *
 * A sum of `app_usage_by_bucket_day.total_tokens` per bucket, which is what
 * `prudence usage --project <name>` sums over a window long enough to hold everything. A
 * bucket this build does not know stays in the total and in no share, the rule the panel's
 * bar keeps.
 *
 * @param {any} data the payload
 * @param {string} repoKey
 */
export function tokensOf(data, repoKey) {
  const byBucket = emptyMix();
  let total = 0;
  for (const row of data.usage ?? []) {
    if (String(row.repo_key) !== repoKey) continue;
    const tokens = Number(row.total_tokens) || 0;
    const bucket = known(String(row.bucket));
    if (bucket) byBucket[bucket] += tokens;
    total += tokens;
  }
  return { byBucket, total, shares: bucketShares({ byBucket, total }) };
}

/**
 * What was still there thirty days on, over every week the engine has measured.
 *
 * `alive_30d` and `measured_30d` summed over the repository's rows of
 * `app_outcomes_by_week`, and their ratio: the engine's own totals, bucketed by week, and
 * a bucket can move a commit between weeks but never out of the total. Null where nothing
 * was measured, which is every repository not recorded and every one whose first thirty
 * days are not up: not measured is not "none survived".
 *
 * @param {any} data the payload
 * @param {string} repoKey
 * @returns {{ alive: number, measured: number, share: number } | null}
 */
export function aliveOf(data, repoKey) {
  let alive = 0;
  let measured = 0;
  for (const row of data.outcomes ?? []) {
    if (String(row.repo_key) !== repoKey) continue;
    alive += Number(row.alive_30d) || 0;
    measured += Number(row.measured_30d) || 0;
  }
  return measured > 0 ? { alive, measured, share: alive / measured } : null;
}

/**
 * The name the rest of the window calls this repository by, or null when the store has no
 * session from it. It is the name the project picker offers, so a row sets the same filter
 * the picker does.
 *
 * @param {any} data the payload
 * @param {string} repoKey
 * @returns {string|null}
 */
export function projectOf(data, repoKey) {
  const found = (data.projects ?? []).find((row) => String(row.key) === repoKey);
  return found ? String(found.name) : null;
}

/**
 * How many repositories are recorded and how many were found and are not, from the scan.
 * The group of sessions that belong to no repository has no path and is neither.
 *
 * @param {any[]} scan
 */
export function scanCounts(scan) {
  const listed = (Array.isArray(scan) ? scan : []).filter((row) => row.path);
  const recorded = listed.filter((row) => row.enabled).length;
  return { recorded, found: listed.length - recorded };
}
