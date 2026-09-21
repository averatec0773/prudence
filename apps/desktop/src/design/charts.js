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

/* --- composition of a whole, over time ---------------------------------------------
 *
 * One bar per ISO week, the fixed purpose order, and the totals printed under the chart
 * rather than only on hover, because a screenshot has no pointer.
 */

/**
 * @param {{
 *   weeks: {week: string, byPurpose: Record<string, number>, total: number}[],
 *   caption: string,
 *   label: (week: string) => string,
 *   selected?: string | null,
 *   onHover?: (week: string | null) => void,
 *   onSelect?: (week: string | null) => void,
 * }} options
 */
export function stackedBars(options) {
  const { weeks } = options;
  const height = 150;
  const gap = 6;
  const max = Math.max(1, ...weeks.map((week) => week.total));
  // Capped, so four weeks do not draw four slabs the width of the card.
  const barWidth = Math.min(46, Math.max(10, 320 / Math.max(weeks.length, 1) - gap));
  const width = Math.max(1, weeks.length * (barWidth + gap) - gap);

  const marks = [];
  weeks.forEach((week, index) => {
    const x = index * (barWidth + gap);
    let y = height;
    for (const purpose of PURPOSES) {
      const value = week.byPurpose[purpose] || 0;
      if (value <= 0) continue;
      const h = (value / max) * height;
      y -= h;
      marks.push(
        svgEl("rect", {
          x,
          y,
          width: barWidth,
          height: Math.max(h, 1),
          fill: purposeColour(purpose),
        })
      );
    }
    // One transparent rectangle per week over the whole column height, so pointing
    // anywhere in the column answers rather than only on the ink.
    const hit = svgEl("rect", {
      x,
      y: 0,
      width: barWidth,
      height,
      fill: "transparent",
      class: week.week === options.selected ? "hit is-selected" : "hit",
    });
    hit.addEventListener("mouseenter", () => options.onHover?.(week.week));
    hit.addEventListener("mouseleave", () => options.onHover?.(null));
    hit.addEventListener("click", () =>
      options.onSelect?.(week.week === options.selected ? null : week.week)
    );
    marks.push(hit);
  });

  // Not stretched: the bar width is a design decision (capped at 46, as the design
  // says) and a viewBox scaled to the card's width would throw it away. The chart is
  // drawn at its own size and scrolls if the card is ever narrower than it is.
  const svg = svgEl("svg", { viewBox: `0 0 ${width} ${height}`, class: "bars" }, marks);
  svg.style.height = `${height}px`;
  svg.style.width = `${width}px`;
  return figure(svg, options.caption);
}

/* --- over time, with holes ----------------------------------------------------------
 *
 * One path per **run** of measured weeks, never one path with a gap in the data: a line
 * that joins across a week nothing measured is a line that invents a measurement.
 */

/**
 * @param {{
 *   series: {project: string, colour: string, runs: {week: string, value: number}[][]}[],
 *   coverage?: {week: string, value: number}[][],
 *   weeks: string[],
 *   caption: string,
 *   dashed?: boolean,
 * }} options
 */
export function linesWithGaps(options) {
  const height = 140;
  const width = 320;
  const weeks = options.weeks;
  const at = (week) => (weeks.length < 2 ? width / 2 : (weeks.indexOf(week) / (weeks.length - 1)) * width);
  const y = (value) => height - value * height;

  const marks = [];

  // The coverage goes down first and wide and pale: it is the context for the lines
  // above it, not a series to read against them.
  for (const run of options.coverage ?? []) {
    if (run.length < 1) continue;
    marks.push(
      svgEl("path", {
        d: path(run, at, y),
        fill: "none",
        stroke: "var(--coverage)",
        "stroke-width": 6,
        "stroke-linecap": "round",
        "stroke-linejoin": "round",
        // The line stretches with the card; its thickness must not.
        "vector-effect": "non-scaling-stroke",
      })
    );
  }

  for (const line of options.series) {
    for (const run of line.runs) {
      if (run.length === 1) {
        // A single measured week between two holes is still a measurement and has to be
        // visible; a one-point path draws nothing.
        marks.push(
          svgEl("circle", { cx: at(run[0].week), cy: y(run[0].value), r: 2.5, fill: line.colour })
        );
        continue;
      }
      marks.push(
        svgEl("path", {
          d: path(run, at, y),
          fill: "none",
          stroke: line.colour,
          "stroke-width": 1.75,
          "stroke-linecap": "round",
          "stroke-linejoin": "round",
          "stroke-dasharray": options.dashed ? "4 3" : null,
          "vector-effect": "non-scaling-stroke",
        })
      );
    }
  }

  const svg = svgEl(
    "svg",
    { viewBox: `0 0 ${width} ${height}`, preserveAspectRatio: "none", class: "lines" },
    marks
  );
  svg.style.height = `${height}px`;
  return figure(svg, options.caption);
}

function path(run, at, y) {
  return run.map((point, i) => `${i === 0 ? "M" : "L"}${at(point.week)} ${y(point.value)}`).join(" ");
}

/* --- where the hours went -----------------------------------------------------------
 *
 * One cell per local day, seven rows Monday first, a single hue. A day the view has no
 * row for has **no value**, and is drawn as the empty track rather than as a measured
 * zero: the engine writes no row for a day nothing happened on.
 */

/**
 * @param {{ weeks: {week: string, days: {day: string, hours: number|null, inRange: boolean}[]}[],
 *           max: number, caption: string, title: (day: string, hours: number|null) => string }} options
 */
export function heatStrip(options) {
  const cell = 13;
  const gap = 3;
  const rows = 7;
  const width = Math.max(1, options.weeks.length * (cell + gap) - gap);
  const height = rows * (cell + gap) - gap;

  const marks = [];
  options.weeks.forEach((week, column) => {
    week.days.forEach((day, row) => {
      if (!day.inRange) return;
      const measured = day.hours !== null && options.max > 0;
      const strength = measured ? Math.max(0.12, day.hours / options.max) : 0;
      marks.push(
        svgEl(
          "rect",
          {
            x: column * (cell + gap),
            y: row * (cell + gap),
            width: cell,
            height: cell,
            rx: 3,
            fill: measured ? "var(--accent)" : "var(--surface-sunken)",
            "fill-opacity": measured ? strength : 1,
          },
          [svgEl("title", { }, [])]
        )
      );
      marks[marks.length - 1].querySelector("title").textContent = options.title(day.day, day.hours);
    });
  });

  const svg = svgEl("svg", { viewBox: `0 0 ${width} ${height}`, class: "heat" }, marks);
  svg.style.height = `${height}px`;
  return figure(svg, options.caption);
}
