/* The route table: every screen the window can show, and nothing about how it looks.
 *
 * **This file is the seam that lets four screens be built at once.** A screen is a module
 * that exports one function and owns one stylesheet, registered here by one line. Nothing
 * else in the app names a screen, so two people adding two screens touch two new files
 * and this table, and never the same line of anything.
 *
 * The contract a screen keeps is in `DESIGN.md` under "The page contract". In short: it
 * is handed everything it needs and reaches for nothing; it returns one element; it
 * computes no figures of its own; and its stylesheet may declare no design token.
 */

import { observations } from "./observations.js";
import { overview } from "./overview.js";
import { review } from "./review.js";
import { settings } from "./settings.js";

/**
 * @typedef {{
 *   data: any,
 *   info: any,
 *   project: string|null,
 *   range: string,
 *   week: string|null,
 *   onWeek: (week: string|null) => void,
 *   redraw: () => void,
 * }} ScreenState
 */

/**
 * The order is the sidebar's order and the keyboard's order: Cmd-1 is the first row.
 *
 * `scope` says whether the project and range pickers belong above this screen. A screen
 * that does not read them must not show them, because a control that changes nothing is
 * worse than no control.
 *
 * @type {{ key: string, label: string, scope: boolean, render: (state: ScreenState) => Element }[]}
 */
export const SCREENS = [
  { key: "overview", label: "section.overview", scope: true, render: overview },
  { key: "review", label: "section.review", scope: true, render: review },
  { key: "observations", label: "section.observations", scope: true, render: observations },
  { key: "settings", label: "section.settings", scope: false, render: settings },
];

export function screenFor(key) {
  return SCREENS.find((screen) => screen.key === key) ?? SCREENS[0];
}

export function screenExists(key) {
  return SCREENS.some((screen) => screen.key === key);
}
