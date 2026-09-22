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

/* --- the engine -----------------------------------------------------------------------
 *
 * The page cannot look at a filesystem and cannot start a process, so all four of these
 * are questions for the shell. `src-tauri/src/engine.rs` holds the search order, the
 * verification and the one-run-at-a-time rule.
 */

/** Where the `prudence` executable is and what version it is, or why there is none.
 *  Slow the first time: it may run a login shell. */
export function engineStatus() {
  return core().invoke("engine_status");
}

/** Run `ingest` or `review`. The promise settles when the engine exits, which is how the
 *  page knows a run is still going; `force` is the review's `--force`. */
export function runEngine(action, force) {
  return core().invoke("engine_run", { action: String(action), force: Boolean(force) });
}

/** The user picks the executable. The shell opens the picker, verifies what came back
 *  and remembers it only if it is an engine. */
export function chooseEngine() {
  return core().invoke("engine_choose");
}

/** Forget the chosen path, which puts the search back in charge. */
export function forgetEngine() {
  return core().invoke("engine_forget");
}

/** Install `prudence-core` with uv, or update it. One boolean: every word of both command
 *  lines is a constant in `src-tauri/src/installer.rs`. */
export function installEngine(upgrade) {
  return core().invoke("engine_install", { upgrade: Boolean(upgrade) });
}

/** Every repository the engine found, and which of them it records. `prudence init
 *  --scan --json`, decoded in `src-tauri/src/repositories.rs`. */
export function engineRepositories() {
  return core().invoke("engine_repositories");
}

/** Record one repository at `off`, `metadata-only` or `full`, and answer with the whole
 *  scan as it is afterwards. The key is the scan's own `repoKey`: the engine refuses a
 *  path. */
export function setRepositoryLevel(key, level) {
  return core().invoke("engine_repository_level", { key: String(key), level: String(level) });
}

/** Whether a review is ready, with the engine's own sentence when it is. Null where the
 *  engine does not answer the question. */
export function engineReadiness() {
  return core().invoke("engine_readiness");
}

/* --- the model settings ---------------------------------------------------------------
 *
 * The app never calls a model. These read what `prudence config model` prints and set the
 * one field the Model tab offers, which is the language the engine writes its optional
 * prose in.
 */

export function modelSettings() {
  return core().invoke("model_read");
}

/** One of `system`, `en` or `zh-Hans`; the shell refuses anything else before it spawns. */
export function setModelLanguage(language) {
  return core().invoke("model_set_language", { language: String(language) });
}

/* --- the app's own settings -----------------------------------------------------------
 *
 * Each of these answers with the whole settings block rather than with nothing, so the
 * page draws what is in force instead of what it asked for. Open at login in particular
 * can refuse, and a control that ticks itself on a refusal is a control that lies.
 */

export function settings() {
  return core().invoke("settings_read");
}

export function setLanguage(language) {
  return core().invoke("settings_language", { language: String(language) });
}

export function setAppearance(appearance) {
  return core().invoke("settings_appearance", { appearance: String(appearance) });
}

/** How often the shell runs an ingest on its own, in minutes. Zero is off. */
export function setTimedIngest(minutes) {
  return core().invoke("settings_timed_ingest", { minutes: Number(minutes) });
}

export function setOpenAtLogin(enabled) {
  return core().invoke("settings_open_at_login", { enabled: Boolean(enabled) });
}

/** Open one of the About tab's links in the system browser, **by name**: the shell owns
 *  the addresses, so no URL crosses this bridge and nothing the page invents is opened. */
export function openLink(name) {
  return core().invoke("open_link", { name: String(name) });
}

/**
 * The shell watches the store and says when an ingest has landed. The payload is
 * deliberately empty: the page re-reads through `readStore`, so there is one way to get
 * the store's contents and not two.
 *
 * @param {() => void} handler
 * @returns {Promise<() => void>} a function that stops listening
 */
export function onStoreChanged(handler) {
  const tauri = /** @type {any} */ (globalThis).__TAURI__;
  if (!tauri?.event) return Promise.resolve(() => {});
  return tauri.event.listen("store-changed", () => handler());
}

/**
 * A setting changed, wherever it was changed from. Empty payload, on the same rule as
 * `onStoreChanged`: there is one way to get the settings and it is `info()`.
 *
 * Both pages listen, which is the point: the panel has no settings screen of its own and
 * still has to follow a language chosen in the window.
 *
 * @param {() => void} handler
 * @returns {Promise<() => void>}
 */
export function onSettingsChanged(handler) {
  const tauri = /** @type {any} */ (globalThis).__TAURI__;
  if (!tauri?.event) return Promise.resolve(() => {});
  return tauri.event.listen("settings-changed", () => handler());
}

/**
 * What a run is doing, while it is still doing it. One event per line the engine writes
 * on its standard error under `--progress`.
 *
 * It carries its payload for the same reason the install's does: a progress line is true
 * for a moment, and asking for it again would mean asking a run that has moved on. Both
 * pages listen, because a run started in one surface can be watched from the other and a
 * timed ingest belongs to neither.
 *
 * @param {(progress: any) => void} handler
 * @returns {Promise<() => void>}
 */
export function onEngineProgress(handler) {
  const tauri = /** @type {any} */ (globalThis).__TAURI__;
  if (!tauri?.event) return Promise.resolve(() => {});
  return tauri.event.listen("engine-progress", (event) => {
    const payload = /** @type {any} */ (event)?.payload;
    if (payload) handler(payload);
  });
}

/**
 * The lines uv is printing, while it is still printing them. Unlike the two above, this
 * one carries its payload: the lines are the whole point, and asking for them again would
 * mean asking a process that has already moved on.
 *
 * @param {(lines: string[]) => void} handler
 * @returns {Promise<() => void>}
 */
export function onInstallProgress(handler) {
  const tauri = /** @type {any} */ (globalThis).__TAURI__;
  if (!tauri?.event) return Promise.resolve(() => {});
  return tauri.event.listen("engine-install", (event) => {
    const lines = /** @type {any} */ (event)?.payload?.lines;
    handler(Array.isArray(lines) ? lines.map(String) : []);
  });
}
