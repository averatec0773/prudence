/* The charts this app draws.
 *
 * The mockups' chart module had seven builders and 598 lines; six of them drew screens
 * that do not exist yet and none of them had been read to a product standard. They are
 * not here. `docs/design/mockups/charts.js` keeps them as the visual reference, and the
 * batch that builds each screen writes that screen's chart against this module's rules:
 *
 * - marks in the SVG, labels and values in HTML beside it, so type stays at its real
 *   size however narrow the column gets;
 * - `n` and the denominator printed, never only hovered, because a screenshot has no
 *   pointer;
 * - one `figure()` per chart, carrying the same numbers in words;
 * - colour is identity, never judgement.
 */

import { figure, svgEl } from "./dom.js";
import { PURPOSES } from "./purposes.js";

/** The palette lives in `tokens.css`; this is only how a purpose names its own variable. */
function purposeColour(purpose) {
  return `var(--p-${purpose})`;
}

/**
 * One row of a stacked bar: the composition of a whole, in a single line.
 *
 * @param {{ byPurpose: Record<string, number>, height?: number, caption: string }} options
 * @returns {HTMLElement}
 */
export function miniStack(options) {
  const width = 320;
  const height = options.height ?? 10;
  // Summed over the fixed list, which is the same list the caller's percentages are over.
  // Summing over the bucket's own keys instead would let an unrecognised purpose into the
  // denominator here and not into the legend, and the two would disagree.
  const total = PURPOSES.reduce((sum, purpose) => sum + (options.byPurpose[purpose] || 0), 0);

  const marks = [];
  if (total <= 0) {
    marks.push(
      svgEl("rect", { x: 0, y: 0, width, height, rx: height / 2, fill: "var(--control-2)" })
    );
  } else {
    let x = 0;
    for (const purpose of PURPOSES) {
      const value = options.byPurpose[purpose] || 0;
      if (value <= 0) continue;
      const w = (value / total) * width;
      marks.push(
        svgEl("rect", {
          x,
          y: 0,
          width: Math.max(w - 1.5, 1.5),
          height,
          rx: 2,
          fill: purposeColour(purpose),
        })
      );
      x += w;
    }
  }

  const svg = svgEl("svg", { viewBox: `0 0 ${width} ${height}`, preserveAspectRatio: "none" }, marks);
  svg.style.height = `${height}px`;
  return figure(svg, options.caption, { visuallyHidden: true });
}
