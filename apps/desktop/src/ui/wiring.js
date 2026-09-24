/* The window's wiring: the one file under `src/ui/` that calls the bridge.
 *
 * A screen may not talk to the shell (`DESIGN.md`, "the page contract"), and several pieces
 * of this window need to: the toolbar's two actions and the status row, which follow what
 * the engine is doing; the engine block, which finds and installs the executable; the
 * Repositories screen, which asks the engine what it records; and the Settings screen's
 * General, Model and About tabs, which write settings through the CLI and the app's own
 * state. Each declares a **port** and this file fills it in, so the rule stays one
 * sentence: everything under `src/ui/` reaches the shell through here.
 *
 * Called once per page, from `window.html`, before the first draw.
 */

import * as Bridge from "../bridge.js";
import { ACTIVITY, follow, runReport } from "./activity.js";
import { RUNS } from "./engine-runs.js";
import { ENGINE } from "./engine-section.js";
import { REPOSITORIES } from "./repositories.js";
import { REVIEW_NOW } from "./review.js";
import { SETTINGS } from "./settings.js";
import { SOURCES } from "./sources.js";

/**
 * A write that failed, on the shell's standard error.
 *
 * The Settings screen cannot report one itself: a screen may not call the bridge, and a
 * menu bar app has no console anybody is watching. The shell answers `Ok` with what is
 * actually in force even when the system refuses a login item, so a rejection here means
 * the page sent something the shell would not take, which is a defect in this file rather
 * than something to translate. The promise still settles, so the caller may ignore it.
 *
 * @template T
 * @param {string} what
 * @param {Promise<T>} promise
 * @returns {Promise<T|undefined>}
 */
function reported(what, promise) {
  return promise.catch((error) => {
    Bridge.log(`settings: ${what} was refused: ${error instanceof Error ? error.message : error}`);
    return undefined;
  });
}

export function wireWindow() {
  ENGINE.port = {
    status: () => Bridge.engineStatus(),
    choose: () => Bridge.chooseEngine(),
    forget: () => Bridge.forgetEngine(),
    install: (upgrade) => Bridge.installEngine(upgrade),
    onInstallProgress: (handler) => Bridge.onInstallProgress(handler),
    link: (name) => Bridge.openLink(name),
  };

  // The toolbar, the status row and the report. The three that only listen settle rather
  // than reject, so `activity.js` has nothing to swallow: a failure is a line on the
  // shell's standard error and the page stays as it was.
  ACTIVITY.port = {
    read: () => reported("activity", Bridge.engineActivity()),
    onActivity: (handler) =>
      reported("activity events", Bridge.onEngineActivity(handler)).then((off) => off ?? (() => {})),
    onProgress: (handler) =>
      reported("progress events", Bridge.onEngineProgress(handler)).then((off) => off ?? (() => {})),
    run: (action, force) => Bridge.runEngine(action, force),
    runs: (count) => reported("run log", Bridge.engineRuns(count)),
  };

  // The Engine tab's run records and diagnosis. `runs` and `diagnose` reject, because the
  // cards say a failure themselves; `reveal` only opens a folder, and a refusal of that
  // is a line on the shell's standard error.
  RUNS.port = {
    runs: (count) => Bridge.engineRuns(count),
    diagnose: () => Bridge.diagnose(),
    reveal: (name) => reported("reveal", Bridge.reveal(name)),
  };

  REPOSITORIES.port = {
    scan: () => Bridge.engineRepositories(),
    level: (key, level) => Bridge.setRepositoryLevel(key, level),
  };

  SOURCES.port = {
    read: () => Bridge.engineSources(),
    add: (kind, name, home) => Bridge.addSource(kind, name, home),
    set: (id, enabled, name, home) => Bridge.setSource(id, enabled, name, home),
  };

  SETTINGS.port = {
    read: () => Bridge.settings(),
    language: (code) => reported("language", Bridge.setLanguage(code)),
    appearance: (code) => reported("appearance", Bridge.setAppearance(code)),
    openAtLogin: (on) => reported("open at login", Bridge.setOpenAtLogin(on)),
    timedIngest: (minutes) => reported("timed ingest", Bridge.setTimedIngest(minutes)),
    model: () => Bridge.modelSettings(),
    modelLanguage: (code) => reported("model language", Bridge.setModelLanguage(code)),
    link: (name) => reported("link", Bridge.openLink(name)),
  };

  // The line above the review that says whether writing one would produce anything.
  // `review.js` exports the seam and refuses to invent it, because a screen may not call
  // the bridge. Reported rather than thrown: an engine that cannot be asked leaves the
  // line off the screen, and the reason goes where a screen's failures have to go.
  REVIEW_NOW.readiness = () => reported("readiness", Bridge.engineReadiness());

  document.body.appendChild(runReport());

  // Only with a shell behind the page: opened in a browser while layout is worked on,
  // there is no engine to follow and the toolbar says so when it is pressed.
  if (Bridge.attached()) follow();
}
