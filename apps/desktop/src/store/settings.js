/* What the store says is recorded, for the Settings screen.
 *
 * One question, and the reason it needs a reader at all: **which repositories are on
 * record, at which capture level, and how many sessions that is.** The capture level is
 * a column of `app_session_list`, so the store already knows it; the engine's
 * `config.toml` is the consent record, but the app cannot read a TOML file and has no
 * bridge command that would, so what the store recorded is the honest answer and is in
 * some ways the better one: it is what happened rather than what is set.
 *
 * **The rule this file keeps** (`DESIGN.md`, "the app owns no numbers"): a session is
 * one row of `app_session_list`, so the only arithmetic here is counting rows of one
 * view into buckets. It is never a sum of `app_usage_by_purpose_day.sessions`, which is
 * per purpose per day and counts one session once for every day and purpose it touched;
 * `store/payload.js` carries the same warning for the same reason. The groups add up to
 * `app_status.sessions`, and `test/settings.test.mjs` asserts that against the fixture.
 */

/**
 * @typedef {{ project: string, level: string, sessions: number }} Bucket
 */

/**
 * Every project on record, split by the level its sessions were recorded at.
 *
 * A project appears once per level, not once: a repository whose level was changed has
 * sessions at both, and folding them into one row would print a level the older half of
 * the work was never recorded at.
 *
 * A row with no project or no level keeps an empty string rather than being dropped. The
 * engine reports no such session today (`prudence status` prints "sessions with no
 * repository: 0"), and a session the app silently left out of a screen whose subject is
 * what was recorded would be the worst possible defect on it.
 *
 * @param {{ sessions: Record<string, any>[] }} data the payload from `store/payload.js`
 * @returns {{ rows: Bucket[], sessions: number }}
 */
export function recorded(data) {
  /** @type {Map<string, Bucket>} */
  const buckets = new Map();
  for (const row of data.sessions ?? []) {
    const project = text(row.project);
    const level = text(row.capture_level);
    // A tab cannot appear in either value, so it separates the two halves of the key
    // without a project called "a" and a level called "b" colliding with the reverse.
    const key = `${project}\t${level}`;
    const found = buckets.get(key);
    if (found) found.sessions += 1;
    else buckets.set(key, { project, level, sessions: 1 });
  }

  const rows = [...buckets.values()].sort(
    (a, b) => a.project.localeCompare(b.project) || a.level.localeCompare(b.level)
  );
  return { rows, sessions: rows.reduce((total, row) => total + row.sessions, 0) };
}

function text(value) {
  return value === null || value === undefined ? "" : String(value);
}
