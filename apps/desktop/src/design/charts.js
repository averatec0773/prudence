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

/* --- the axis every weekly chart shares --------------------------------------------
 *
 * The x axis is the **complete list of weeks in the range**, in order, whether or not
 * anything happened in one. Both Overview charts are handed the same list, so a week sits
 * at the same x in each and the two can be read against one another. It is ordinal: every
 * slot is the same width, because a week is a week.
 *
 * The first slot may be a partial week. A range is counted in days (56, 90) and a day is
 * rarely a Monday, so the earliest week the range touches is usually entered part-way.
 * The alternative is to drop the data in it, which would be worse.
 */

/** The plot box the weekly charts draw into, in viewBox units. */
const PLOT = { width: 760, padLeft: 8, padRight: 56, padTop: 12, padBottom: 26 };

/**
 * A round number at or above the largest value, so the axis reads 0 / 1.5k / 3k / 6k.
 *
 * The steps are finer than the usual 1-2-5 because that ladder wastes the plot: a tallest
 * bar of 5,955 rounds up to 10,000 and then reaches three fifths of the way up a chart
 * whose whole job is to compare heights. Every step here divides by four into a number a
 * person can read, because the gridlines are quarters.
 */
const STEPS = [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10];

export function niceMax(value) {
  if (!(value > 0)) return 1;
  const power = 10 ** Math.floor(Math.log10(value));
  const scaled = value / power;
  return (STEPS.find((step) => scaled <= step) ?? 10) * power;
}

/**
 * How often to print a week's label, so they never collide.
 *
 * The labels are drawn at a fixed size in a box 760 units wide; past about fifteen weeks
 * the names touch, and past thirty they overlap whatever is done with them. Printing
 * every second or every fourth is the honest way out: the axis still reads, and the table
 * under the chart has every week in full.
 */
export function labelEvery(count) {
  if (count <= 14) return 1;
  if (count <= 28) return 2;
  return Math.ceil(count / 14);
}

/** The gridlines and their values, shared so both charts sit on the same furniture. */
function axisFurniture({ fractions, format, plotH }) {
  const marks = [];
  for (const fraction of fractions) {
    const y = PLOT.padTop + plotH - plotH * fraction;
    marks.push(
      svgEl("line", {
        x1: PLOT.padLeft,
        y1: y,
        x2: PLOT.width - PLOT.padRight,
        y2: y,
        class: "gridline",
      })
    );
    marks.push(
      svgEl("text", { x: PLOT.width - PLOT.padRight + 8, y: y + 3.5, text: format(fraction), class: "axis" })
    );
  }
  return marks;
}

/** The week names under the plot, thinned so they cannot collide. */
function weekLabels({ weeks, label, at, height }) {
  const every = labelEvery(weeks.length);
  return weeks
    .map((week, index) =>
      index % every === 0
        ? svgEl("text", {
            x: at(index),
            y: height - 8,
            "text-anchor": "middle",
            text: label(week),
            class: "axis",
          })
        : null
    )
    .filter(Boolean);
}

/* --- composition of a whole, over time ---------------------------------------------
 *
 * One bar per ISO week across the whole range, the fixed purpose order, a quiet value
 * axis on the right and the week under each bar. A week the store has no row for is an
 * **empty slot**: no bar at all, because nothing recorded and nothing spent are different
 * statements and must not look alike.
 */

/**
 * @param {{
 *   weeks: {week: string, byPurpose: Record<string, number>, total: number, measured: boolean}[],
 *   caption: string,
 *   label: (week: string) => string,
 *   axisFormat: (value: number) => string,
 *   selected?: string | null,
 *   onHover?: (week: string | null) => void,
 *   onSelect?: (week: string | null) => void,
 * }} options
 */
