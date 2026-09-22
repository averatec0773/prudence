/* The window's wiring: the one file under `src/ui/` that calls the bridge.
 *
 * A screen may not talk to the shell (`DESIGN.md`, "the page contract"), and two pieces of
 * this window need to: the engine block, which finds and runs the executable, and the
 * Settings screen's General, Model and About tabs, which write settings through the CLI
 * and the app's own state. Both declare a **port** and this file fills it in, so the rule
 * stays one sentence: everything under `src/ui/` reaches the shell through here.
 *
 * It was inside `engine-section.js` while the engine block was the only thing that needed
 * it. Settings arriving with four controls of its own made that the second file importing
 * the bridge, which is one more than the rule allows.
 *
 * Called once per page, from `window.html`, before the first draw.
 */

import * as Bridge from "../bridge.js";
import { ENGINE, engineActivity, run } from "./engine-section.js";
import { REVIEW_NOW } from "./review.js";
import { SETTINGS } from "./settings.js";

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
    run: (action, force) => Bridge.runEngine(action, force),
    choose: () => Bridge.chooseEngine(),
    forget: () => Bridge.forgetEngine(),
    install: (upgrade) => Bridge.installEngine(upgrade),
    onInstallProgress: (handler) => Bridge.onInstallProgress(handler),
    onProgress: (handler) => Bridge.onEngineProgress(handler),
    link: (name) => Bridge.openLink(name),
  };

  SETTINGS.port = {
    read: () => Bridge.settings(),
    language: (code) => reported("language", Bridge.setLanguage(code)),
    appearance: (code) => reported("appearance", Bridge.setAppearance(code)),
    openAtLogin: (on) => reported("open at login", Bridge.setOpenAtLogin(on)),
    timedIngest: (minutes) => reported("timed ingest", Bridge.setTimedIngest(minutes)),
    model: () => Bridge.modelSettings(),
    modelLanguage: (code) => reported("model language", Bridge.setModelLanguage(code)),
    repositories: () => Bridge.engineRepositories(),
    repositoryLevel: (key, level) => Bridge.setRepositoryLevel(key, level),
    link: (name) => reported("link", Bridge.openLink(name)),
  };

  // The Review screen's button, and the line above the review that says whether writing
  // one would produce anything. `review.js` exports the seam and refuses to invent either
  // of them, because a screen may not call the bridge.
  REVIEW_NOW.run = () => {
    run("review");
  };
  // Reported rather than thrown: an engine that cannot be asked leaves the line off the
  // screen, and the reason goes where a screen's failures have to go.
  REVIEW_NOW.readiness = () => reported("readiness", Bridge.engineReadiness());
  document.body.appendChild(engineActivity());
}
