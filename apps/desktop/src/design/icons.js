/* The sidebar's five icons.
 *
 * SF Symbols are not reachable from a webview: they are a font and an API, and a web
 * page gets neither. So these are drawn, once, to the same brief as the symbols the
 * Swift sidebar uses (`chart.bar`, `doc.text`, `lightbulb`, `gearshape`): a 16 pt box, a
 * 1.5 pt stroke on the 16-unit grid, round caps and joins, and `currentColor` so a
 * selected row's icon turns with its label.
 *
 * They are paths rather than files for the same reason the brand mark is: a page has
 * them without a fetch, and a single-file copy stays self-contained.
 */

import { svgEl } from "./dom.js";

/** @type {Record<string, string[]>} */
const PATHS = {
  // Three bars of different heights: what the Overview draws.
  overview: ["M3 13.5V9", "M8 13.5V4", "M13 13.5v-6"],
  // A folder with its tab: what a repository is on disk. The symbol the Swift sidebar
  // would have used is `folder`, drawn to the same brief as the other four.
  repositories: [
    "M2.5 12V4.5a1 1 0 0 1 1-1h2.8l1.5 1.5h4.7a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1h-9a1 1 0 0 1-1-1Z",
    "M2.5 7h11",
  ],
  // A page with two lines of writing on it.
  review: ["M4 2.5h5.5L12 5v8.5H4z", "M6 8h4", "M6 10.5h4"],
  // A bulb with its base: a thing noticed.
  observations: ["M8 2.5a3.75 3.75 0 0 0-2.25 6.75V11h4.5V9.25A3.75 3.75 0 0 0 8 2.5Z", "M6.75 13h2.5"],
  // A gear: a hub, a ring, and eight teeth on the ring. Drawn this way rather than as a
  // twelve-point outline because at 16 pt an outline is a smudge, and rather than as
  // spokes from the centre because that reads as a sun.
  settings: [
    "M8 5.7A2.3 2.3 0 1 0 8 10.3 2.3 2.3 0 0 0 8 5.7Z",
    "M8 2.7a5.3 5.3 0 1 0 0 10.6 5.3 5.3 0 0 0 0-10.6Z",
    "M13.30 8.00L14.70 8.00",
    "M11.75 11.75L12.74 12.74",
    "M8.00 13.30L8.00 14.70",
    "M4.25 11.75L3.26 12.74",
    "M2.70 8.00L1.30 8.00",
    "M4.25 4.25L3.26 3.26",
    "M8.00 2.70L8.00 1.30",
    "M11.75 4.25L12.74 3.26",
  ],
};

/**
 * @param {string} name
 * @param {number} [size]
 * @returns {SVGElement}
 */
export function icon(name, size = 16) {
  const paths = PATHS[name] ?? [];
  const node = svgEl(
    "svg",
    {
      viewBox: "0 0 16 16",
      width: size,
      height: size,
      fill: "none",
      stroke: "currentColor",
      "stroke-width": 1.5,
      "stroke-linecap": "round",
      "stroke-linejoin": "round",
      "aria-hidden": "true",
      focusable: "false",
    },
    paths.map((d) => svgEl("path", { d }))
  );
  node.classList.add("icon");
  return node;
}

export const ICONS = Object.keys(PATHS);
