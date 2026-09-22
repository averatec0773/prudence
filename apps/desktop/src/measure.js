/* Timing the page, for a harness run and for nothing else.
 *
 * Every question asked of this app's performance used to be answered by reasoning about
 * the code, because there was nothing that could answer it with a number: a menu bar app
 * has no console anybody is watching and the one channel out of the page is the shell's
 * standard error. This is that channel, used for timings.
 *
 * **It is off unless the shell says the build carries the harness.** `boot.js` turns it on
 * from `shell_info.harness`, which is `cfg!(feature = "harness")`, so a release build calls
 * `say` and `timed` and they do nothing and report nothing. That is the same rule the
 * `Stress` object keeps, and the reason the cost of having this here is a branch.
 */

/** Where a line goes, and whether to write one at all. */
let report = /** @type {null | ((line: string) => void)} */ (null);

/**
 * Start reporting. Called once per page, as soon as the shell has answered.
 *
 * @param {(line: string) => void} log where a line goes; `bridge.js`'s `log` in the app
 */
export function reportTo(log) {
  report = log;
}

export function measuring() {
  return report !== null;
}

/** One line, prefixed so a log can be grepped for the measurements alone. */
export function say(line) {
  report?.(`[measure] ${line}`);
}

/** The clock. `performance.now()` is monotonic and sub-millisecond, unlike `Date.now`. */
export function at() {
  return globalThis.performance?.now?.() ?? Date.now();
}

/** How long since `started`, in whole milliseconds. */
export function since(started) {
  return Math.round(at() - started);
}

/**
 * Run `work` and say how long it took.
 *
 * The work runs whether or not anything is measuring, and the return value is passed
 * through, so a call site reads the same in both builds.
 *
 * @template T
 * @param {string} label
 * @param {() => T} work
 * @returns {T}
 */
export function timed(label, work) {
  if (!report) return work();
  const started = at();
  const out = work();
  say(`${label} ${since(started)} ms`);
  return out;
}

/** How many elements are under a node. The unit the DOM cost of a redraw is counted in. */
export function nodes(root) {
  return root?.querySelectorAll ? root.querySelectorAll("*").length : 0;
}
