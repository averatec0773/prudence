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

import { el, figure, svgEl } from "./dom.js";
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

/* --- shares, as horizontal bars ------------------------------------------------------
 *
 * One row per figure: what it is, how far it reaches, and the figure itself printed
 * beside it. The Review screen and the Observations screen both drew this and neither
 * drew it the same way: one built the track out of two nested `<div>`s and the other out
 * of an SVG, with two class families, two floors and two readings of what a null value
 * means. Two copies of a chart is two places for a chart to change, so it moved here
 * whole, which is what both files' own comments said should happen when a second screen
 * wanted it.
 *
 * The rules it keeps, which is why the two readings had to be settled rather than merged:
 *
 * - **One axis, always the whole share.** Every row is a fraction of the same thing, so
 *   every row is drawn against 0 to 1. A chart that scales to its own tallest bar draws a
 *   19% bar longer than an 84% bar on the card below it.
 * - **The value is printed, never only drawn.** A screenshot has no pointer, and a bar
 *   with no number beside it is a picture rather than a figure.
 * - **Colour is identity.** The caller gives each row its colour and it says which
 *   quantity this is, never whether the quantity is good.
 * - **A null value is not a zero.** `value: null` is "this figure is not a share" and
 *   draws no track at all; a value that is not a number is "the engine wrote none" and
 *   draws the empty track. The two are different statements and must not look alike.
 */

/** How much of the track a row fills, in the track's own units. */
const TRACK = 1000;

/** The smallest mark a non-zero share draws, so a side that is nearly nothing is still a
 *  mark rather than a gap the reader has to interpret. */
const FLOOR = 4;

/** One bar: the full track, what this row fills of it, and the context behind it. */
function shareTrack(row) {
  const marks = [
    svgEl("rect", { x: 0, y: 0, width: TRACK, height: 100, fill: "var(--surface-sunken)" }),
  ];
  // The coverage behind the figure: context for the bar, never a series to read against
  // it, which is why it is the full height and pale and goes down first.
  if (Number(row.underlay) > 0) {
    marks.push(
      svgEl("rect", {
        x: 0,
        y: 0,
        width: Math.min(Number(row.underlay), 1) * TRACK,
        height: 100,
        fill: "var(--coverage)",
      })
    );
  }
  if (Number(row.value) > 0) {
    marks.push(
      svgEl("rect", {
        x: 0,
        y: 0,
        width: Math.max(Math.min(Number(row.value), 1) * TRACK, FLOOR),
        height: 100,
        fill: row.colour,
      })
    );
  }
  const svg = svgEl(
    "svg",
    { viewBox: `0 0 ${TRACK} 100`, preserveAspectRatio: "none", "aria-hidden": "true" },
    marks
  );
  svg.style.width = "100%";
  svg.style.height = "100%";
  return el("div", { class: "track-wrap" }, [svg]);
}

/**
 * @param {{
 *   rows: {
 *     label: string,
 *     value: number | null,
 *     text: string,
 *     colour: string,
 *     underlay?: number | null,
 *     foot?: string,
 *   }[],
 *   caption: string,
 * }} options
 * @returns {HTMLElement}
 */
export function shareBars(options) {
  const chart = el("figure", { class: "chart paired" });
  for (const row of options.rows) {
    const value = el("span", { class: "paired-value" }, [el("span", { text: row.text })]);
    // Two elements rather than one string: a value and its qualification are not a
    // sentence, and joining them with a space in JavaScript would be one language's
    // punctuation applied to both.
    if (row.foot) value.appendChild(el("span", { class: "qualifier", text: row.foot }));

    chart.appendChild(
      el("div", { class: "paired-row" }, [
        el("span", { class: "paired-label", text: row.label }),
        // A figure that is not a share keeps its cell and draws nothing in it, so the
        // rows above and below it still line up.
        row.value === null || row.value === undefined
          ? el("span", { class: "track-blank" })
          : shareTrack(row),
        value,
      ])
    );
  }

  chart.setAttribute("role", "img");
  chart.setAttribute("aria-label", options.caption);
  // Hidden rather than printed: every label, value and denominator is already visible
  // HTML beside the marks, so a printed caption would say everything twice.
  chart.appendChild(el("figcaption", { class: "sr", text: options.caption }));
  return chart;
}

