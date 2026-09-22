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

import { chosen, reviewsFor } from "../store/review.js";
import { wholeStore } from "./review.js";
import { day as formatDay } from "../text/fmt.js";
import { t } from "../text/strings.js";
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
 *   bucket: string|null,
 *   onBucket: (bucket: string|null) => void,
 *   redraw: () => void,
 * }} ScreenState
 */

/**
 * The order is the sidebar's order and the keyboard's order: Cmd-1 is the first row.
 *
 * `scope` names **which pickers this screen reads**, and only those are drawn above it.
 * It was one boolean for both until the Review and Observations screens arrived and
 * neither read the range: a stored review carries its own two windows, and an observation
 * has no date window at all (`store/observations.py` has none). The page contract's own
 * words are that a control that changes nothing is worse than no control.
 *
 * `subtitle` is the line under the heading, and it belongs to the screen because only the
 * screen knows what it is showing. A screen that does not give one gets its own name.
 *
 * @typedef {"project" | "range"} Picker
 * @type {{
 *   key: string,
 *   label: string,
 *   scope: Picker[],
 *   subtitle?: (state: ScreenState) => string,
 *   render: (state: ScreenState) => Element,
 * }[]}
 */
export const SCREENS = [
  // No subtitle. The Overview states its scope and its window in the summary line at the
  // top of the screen itself, in a sentence with the three figures in it, because a grey
  // line in the window's head was the only place the window was named and every figure
  // below it had lost its time frame.
  { key: "overview", label: "section.overview", scope: ["project", "range"], render: overview },
  {
    key: "review",
    label: "section.review",
    scope: ["project"],
    subtitle: reviewSubtitle,
    render: review,
  },
  {
    key: "observations",
    label: "section.observations",
    scope: ["project"],
    subtitle: observationsSubtitle,
    render: observations,
  },
  { key: "settings", label: "section.settings", scope: [], render: settings },
];

export function screenFor(key) {
  return SCREENS.find((screen) => screen.key === key) ?? SCREENS[0];
}

export function screenExists(key) {
  return SCREENS.some((screen) => screen.key === key);
}


/* --- the subtitles ------------------------------------------------------------------
 *
 * One per screen, because only the screen knows what it is showing. This used to be a
 * single function in `window.js` that returned a hardcoded English sentence for every
 * screen but the Overview, which was true while three screens were placeholders and
 * became a lie above each one as it was written.
 */

function reviewSubtitle(state) {
  // The one the screen opens on: the newest in scope.
  const newest = chosen(reviewsFor(state.data, { project: state.project }), null);
  if (!newest) return t("review.subtitle.none");
  const scope = wholeStore(newest.project) ? t("review.scope.everyProject") : String(newest.project);
  return t("review.subtitle.scope", scope, formatDay(newest.created_at));
}

function observationsSubtitle(state) {
  return state.project ? t("observations.subtitle.project", state.project) : t("observations.subtitle.pooled");
}
