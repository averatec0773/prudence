/* The engine: where the `prudence` executable is, and what it can be asked to do.
 *
 * **This is a seam between two pieces of work.** The Settings screen places this block;
 * the CLI wiring fills it in. It is its own module so that neither has to edit the
 * other's file, and so the block can also be shown from somewhere else later (the panel
 * has the same four actions).
 *
 * It keeps the page contract: everything is handed in, one element comes out, and it
 * computes nothing. What it reports comes from the shell, which is the only thing that
 * can look at a filesystem or run a process.
 */

import { emptyState } from "../design/components.js";
import { el } from "../design/dom.js";
import { t } from "../text/strings.js";

/**
 * @param {import("./screens.js").ScreenState} state
 * @returns {Element}
 */
export function engineSection(state) {
  void state;
  return el("div", { class: "engine-section" }, [
    emptyState(t("screen.notBuilt.title"), t("screen.notBuilt.detail")),
  ]);
}
