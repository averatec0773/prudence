/* The Observations screen: one card per behaviour, paired bars per outcome.
 *
 * An observation is the join this product exists for: one behaviour, the reader's own
 * sessions split in two at one threshold, and the median of one outcome on each side.
 * The card is the unit, not the row, because survival at head and rework are two
 * readings of **the same two groups of sessions**; two cards would make them look like
 * two findings. That is the Swift app's variant C, the founder's choice on 2026-09-20.
 *
 * What this file is careful about:
 *
 * - **It owns no numbers.** Every figure is a column of `app_observation`. The only
 *   arithmetic is the gap between two shares, taken over the shares **as printed** so
 *   that subtracting the two visible cells gives the number under them, and the ordering
 *   key in `store/observations.js`, which is presentation.
 * - **Colour is identity.** The with-side takes the outcome's own colour and the
 *   without-side is grey. `direction` is deliberately not drawn at all: it says which
 *   way the with-side went, not which way is good, and an arrow or a second colour would
 *   turn it into a verdict. The two bars already say which is longer.
 * - **Every share carries its denominator**, in sessions, beside the bar it is on and
 *   again under the pair.
 * - **The method is stated twice**: in words on the card (the threshold, the coverage,
 *   the fact and inferred mix) and behind a disclosure as view and column names.
 */

import { el, svgEl } from "../design/dom.js";
import { scoped, shareOf } from "../store/observations.js";
import { count, decimal, percent, purpose, sessions } from "../text/fmt.js";
import { observationCaveat, observationSentence } from "../text/sentences.js";
import { plural, t } from "../text/strings.js";

/** The prefix the engine gives a purpose label used as a behaviour fact. */
const PURPOSE_PREFIX = "purpose:";

/* --- words ------------------------------------------------------------------------- */

/**
 * A behaviour in the two or three words a card heading and a bar label have room for.
 *
 * The catalogue is the list of known facts, rather than a copy of the engine's `SPLITS`
 * kept in this file: `t` answers with the key itself when there is no entry, which is
 * how a fact this build has never heard of falls back to the engine's own key. Ugly and
 * readable, never blank.
 *
 * @param {string} fact
 */
export function shortLabel(fact) {
  if (fact.startsWith(PURPOSE_PREFIX)) {
    return t("observation.split.purpose", purpose(fact.slice(PURPOSE_PREFIX.length)));
  }
  const key = `observation.short.${fact}`;
  const found = t(key);
  return found === key ? fact : found;
}

/** Which outcome the two medians are of. Every outcome but `rework` is survival at head,
 *  which is the engine's own else-branch rather than a second special case. */
export function outcomeLabel(outcome) {
  return outcome === "rework" ? t("observation.outcome.rework") : t("observation.outcome.alive");
}

/**
 * The line that made the split, in the reader's own language where the store can say it.
 *
 * `threshold_text` is the engine's English ("commit_attempts_per_commit > 2"), so a
 * Chinese card would otherwise carry one English expression in the middle of it.
 * Contract 3 stores the split as an operator and a number, which is enough for the
 * interface to word it itself.
 *
 * **The engine's text stays the fallback and stays authoritative where it disagrees.** A
 * contract 2 store has neither column, and a contract 3 row may carry an operator this
 * build has never heard of; either way the engine's own words are printed rather than a
 * clause this app invented. The text is shown behind the disclosure in both cases, so
 * the rewording can be checked against it.
 *
 * @param {Record<string, any>} row
 */
export function thresholdLine(row) {
  const fallback =
    row.threshold_text === null || row.threshold_text === undefined
      ? ""
      : String(row.threshold_text);
  const value = Number(row.threshold_value);
  if (!row.threshold_op || row.threshold_value === null || row.threshold_value === undefined) {
    return fallback;
  }
  if (!Number.isFinite(value)) return fallback;
  // A count or a rate, written the way the reader's locale writes one.
  const number = Number.isInteger(value) ? count(value) : decimal(value, 1);
  if (row.threshold_op === ">=") return t("observations.threshold.atLeast", number);
  if (row.threshold_op === ">") return t("observations.threshold.moreThan", number);
  if (row.threshold_op === "==") return t("observations.threshold.exactly", number);
  return fallback;
}

/* --- the chart ----------------------------------------------------------------------
 *
 * Two groups compared, as paired horizontal bars. The marks are SVG; the label, the
 * value and the n are HTML beside them, so the type stays at its real size however
 * narrow the column gets. This is the chart the product exists for, and it lives in the
 * screen that draws it until a second screen wants it, at which point it moves whole to
 * `design/charts.js` rather than being copied.
 */

/**
 * The axis top: a quarter, a half, three quarters or the whole, whichever first holds
 * the taller bar. A scale fitted to the data would draw two observations with different
 * values identically.
 *
 * @param {number} value
 */
export function niceMaxShare(value) {
  if (value <= 0.25) return 0.25;
  if (value <= 0.5) return 0.5;
  if (value <= 0.75) return 0.75;
  return 1;
}

