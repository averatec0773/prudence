/* The one door between the page and the shell.
 *
 * Every Tauri call in this frontend is in this file. Nothing under `design/`, `text/`,
 * `store/` or `ui/` knows what a Tauri is, and `test/bridge.test.mjs` asserts it.
 *
 * That is load bearing, not tidiness. If the webview under this frontend ever has to
 * change, the shell and this one file are rewritten and everything else moves unchanged.
 *
 * **The commands and their argument names must match `src-tauri/src/lib.rs` exactly.**
 * Renaming a Rust parameter breaks the page at runtime with no error on either side, so
 * `test/bridge.test.mjs` parses both files and compares the two sets.
 *
 * There is one channel in the other direction and it is not here: with the `harness`
 * feature built in, the shell drives `window.eval` against `ui/stress.js`. It is a test
 * hook, it is absent from a release build, and it is registered in `DESIGN.md`.
 */

function core() {
  const tauri = /** @type {any} */ (globalThis).__TAURI__;
  if (!tauri?.core) throw new Error("no shell: this page is running outside its host");
  return tauri.core;
}

/** Whether there is a shell at all. Opening a page in a browser is a real thing to do
 *  while working on layout, and it should say so rather than throw. */
export function attached() {
  return Boolean(/** @type {any} */ (globalThis).__TAURI__?.core);
}

/** One payload: a status row, and the `app_*` views the pages read. */
export function readStore() {
  return core().invoke("store_read");
}

/** What the shell is and what it managed to do. */
export function info() {
  return core().invoke("shell_info");
}

/** A line on the shell's standard error. The page has no console anybody can read while
 *  the app is running from a menu bar. */
export function log(line) {
  return core().invoke("page_log", { line: String(line) });
}

/** A popover is as tall as what is in it. The page measures and reports; the shell owns
 *  the window, and a resized panel has to be anchored under its status item again. */
export function fitPanel(width, height) {
  return core().invoke("panel_fit", { width, height });
}

export function hidePanel() {
  return core().invoke("panel_hide");
}

export function openWindow() {
  return core().invoke("window_open");
}

export function closeWindow() {
  return core().invoke("window_close");
}

/** Which section the window is on, so the next launch opens on it. The shell drops a
 *  value this build no longer has rather than forcing it. */
export function setSection(section) {
  return core().invoke("section_set", { section: String(section) });
}

export function quit() {
  return core().invoke("app_quit");
}