/* --- the axis a chart over time draws on --------------------------------------------
 *
 * The x axis is the **complete list of buckets in the range**, in order, whether or not
 * anything happened in one. It is ordinal: every slot is the same width, because a day is
 * a day and a week is a week. What a bucket is comes from the range and is decided in
 * `store/overview.js`, which holds the rule and its reason.
 *
 * A week slot may be a partial week. A range is counted in days (90, 365) and a day is
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
 * How often to print a slot's label, so they never collide.
 *
 * The labels are drawn at a fixed size in a box 760 units wide; past about fifteen slots
 * the names touch, and past thirty they overlap whatever is done with them. Printing
 * every second or every fourth is the honest way out: the axis still reads, and the table
 * under the chart has every bucket in full. It is also the measurement the bucket rule in
 * `store/overview.js` rests on: sixty daily slots is the most this box can carry.
 */
export function labelEvery(count) {
  if (count <= 14) return 1;
  if (count <= 28) return 2;
  return Math.ceil(count / 14);
}

/** The gridlines and their values, shared so both charts sit on the same furniture.
 *
 *  `unit` is the word the values are in, printed once above the topmost one. A value axis
 *  reading `0 / 0.4B / 0.8B / 1.1B / 1.5B` states its unit nowhere: the card's title
 *  carried "Tokens", which makes it inferable rather than stated. The percentage axis
 *  passes none, because `%` is on every label already. */
/**
 * @param {{ fractions: number[], format: (fraction: number) => string, plotH: number,
 *           unit?: string }} options
 */
