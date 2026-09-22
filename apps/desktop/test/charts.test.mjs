/* The share bars, which two screens now draw and neither owns.
 *
 * The Review screen and the Observations screen each had their own copy of this chart,
 * with two class families, two floors and two readings of what a null value means. This
 * is the test that came with the one that is left: the rules it has to keep are the ones
 * the two copies disagreed about.
 *
 * The screens' own tests still assert what each of them puts in it. What is asserted here
 * is only what the component decides: the axis, the floor, the two kinds of absence, and
 * that the reading is printed rather than only drawn.
 *
 *     pnpm test
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { installDom } from "./dom.mjs";

installDom();

const { shareBars } = /** @type {any} */ (await import("../src/design/charts.js"));

const TRACK = 1000;

function drawn(rows, caption = "a caption") {
  const chart = shareBars({ rows, caption });
  return {
    chart,
    rows: chart.findAll(".paired-row"),
    /** Every mark that is not the empty track behind it. */
    inks: chart
      .findAll("rect")
      .filter((node) => node.getAttribute("fill") !== "var(--surface-sunken)"),
  };
}

function row(over = {}) {
  return { label: "did", value: 0.5, text: "50% of 12 sessions", colour: "var(--o-alive)", ...over };
}

/* One axis, always the whole share. It used to be a quarter, a half, three quarters or
   the whole, whichever first held the taller bar, and nothing said which had been picked:
   that drew a 19% bar longer than an 84% bar on the card below it. */
test("every bar is drawn against the whole share, so two charts can be compared", () => {
  const small = drawn([row({ value: 0.19 })]).inks[0];
  const large = drawn([row({ value: 0.94 })]).inks[0];
  assert.equal(Number(small.getAttribute("width")), 0.19 * TRACK);
  assert.equal(Number(large.getAttribute("width")), 0.94 * TRACK);
});

test("a share that is nearly nothing is still a mark, and none is not a gap to interpret", () => {
  const tiny = drawn([row({ value: 0.0001 })]).inks[0];
  assert.ok(Number(tiny.getAttribute("width")) >= 4, "a tiny share drew nothing at all");
  // A measured zero is a track with nothing in it, which is what zero looks like.
  assert.deepEqual(drawn([row({ value: 0 })]).inks, []);
});

/* The two kinds of absence, which the two copies read differently. */
test("a figure that is not a share draws no track, and a value the engine never wrote draws an empty one", () => {
  const notAShare = drawn([row({ value: null, text: "53,166 lines" })]);
  assert.equal(notAShare.chart.find(".track-wrap"), null, "a track was drawn for a count");
  assert.ok(notAShare.chart.find(".track-blank"), "the cell was dropped rather than left empty");
  assert.ok(notAShare.chart.textContent.includes("53,166 lines"), "the figure was not printed");

  const unwritten = drawn([row({ value: Number.NaN, text: "-" })]);
  assert.ok(unwritten.chart.find(".track-wrap"), "the empty track is missing");
  assert.deepEqual(unwritten.inks, [], "a bar was drawn for a value the engine never wrote");
});

/* Context for the bar, never a series to read against it: the coverage goes down first
   and the figure is drawn over it. */
test("the coverage sits behind the figure rather than beside it", () => {
  const { inks } = drawn([row({ value: 0.4, underlay: 0.9 })]);
  assert.deepEqual(
    inks.map((node) => node.getAttribute("fill")),
    ["var(--coverage)", "var(--o-alive)"]
  );
  assert.equal(Number(inks[0].getAttribute("width")), 0.9 * TRACK);
});

/* Colour is identity. The component takes the colour it is given and consults nothing:
   there is no path here by which which-side-is-longer changes an ink. */
test("colour is the caller's and nothing here changes it", () => {
  const higher = drawn([row({ value: 0.9, colour: "var(--o-rework)" })]);
  const lower = drawn([row({ value: 0.1, colour: "var(--o-rework)" })]);
  assert.equal(higher.inks[0].getAttribute("fill"), "var(--o-rework)");
  assert.equal(lower.inks[0].getAttribute("fill"), "var(--o-rework)");
});

test("every row prints its figure and its qualification, and the caption carries both", () => {
  const { chart, rows } = drawn(
    [
      row({ label: "did", text: "50% of 12 sessions", foot: "coverage 80%" }),
      row({ label: "did not", text: "20% of 30 sessions", colour: "var(--text-3)" }),
    ],
    "did 50% of 12 sessions, did not 20% of 30 sessions"
  );
  assert.equal(rows.length, 2);
  assert.ok(chart.textContent.includes("50% of 12 sessions"));
  assert.ok(chart.textContent.includes("coverage 80%"));
  // The same numbers for anything reading the page rather than looking at it, and the
  // printed caption is not a second copy on screen.
  assert.equal(
    chart.getAttribute("aria-label"),
    "did 50% of 12 sessions, did not 20% of 30 sessions"
  );
  assert.equal(chart.find("figcaption").className, "sr");
});
