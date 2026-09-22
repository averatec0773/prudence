/* What the Observations screen reads: the rows of `app_observation`, scoped and grouped.
 *
 * **Nothing here computes a statistic.** `with_value` and `without_value` are medians the
 * engine took (`src/prudence/store/observations.py`), and `coverage`, `with_n`,
 * `without_n`, `fact_commits` and `inferred_commits` are columns. This module filters,
 * groups and orders them, which is all a reader of a view is allowed to do.
 *
 * The one piece of arithmetic is `gap`, the distance between the two medians, and it is
 * here **only to order the list**. A sort order is a statement about the page, not about
 * the world, so it is allowed; a "lift", an "effect size" or anything else derived from
 * the two medians would not be.
 *
 * **It is never shown.** The distance between the medians is a quantity the engine owns:
 * `store/observations.py` has `MIN_GAP = 0.10` and takes it on the unrounded values as
 * the floor an observation must clear to exist. A second one printed from the two rounded
 * shares would be a second definition of one number, and they disagree (with 0.9051
 * against 0.8050 the engine has 10.01 points, the rounded shares give 11). Both medians
 * are on the card and the engine's own sentence states them; if the distance itself
 * should be on screen, the engine exposes it as a column.
 */

/** The repository key of a row pooled over every project. */
export const POOLED_KEY = "*";

/**
 * Whether a row is pooled over every project rather than about one.
 *
 * Both the flag and the key are checked. They say the same thing, and a store whose
 * `pooled` column disagreed with its `repo_key` should still read right rather than file
 * a whole-store row under a project name.
 *
 * @param {Record<string, any>} row
 */
export function isPooled(row) {
  return Number(row.pooled) === 1 || row.repo_key === POOLED_KEY;
}

/** The project a row is about, or null when it is about all of them. */
export function projectOf(row) {
  if (isPooled(row)) return null;
  const name = row.project ?? row.repo_key;
  return name === null || name === undefined ? null : String(name);
}

/**
 * A column that should hold a share, as a number, or null when it holds nothing.
 *
 * Not `Number(value)`: that turns null into 0, and a median the engine never wrote is
 * not a median of zero. The screen prints the difference (a dash, not "0%") and the
 * order below puts such a row last rather than ranking it as if it had been measured.
 *
 * @param {unknown} value
 * @returns {number|null}
 */
export function shareOf(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

/**
 * The distance between the two medians, as a share. **An ordering key, not a figure.**
 *
 * Null when either side is missing, so a malformed row sorts last instead of poisoning
 * the comparison with a NaN.
 *
 * @param {Record<string, any>} row
 * @returns {number|null}
 */
export function gap(row) {
  const a = shareOf(row.with_value);
  const b = shareOf(row.without_value);
  if (a === null || b === null) return null;
  return Math.abs(a - b);
}

/**
 * The rows the chosen scope shows.
 *
 * **A pooled row is always in.** The engine computes one only for a behaviour no single
 * repository had the sessions to answer, so a project filter that dropped it would hide
 * the only answer there is. It still says "across your projects" on its own card, because
 * it is not a finding about the project that was picked.
 *
 * @param {Record<string, any>[]} rows
 * @param {string|null|undefined} project
 */
export function forScope(rows, project) {
  if (project === null || project === undefined) return [...rows];
  return rows.filter((row) => projectOf(row) === project || isPooled(row));
}

/**
 * One card's worth of rows: one behaviour, one scope, and the one or two outcomes
 * measured over the same split of the same sessions.
 *
 * Grouped on `repo_key|fact` rather than on the fact alone, so that two pooled rows about
 * one behaviour meet and a project's own row never joins a pooled one.
 *
 * **The order is presentation.** Widest gap first, because that is the card a reader is
 * looking for; a group's place is its *largest* gap, since a card is as interesting as
 * its most interesting bar. Ties break on the group key so that two runs over the same
 * store draw the same page.
 *
 * @param {Record<string, any>[]} rows
 */
export function groupsOf(rows) {
  /** @type {Map<string, Record<string, any>[]>} */
  const byKey = new Map();
  for (const row of rows) {
    const key = `${row.repo_key ?? ""}|${row.fact ?? ""}`;
    const found = byKey.get(key);
    if (found) found.push(row);
    else byKey.set(key, [row]);
  }

  return [...byKey.entries()]
    .map(([key, list]) => {
      const ordered = [...list].sort(
        (a, b) =>
          (gap(b) ?? 0) - (gap(a) ?? 0) ||
          String(a.outcome ?? "").localeCompare(String(b.outcome ?? ""))
      );
      const first = ordered[0];
      return {
        key,
        fact: String(first.fact ?? ""),
        pooled: isPooled(first),
        project: projectOf(first),
        rows: ordered,
        gap: Math.max(...ordered.map((row) => gap(row) ?? 0)),
      };
    })
    .sort((a, b) => b.gap - a.gap || a.key.localeCompare(b.key));
}

/**
 * The whole screen's data: the rows in scope, the pooled cards, and one block of cards
 * per project.
 *
 * Projects come out **alphabetically**, not by their widest gap. Ordering the projects by
 * their observations would rank the projects, and a ranking is a score by another name
 * (principle 2). Inside a project the cards are ordered, because there the gap is about
 * one behaviour against another in the same work.
 *
 * @param {{ observations?: Record<string, any>[] }} data
 * @param {{ project?: string|null }} [scope]
 */
export function scoped(data, { project = null } = {}) {
  const rows = forScope(data?.observations ?? [], project);
  const own = rows.filter((row) => !isPooled(row));
  const names = [...new Set(own.map((row) => projectOf(row) ?? ""))].sort((a, b) =>
    a.localeCompare(b)
  );
  return {
    rows,
    pooled: groupsOf(rows.filter(isPooled)),
    projects: names.map((name) => ({
      project: name,
      groups: groupsOf(own.filter((row) => (projectOf(row) ?? "") === name)),
    })),
  };
}