function axisFurniture({ fractions, format, plotH, unit }) {
  const marks = [];
  if (unit) {
    marks.push(
      svgEl("text", {
        x: PLOT.width - PLOT.padRight + 8,
        y: PLOT.padTop - 4,
        text: unit,
        class: "axis",
      })
    );
  }
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

/** The slot names under the plot, thinned so they cannot collide. */
function slotLabels({ slots, label, at, height }) {
  const every = labelEvery(slots.length);
  return slots
    .map((slot, index) =>
      index % every === 0
        ? svgEl("text", {
            x: at(index),
            y: height - 8,
            "text-anchor": "middle",
            text: label(slot),
            class: "axis",
          })
        : null
    )
    .filter(Boolean);
}

/* --- composition of a whole, over time ---------------------------------------------
 *
 * One bar per bucket across the whole range, the fixed purpose order, a quiet value axis
 * on the right and the bucket under each bar. A bucket the store has no row for is an
 * **empty slot**: no bar at all, because nothing recorded and nothing spent are different
 * statements and must not look alike.
 */

/**
 * @param {{
 *   buckets: {bucket: string, byPurpose: Record<string, number>, total: number, measured: boolean}[],
 *   caption: string,
 *   label: (bucket: string) => string,
 *   axisFormat: (value: number) => string,
 *   axisUnit?: string,
 *   selected?: string | null,
 *   onHover?: (bucket: string | null) => void,
 *   onSelect?: (bucket: string | null) => void,
 * }} options
 */
export function stackedBars(options) {
  const { buckets } = options;
  const height = 200;
  const plotW = PLOT.width - PLOT.padLeft - PLOT.padRight;
  const plotH = height - PLOT.padTop - PLOT.padBottom;
  const max = niceMax(Math.max(0, ...buckets.map((one) => one.total)));
  const slot = plotW / Math.max(buckets.length, 1);
  // Capped, so a single day does not draw one slab the width of the card.
  const barWidth = Math.min(slot * 0.62, 56);
  const at = (index) => PLOT.padLeft + slot * index + slot / 2;

  const marks = axisFurniture({
    fractions: [0, 0.25, 0.5, 0.75, 1],
    format: (fraction) => options.axisFormat(max * fraction),
    plotH,
    unit: options.axisUnit,
  });

  buckets.forEach((one, index) => {
    const x = at(index) - barWidth / 2;
    const group = svgEl("g", {
      class: one.bucket === options.selected ? "col is-selected" : "col",
      "data-bucket": one.bucket,
    });

    let y = PLOT.padTop + plotH;
    for (const purpose of PURPOSES) {
      const value = one.byPurpose[purpose] || 0;
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

    // A bucket with no row draws the empty slot itself, so the gap is visibly a slot and
    // not the chart having stopped.
    if (!one.measured) {
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

    // One transparent rectangle per bucket over the whole column, so pointing anywhere in
    // the column answers rather than only at the ink.
    const hit = svgEl("rect", {
      class: "hit",
      x: PLOT.padLeft + slot * index,
      y: PLOT.padTop,
      width: slot,
      height: plotH,
      fill: "transparent",
    });
    hit.addEventListener("mouseenter", () => options.onHover?.(one.bucket));
    hit.addEventListener("mouseleave", () => options.onHover?.(null));
    hit.addEventListener("click", () =>
      options.onSelect?.(one.bucket === options.selected ? null : one.bucket)
    );
    group.appendChild(hit);
    marks.push(group);
  });

  marks.push(
    ...slotLabels({ slots: buckets.map((one) => one.bucket), label: options.label, at, height })
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

  marks.push(...slotLabels({ slots: weeks, label: options.label, at: slot, height }));

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
 *
 * ## The axis
 *
 * The strip had none: seven rows and N columns of squares, with the day only inside each
 * cell's `title`, which a pointer reaches and a screenshot does not. So the reader could
 * not tell which row was Monday.
 *
 * **The geometry**, which is also written in `DESIGN.md`:
 *
 * - a cell is 13 units square, 3 between them, so a row or a column is 16;
 * - the weekday gutter is `GUTTER` units wide, and its label sits on the cell's middle,
 *   right-aligned against the first column;
 * - the month band is `MONTH_BAND` units tall under the grid, and a month's name is drawn
 *   at the **left edge of the first column whose Monday falls in it**, which is where a
 *   month starts to within the week it starts in;
 * - both labels are the caller's strings. This module holds no text and reads no
 *   catalogue: `weekdays` is the seven names, Monday first, and `monthOf` answers with a
 *   column's month name.
 */

/** The width of the weekday gutter, which is three Latin letters or two Chinese ones. */
const GUTTER = 24;

/** The band under the grid that carries the months. */
const MONTH_BAND = 14;

/**
 * @param {{ weeks: {week: string, days: {day: string, hours: number|null, inRange: boolean}[]}[],
 *           max: number, caption: string, title: (day: string, hours: number|null) => string,
 *           weekdays?: string[], monthOf?: (week: string) => string }} options
 */
export function heatStrip(options) {
  const cell = 13;
  const gap = 3;
  const rows = 7;
  const weekdays = options.weekdays ?? [];
  const grid = Math.max(1, options.weeks.length * (cell + gap) - gap);
  const gridHeight = rows * (cell + gap) - gap;
  const width = GUTTER + grid;
  const height = gridHeight + MONTH_BAND;
  const at = (column) => GUTTER + column * (cell + gap);

  const marks = [];

  // Down the left, one per row, on the cell's own middle so the label and the row it names
  // cannot drift apart as the strip is scaled.
  weekdays.forEach((name, row) => {
    marks.push(
      svgEl("text", {
        x: GUTTER - 6,
        y: row * (cell + gap) + cell / 2 + 3,
        "text-anchor": "end",
        text: name,
        class: "axis",
      })
    );
  });

  options.weeks.forEach((week, column) => {
    week.days.forEach((day, row) => {
      if (!day.inRange) return;
      const measured = day.hours !== null && options.max > 0;
      const strength = measured ? Math.max(0.12, day.hours / options.max) : 0;
      marks.push(
        svgEl(
          "rect",
          {
            x: at(column),
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

  // Under the first column of each month. The first column carries its month too: a strip
  // that starts mid-month would otherwise leave its opening weeks unnamed.
  if (options.monthOf) {
    let said = null;
    options.weeks.forEach((week, column) => {
      const name = options.monthOf(week.week);
      if (!name || name === said) return;
      said = name;
      marks.push(
        svgEl("text", {
          x: at(column),
          y: gridHeight + MONTH_BAND - 3,
          text: name,
          class: "axis",
        })
      );
    });
  }

  const svg = svgEl("svg", { viewBox: `0 0 ${width} ${height}`, class: "heat" }, marks);
  svg.style.height = `${height}px`;
  return figure(svg, options.caption);
}