/**
 * A share in whole points, **as the bar prints it**.
 *
 * Read back out of `percent` on purpose. The gap under the pair has to be the one a
 * reader gets by subtracting the two cells in front of them, and the engine's rounding
 * rule (half to even, to match `f"{x:.0f}%"`) lives in `text/fmt.js`. Rounding again
 * here would put a second copy of that rule in a second file, and the two would
 * eventually disagree on an exact half.
 *
 * @param {number} share
 */
function printedPoints(share) {
  return Number.parseInt(percent(share), 10);
}

/**
 * The distance between the two sides, in whole points, over the values as printed.
 *
 * @param {number} withValue
 * @param {number} withoutValue
 * @returns {number|null} null when either side cannot be printed as a share
 */
export function gapPoints(withValue, withoutValue) {
  const first = printedPoints(withValue);
  const second = printedPoints(withoutValue);
  if (!Number.isFinite(first) || !Number.isFinite(second)) return null;
  return Math.abs(first - second);
}

/** One bar: the full track, and the share of it this side fills. */
function track(fraction, fill) {
  const marks = [
    svgEl("rect", { x: 0, y: 0, width: 1000, height: 100, fill: "var(--surface-sunken)" }),
  ];
  if (fraction > 0) {
    // A floor of four units, so a side that is nearly nothing is still a mark rather
    // than a gap the reader has to interpret.
    marks.push(
      svgEl("rect", {
        x: 0,
        y: 0,
        width: Math.max(Math.min(fraction, 1) * 1000, 4),
        height: 100,
        fill,
      })
    );
  }
  const svg = svgEl(
    "svg",
    { viewBox: "0 0 1000 100", preserveAspectRatio: "none", "aria-hidden": "true" },
    marks
  );
  svg.style.width = "100%";
  svg.style.height = "100%";
  return el("div", { class: "track-wrap" }, [svg]);
}

/**
 * @param {{ labelWith: string, labelWithout: string, withValue: number, withoutValue: number,
 *           withN: number, withoutN: number, fill: string }} options
 * @returns {HTMLElement}
 */
function pairedBars(options) {
  const scale = niceMaxShare(Math.max(options.withValue, options.withoutValue, 0.01));
  const sides = [
    {
      label: options.labelWith,
      value: options.withValue,
      n: options.withN,
      // The outcome's own colour: which outcome this pair is of, never which side to be
      // on. `direction` is not consulted here and must not be.
      fill: options.fill,
    },
    {
      label: options.labelWithout,
      value: options.withoutValue,
      n: options.withoutN,
      fill: "var(--text-3)",
    },
  ];

  const figure = el("figure", { class: "chart paired" });
  const readings = [];
  for (const side of sides) {
    const reading = t("chart.shareOver", percent(side.value), sessions(side.n));
    readings.push(reading);
    figure.appendChild(
      el("div", { class: "paired-row" }, [
        el("span", { class: "paired-label", text: side.label }),
        track(side.value / scale, side.fill),
        el("span", { class: "paired-value", text: reading }),
      ])
    );
  }

  const gap = gapPoints(options.withValue, options.withoutValue);
  const gapText = gap === null ? t("common.dash") : plural("observation.gapPoints", gap, count(gap));
  figure.appendChild(
    el("div", { class: "paired-row paired-gap" }, [
      el("span", { class: "paired-label" }),
      el("span", { text: gapText }),
    ])
  );

  const caption = t(
    "observations.pairReading",
    sides[0].label,
    readings[0],
    sides[1].label,
    readings[1],
    gapText
  );
  figure.setAttribute("role", "img");
  figure.setAttribute("aria-label", caption);
  // Hidden rather than printed: the label, the share and the n of both sides are already
  // visible HTML beside the marks, so a printed caption would say everything twice.
  figure.appendChild(el("figcaption", { class: "sr", text: caption }));
  return figure;
}

/* --- the card ------------------------------------------------------------------------ */

/** One outcome of one split: what it is of, the sentence, the bars, and the caveat. */
function outcomeBlock(row) {
  const block = el("div", { class: "obs-outcome" });
  block.appendChild(el("h3", { class: "chart-name", text: outcomeLabel(String(row.outcome)) }));
  block.appendChild(el("p", { class: "obs-sentence", text: observationSentence(row) }));
  block.appendChild(
    pairedBars({
      labelWith: shortLabel(String(row.fact ?? "")),
      labelWithout: t("observation.side.didNot"),
      // NaN rather than 0 where the column is empty: `percent` prints a dash for it and
      // the bar is not drawn, which is what "the engine did not write one" looks like.
      withValue: shareOf(row.with_value) ?? Number.NaN,
      withoutValue: shareOf(row.without_value) ?? Number.NaN,
      withN: Number(row.with_n),
      withoutN: Number(row.without_n),
      fill: row.outcome === "rework" ? "var(--o-rework)" : "var(--o-alive)",
    })
  );
  // The coverage and the method mix sit with the numbers they qualify, never a section
  // away: an observation whose caveat cannot be shown is an observation not shown.
  block.appendChild(
    el("div", { class: "obs-caveat" }, [
      el("div", { class: "coverage-chip", text: observationCaveat(row) }),
      el("div", {
        class: "method",
        text: t(
          "observation.sessionsDidDidNot",
          sessions(Number(row.with_n)),
          count(Number(row.without_n))
        ),
      }),
    ])
  );
  return block;
}