export function stackedBars(options) {
  const { weeks } = options;
  const height = 200;
  const plotW = PLOT.width - PLOT.padLeft - PLOT.padRight;
  const plotH = height - PLOT.padTop - PLOT.padBottom;
  const max = niceMax(Math.max(0, ...weeks.map((week) => week.total)));
  const slot = plotW / Math.max(weeks.length, 1);
  // Capped, so three weeks do not draw three slabs a third of the card wide.
  const barWidth = Math.min(slot * 0.62, 56);
  const at = (index) => PLOT.padLeft + slot * index + slot / 2;

  const marks = axisFurniture({
    fractions: [0, 0.25, 0.5, 0.75, 1],
    format: (fraction) => options.axisFormat(max * fraction),
    plotH,
  });

  weeks.forEach((week, index) => {
    const x = at(index) - barWidth / 2;
    const group = svgEl("g", {
      class: week.week === options.selected ? "col is-selected" : "col",
      "data-week": week.week,
    });

    let y = PLOT.padTop + plotH;
    for (const purpose of PURPOSES) {
      const value = week.byPurpose[purpose] || 0;
      if (value <= 0) continue;
      const h = (value / max) * plotH;
      y -= h;
      group.appendChild(
        svgEl("rect", {
          class: "bar",
          x,
          y,
          width: barWidth,
          height: Math.max(h, 0.75),
          rx: 1.5,
          fill: purposeColour(purpose),
        })
      );
    }

    // A week with no row draws the empty slot itself, so the gap is visibly a slot and
    // not the chart having stopped.
    if (!week.measured) {
      group.appendChild(
        svgEl("rect", {
          class: "bar-empty",
          x,
          y: PLOT.padTop + plotH - 2,
          width: barWidth,
          height: 2,
          rx: 1,
        })
      );
    }

    // One transparent rectangle per week over the whole column, so pointing anywhere in
    // the column answers rather than only at the ink.
    const hit = svgEl("rect", {
      class: "hit",
      x: PLOT.padLeft + slot * index,
      y: PLOT.padTop,
      width: slot,
      height: plotH,
      fill: "transparent",
    });
    hit.addEventListener("mouseenter", () => options.onHover?.(week.week));
    hit.addEventListener("mouseleave", () => options.onHover?.(null));
    hit.addEventListener("click", () =>
      options.onSelect?.(week.week === options.selected ? null : week.week)
    );
    group.appendChild(hit);
    marks.push(group);
  });

  marks.push(
    ...weekLabels({ weeks: weeks.map((w) => w.week), label: options.label, at, height })
  );

  const svg = svgEl("svg", { viewBox: `0 0 ${PLOT.width} ${height}`, class: "bars" }, marks);
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
 *   label: (week: string) => string,
 *   dashed?: boolean,
 * }} options
 */
export function linesWithGaps(options) {
  const height = 220;
  const weeks = options.weeks;
  const plotW = PLOT.width - PLOT.padLeft - PLOT.padRight;
  const plotH = height - PLOT.padTop - PLOT.padBottom;
  const step = weeks.length < 2 ? 0 : plotW / (weeks.length - 1);
  const slot = (index) =>
    weeks.length < 2 ? PLOT.padLeft + plotW / 2 : PLOT.padLeft + step * index;
  const at = (week) => slot(Math.max(0, weeks.indexOf(week)));
  const y = (value) => PLOT.padTop + plotH - value * plotH;

  const marks = axisFurniture({
    fractions: [0, 0.5, 1],
    format: (fraction) => `${Math.round(fraction * 100)}%`,
    plotH,
  });

  // The coverage goes down first and wide and pale: it is the context for the lines
  // above it, not a series to read against them.
  for (const run of options.coverage ?? []) {
    if (run.length < 1) continue;
    if (run.length === 1) {
      // Same reason as the series below: a one-point path is a lone moveto and draws
      // nothing, so the one week whose coverage was measured would vanish.
      marks.push(
        svgEl("circle", { cx: at(run[0].week), cy: y(run[0].value), r: 3.5, fill: "var(--coverage)" })
      );
      continue;
    }
    marks.push(
      svgEl("path", {
        d: path(run, at, y),
        fill: "none",
        stroke: "var(--coverage)",
        "stroke-width": 7,
        "stroke-linecap": "round",
        "stroke-linejoin": "round",
      })
    );
  }

  for (const line of options.series) {
    for (const run of line.runs) {
      if (run.length === 1) {
        // A single measured week between two holes is still a measurement and has to be
        // visible; a one-point path draws nothing.
        marks.push(
          svgEl("circle", { cx: at(run[0].week), cy: y(run[0].value), r: 3, fill: line.colour })
        );
        continue;
      }
      marks.push(
        svgEl("path", {
          d: path(run, at, y),
          fill: "none",
          stroke: line.colour,
          "stroke-width": 2,
          "stroke-linecap": "round",
          "stroke-linejoin": "round",
          "stroke-dasharray": options.dashed ? "3 4" : null,
        })
      );
      for (const point of run) {
        marks.push(
          svgEl("circle", { cx: at(point.week), cy: y(point.value), r: 2.6, fill: line.colour })
        );
      }
    }
  }

  marks.push(...weekLabels({ weeks, label: options.label, at: slot, height }));

  const svg = svgEl("svg", { viewBox: `0 0 ${PLOT.width} ${height}`, class: "lines" }, marks);
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
