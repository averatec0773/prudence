/* The engine's run records, read: what `src-tauri/src/runlog.rs` hands over from
 * `<data dir>/logs/runs.jsonl`, turned into the few facts the window says about them.
 *
 * Every value is the engine's own. What this file does is the arithmetic a surface may do
 * on one record: add up the counts of its warnings, pick out the checks it says failed,
 * and subtract its start from its end.
 *
 * **What counts as a warning.** Each warning's own `count`, summed, plus one per check
 * whose `ok` is false. The engine also records a failed check as a warning of kind
 * `check_failed`; that kind restates the checks and is left out of the sum, so a failed
 * check is counted once, from the checks themselves.
 */

/** The engine's name for the command a record is about: `ingest`, `review`, `init`. A
 *  record whose command starts with the executable itself is read past it. */
export function commandName(run) {
  return commandWords(run)[0] ?? "";
}

/** The command as it was typed, without the executable in front of it. */
export function commandLine(run) {
  return commandWords(run).join(" ");
}

function commandWords(run) {
  const words = Array.isArray(run?.command) ? run.command.map(String) : [];
  const first = words[0] ?? "";
  const base = first.split(/[\\/]/).pop() ?? "";
  return /^prudence(\.exe)?$/.test(base) ? words.slice(1) : words;
}

/** The checks the engine says did not hold. A check with no verdict is not one of them. */
export function failedChecks(run) {
  return (Array.isArray(run?.checks) ? run.checks : []).filter((check) => check?.ok === false);
}

/** The warnings as the engine wrote them, `check_failed` included, for the disclosure. */
export function warningsOf(run) {
  return Array.isArray(run?.warnings) ? run.warnings : [];
}

/** How many warnings the run left, counting each failed check once. See the top. */
export function warningCount(run) {
  const counted = warningsOf(run)
    .filter((warning) => warning?.kind !== "check_failed")
    .reduce((sum, warning) => sum + (Number(warning?.count) || 0), 0);
  return counted + failedChecks(run).length;
}

/** Whether the record is still open: started and never ended. Whether that means it is
 *  running or was interrupted is a question for what the shell knows is running. */
export function unended(run) {
  return run?.ended_at === null || run?.ended_at === undefined;
}

/** How long the run took in seconds, from its own two stamps, or null while it has one. */
export function seconds(run) {
  if (unended(run)) return null;
  const began = Date.parse(String(run?.started_at ?? ""));
  const ended = Date.parse(String(run?.ended_at ?? ""));
  if (Number.isNaN(began) || Number.isNaN(ended)) return null;
  return Math.max(0, (ended - began) / 1000);
}

/** The files the parse step read and the ones it skipped as unchanged, from whichever step
 *  counted them, or null for a run that parsed nothing. */
export function files(run) {
  for (const step of Array.isArray(run?.steps) ? run.steps : []) {
    const counts = step?.counts ?? {};
    if ("files_parsed" in counts || "files_skipped" in counts) {
      return {
        parsed: Number(counts.files_parsed ?? 0),
        skipped: Number(counts.files_skipped ?? 0),
      };
    }
  }
  return null;
}

/**
 * What the sidebar's status row adds about the last ingest, or null for nothing.
 *
 * `interrupted` when the newest ingest record never ended and no run is going now;
 * `warnings` with a count when it ended and left warnings or failed checks. Only ingests:
 * the row is about the last ingest, and the app's own scans and reviews write records too.
 *
 * @param {any[]} runs newest first
 * @param {boolean} running whether the shell says a run is going now
 * @returns {{ kind: "interrupted" } | { kind: "warnings", count: number } | null}
 */
export function statusNote(runs, running) {
  if (running) return null;
  const last = (Array.isArray(runs) ? runs : []).find((run) => commandName(run) === "ingest");
  if (!last) return null;
  if (unended(last)) return { kind: "interrupted" };
  const count = warningCount(last);
  return count > 0 ? { kind: "warnings", count } : null;
}