/**
 * One behaviour: its short name, who it is about, the threshold that made the split, and
 * one paired-bars block per outcome.
 *
 * A pooled card is labelled "across your projects" and nothing else. It is computed only
 * for a behaviour no single project had the sessions to answer, and it is not a finding
 * about any one of them.
 *
 * @param {{ key: string, fact: string, pooled: boolean, project: string|null, gap: number,
 *           rows: Record<string, any>[] }} group
 */
function card(group) {
  const first = group.rows[0];
  const head = el("div", { class: "panel-head" }, [
    el("h2", { text: shortLabel(group.fact) }),
    el("span", {
      class: "chip",
      text: group.pooled ? t("observation.pooledTag") : (group.project ?? t("scope.allProjects")),
    }),
  ]);

  const node = el("div", { class: "card panel obs-card" }, [head]);
  const threshold = thresholdLine(first);
  if (threshold) {
    node.appendChild(
      el("p", { class: "panel-note", text: t("observations.threshold", threshold) })
    );
  }
  for (const row of group.rows) node.appendChild(outcomeBlock(row));

  const how = el("details", { class: "method" }, [
    el("summary", { text: t("chart.method") }),
    el("p", { text: t("observations.method") }),
  ]);
  // The engine's own clause, kept where a reader can check the reworded one above
  // against it. On a contract 2 store the two are the same string, which is honest.
  if (first.threshold_text !== null && first.threshold_text !== undefined) {
    how.appendChild(
      el("p", { text: t("observations.method.threshold", String(first.threshold_text)) })
    );
  }
  node.appendChild(how);
  return node;
}

function emptyState(title, detail) {
  return el("div", { class: "empty" }, [
    el("div", { class: "empty-title", text: title }),
    el("div", { class: "empty-detail", text: detail }),
  ]);
}

/** What an observation is, and which rules produced the ones on this page. */
function footNotes(data) {
  const notes = el("div", { class: "notes" }, [el("div", { text: t("observations.floor") })]);
  const version = data?.status?.observation_fact_version;
  if (version !== null && version !== undefined) {
    notes.appendChild(
      el("div", {
        text: t("observations.version", String(version), String(data?.contract ?? "")),
      })
    );
  }
  return notes;
}

/* --- the screen ----------------------------------------------------------------------- */

/**
 * @param {import("./screens.js").ScreenState} state
 * @returns {Element}
 */
export function observations(state) {
  const { data, project } = state;
  const screen = el("div", { class: "screen-body" });
  const found = scoped(data, { project });

  if (!found.rows.length) {
    // "No observations for this project" and "no observations anywhere" are two
    // different statements, and the reader has to be told which one this is.
    screen.appendChild(
      project === null
        ? emptyState(t("observations.empty.all.title"), t("observations.empty.all.detail"))
        : emptyState(t("observations.empty.project.title"), t("observations.empty.project.detail"))
    );
    screen.appendChild(footNotes(data));
    return screen;
  }

  // Under "All projects" the page comes in blocks: the pooled rows under their own
  // heading, then one heading per project. A row about one project under a heading that
  // says every project would be a statement about all of them, and a heading is cheaper
  // than hiding the row.
  //
  // With one project picked there are no blocks at all: its cards and the pooled ones
  // that answer a behaviour it could not answer alone, in one order, each card saying
  // which it is.
  const blocks =
    project !== null
      ? []
      : [
          ...(found.pooled.length
            ? [{ title: t("observations.group.pooled"), groups: found.pooled }]
            : []),
          ...found.projects.map((entry) => ({ title: entry.project, groups: entry.groups })),
        ];

  const lede = el("div", { class: "notes obs-lede" });
  // The line about blocks is drawn only where there are blocks. On a store with one
  // project and nothing pooled it would describe an arrangement that is not on screen.
  if (project !== null) lede.appendChild(el("div", { text: t("observations.scope.project") }));
  else if (blocks.length > 1) lede.appendChild(el("div", { text: t("observations.scope.pooled") }));
  lede.appendChild(el("div", { text: t("observations.sortedByGap") }));
  // The range picker above this screen changes nothing here, and until the route table
  // can ask for one picker without the other, saying so is the honest answer.
  lede.appendChild(el("div", { text: t("observations.allSessions") }));
  screen.appendChild(lede);

  if (!blocks.length) {
    const groups = [...found.pooled, ...found.projects.flatMap((one) => one.groups)].sort(
      (a, b) => b.gap - a.gap || a.key.localeCompare(b.key)
    );
    for (const group of groups) screen.appendChild(card(group));
  } else {
    for (const block of blocks) {
      // A heading only where there is more than one block to tell apart: every card
      // already carries its own chip, so one heading over one block would say the
      // project's name twice and divide nothing.
      if (blocks.length > 1) {
        screen.appendChild(el("h2", { class: "obs-heading", text: block.title }));
      }
      for (const group of block.groups) screen.appendChild(card(group));
    }
  }

  screen.appendChild(footNotes(data));
  return screen;
}
