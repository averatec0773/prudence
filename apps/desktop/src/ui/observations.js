/* The Observations screen.
 *
 * A stub that says so. It keeps the page contract (`DESIGN.md`, "The page contract") so
 * that the screen can be written without touching anything outside this file and
 * `observations.css`: one exported function, everything handed in, one element returned.
 */

import { el } from "../design/dom.js";
import { t } from "../text/strings.js";

/**
 * @param {import("./screens.js").ScreenState} state
 * @returns {Element}
 */
export function observations(state) {
  void state;
  return el("div", { class: "screen-body" }, [
    el("div", { class: "empty" }, [
      el("div", { class: "empty-title", text: t("screen.notBuilt.title") }),
      el("div", { class: "empty-detail", text: t("screen.notBuilt.detail") }),
    ]),
  ]);
}
