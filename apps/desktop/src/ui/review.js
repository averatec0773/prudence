/* The Review screen: one stored review, as the engine wrote it.
 *
 * Everything with a number in it on this page was formatted by the engine and is stored
 * on the row. The screen selects, arranges and draws; it computes nothing. Where a bar
 * has a length that length comes from the engine's own `value`, and the figure printed
 * beside it is the engine's own `text`, so the picture and the number cannot disagree.
 *
 * Three things the screen is careful about, each because the founder's own store has a
 * review that would otherwise be drawn wrong:
 *
 * - **The two ranges are two windows.** `range_start`/`range_end` is the period
 *   reviewed; `outcome_range_start`/`outcome_range_end` is the window the outcomes were
 *   measured over, which sits behind it so that the commits in it had time to be
 *   followed. The head states both, separately.
 * - **`coverage` may be null**, and it is on review 1. A null coverage is a dash and a
 *   sentence, never a zero and never a blank.
 * - **A dash is the engine's own.** `sections[].rows` carries `-` where nothing was
 *   measured; it is printed as stored and never turned into a zero.
 */

import { miniStack, shareBars } from "../design/charts.js";
import { el } from "../design/dom.js";
import { emptyState, panel, statCard } from "../design/components.js";
import { PURPOSES } from "../design/purposes.js";
import {
  bodyOf,
  chosen,
  comparisons,
  numbersOf,
  observationPairs,
  projectNames,
  purposeTokens,
  reviewsFor,
  segmentParagraphs,
  shares,
} from "../store/review.js";
import { readiness } from "../store/readiness.js";
import {
  count,
  day as formatDay,
  list,
  percent,
  purpose as purposeLabel,
  sessions as sessionPhrase,
  stamp,
} from "../text/fmt.js";
import { observationSentence, readinessSentence, readinessSource } from "../text/sentences.js";
import { t } from "../text/strings.js";

/** The engine's key for an observation computed over every project rather than one. */
const POOLED = "*";

/**
 * What the Review now button does, and what the engine says about pressing it.
 *
 * Running the engine is the CLI wiring's job, not a screen's: a screen is handed
 * everything and reaches for nothing, and `bridge.js` is the only place in the frontend
 * a Tauri call may live. The button is real now; until `run` is set it says where the
 * action is rather than pretending to have started one. The wiring sets `run` to a
 * function that starts the run, and the store watcher already redraws every page when a
 * review lands.
 *
 * `readiness` is the same seam for the line above the review: whether writing one now
 * would produce anything. **When** it is asked is `store/readiness.js`'s decision, not
 * this screen's: the answer follows an ingest, and asking on every draw closes a loop with
 * the store watcher that the file describes in full.
 *
 * @type {{ run: null | (() => void), readiness: null | (() => Promise<any>) }}
 */
export const REVIEW_NOW = { run: null, readiness: null };


/** A section that found nothing says so in the engine's own sentence, and no more. */
function storedEmpty(text) {
  return el("div", { class: "empty" }, [el("div", { class: "empty-detail", text })]);
}

/** The review's own notes, behind the same disclosure the Overview's charts use. */
function methodNotes(notes, extra) {
  if (!notes.length && !extra) return null;
  const how = el("details", { class: "method" });
  how.appendChild(el("summary", { text: t("chart.method") }));
  for (const note of notes) how.appendChild(el("p", { text: note }));
  if (extra) how.appendChild(extra);
  return how;
}

/**
 * A column header in the reader's language, or the engine's own word.
 *
 * The rest of a review is printed as stored, because a key per engine figure label would
 * drift from the engine in silence. Headers are the exception, and the reason is that they
 * are a closed set: `reviews/build.py` writes five header rows, sixteen labels. A header
 * this build has not heard of prints as the engine wrote it, so an engine that adds one is
 * never mistranslated, only untranslated.
 */
const HEADER_KEYS = {
  "purpose": "chart.purpose",
  "sessions": "chart.sessionsShort",
  "active h": "chart.hours",
  "value": "chart.value",
  "coverage": "overview.legend.coverageName",
  "this period": "compare.nowShort",
};

function headerLabel(title) {
  const head = String(title);
  // Six of the sixteen are words the product has already chosen elsewhere, so they are
  // reused rather than written twice: `strings.test.mjs` refuses two keys with the same
  // text unless the pair is two deliberate decisions, and these would have been one
  // decision written twice.
  const key = HEADER_KEYS[head] ?? `review.header.${head.replace(/[^a-z0-9]+/gi, "_").toLowerCase()}`;
  const said = t(key);
  return said === key ? head : said;
}

/** A stored section's table, with the engine's own cells and translated column headers. */
function storedTable(section, { swatches = false } = {}) {
  const table = el("table", { class: "data" });
  const head = el("tr");
  for (const [index, title] of (section.headers ?? []).entries()) {
    head.appendChild(el("th", { class: index ? "n" : "", text: headerLabel(title) }));
  }
  table.appendChild(el("thead", {}, [head]));

  const body = el("tbody");
  for (const row of section.rows ?? []) {
    const line = el("tr");
    for (const [index, cell] of row.entries()) {
      const td = el("td", { class: index ? "n" : "" });
      // A purpose row carries its colour, the same colour the composition bar above the
      // table gives it. The total row is not a purpose and gets none: the test is
      // whether the engine's label is one of the purposes, not a guess at which row is
      // the sum.
      if (swatches && index === 0 && PURPOSES.includes(/** @type {any} */ (cell))) {
        const dot = document.createElement("i");
        dot.className = "swatch";
        dot.style.background = `var(--p-${cell})`;
        td.appendChild(dot);
        td.appendChild(document.createTextNode(purposeLabel(String(cell))));
      } else {
        td.textContent = String(cell);
      }
      line.appendChild(td);
    }
    body.appendChild(line);
  }
  table.appendChild(body);
  return table;
}

/* The horizontal bars this screen draws are `design/charts.js`'s `shareBars`.
 *
 * They were a second implementation here, built out of `<div>`s where the Observations
 * screen's were SVG, with their own class family and their own reading of what a null
 * value means. The comment above them said a share bar belongs in the chart module with
 * the others and that adding one was a shared-file change; this is that change. Every
 * rule it kept is kept there, in one place: the value is printed rather than only drawn,
 * every share carries what it is over, a figure that is not a share draws no track, and
 * the caption carries the same numbers as the picture. */

/* --- the cards ---------------------------------------------------------------------- */

/** The head: which review this is, over which two windows, and what it rests on. */
function headlineCard(stored, figures) {
  // `app_review.project` is `COALESCE(r.name, v.project, 'all projects')`, so it is
  // never null and the `??` fallback here was unreachable: on a whole-store review the
  // engine's own English literal reached the screen, and a Chinese page read
  // "范围 all projects". The literal is recognised and said in the reader's language.
  const scope = wholeStore(stored.project) ? t("review.scope.everyProject") : String(stored.project);
  const start = formatDay(String(stored.range_start).slice(0, 10));
  const end = formatDay(String(stored.range_end).slice(0, 10));
  const card = el("div", { class: "card" }, [
    el("div", {
      class: "card-title",
      text: t("review.headline.project", String(stored.id), start, end, scope),
    }),
    el("div", {
      // The one line that keeps the two windows apart. They are different ranges, and a
      // page that prints one of them twice has told the reader something false.
      class: "card-sub",
      text: t(
        "review.rangeLine",
        start,
        end,
        formatDay(String(stored.outcome_range_start).slice(0, 10)),
        formatDay(String(stored.outcome_range_end).slice(0, 10))
      ),
    }),
  ]);

  const meta = el("div", { class: "meta-row" });
  const entries = [
    [t("review.tag.scope"), scope],
    // Null on the founder's own review 1, which was written before the engine learned
    // to take this column from the activity section when the outcome section has none.
    // A dash; the activity card below still prints its own mean coverage.
    [t("review.tag.coverage"), percent(stored.coverage ?? null)],
    [t("review.tag.written"), formatDay(String(stored.created_at).slice(0, 10))],
    [t("review.tag.figures"), figures === null ? t("common.dash") : count(figures)],
  ];
  for (const [key, value] of entries) {
    meta.appendChild(
      el("div", { class: "meta" }, [
        el("span", { class: "k", text: key }),
        el("span", { class: "v", text: value }),
      ])
    );
  }
  card.appendChild(meta);
  return card;
}

/** What you did: the four totals, the purpose mix, and the stored table. */
function didCard(section) {
  const title = t("review.section.did");
  const note = t("review.did.note");
  const numbers = numbersOf(section);
  // What coverage means is a sentence, so it goes in the disclosure with the engine's
  // own notes rather than under the figure, and only when the review has a coverage.
  const method = methodNotes(
    numbers.has("did.coverage")
      ? [...(section.notes ?? []), t("review.did.coverageHelp")]
      : (section.notes ?? [])
  );
  if (section.empty) return panel({ title, note, body: storedEmpty(section.empty), method });

  const body = el("div", { class: "stack" });

  // Caption, then the qualification the caption cannot carry. Sessions, hours and
  // tokens are the same measures the Overview shows and share its captions; commits are
  // **not**: a review counts the commits credited to the sessions of its period, and
  // the Overview counts the commits made on the days of a range. On the founder's own
  // review 1 those are 18 and 32, so one caption over both would make the two screens
  // look as if one of them were broken.
  const stats = [
    ["did.sessions", t("review.did.sessions"), ""],
    ["did.hours", t("overview.activeHours"), t("overview.sittingsNote")],
    ["did.commits", t("review.did.commits"), t("review.did.commitsFoot")],
    ["did.coverage", t("review.card.coverage"), t("review.did.coverageFoot")],
  ];
  const row = el("div", { class: "card-row" });
  for (const [key, caption, foot] of stats) {
    const number = numbers.get(key);
    if (!number) continue;
    row.appendChild(statCard(caption, number.text, foot));
  }
  if (row.children.length) body.appendChild(row);

  const byPurpose = purposeTokens(section);
  const present = PURPOSES.filter((key) => byPurpose[key] > 0);
  if (present.length) {
    body.appendChild(
      miniStack({
        parts: PURPOSES.map((key) => ({ value: byPurpose[key], colour: `var(--p-${key})` })),
        caption: list(
          present.map((key) => {
            const tokens = numbers.get(`did.tokens.${key}`);
            return t("review.headline.section", purposeLabel(key), tokens?.text ?? "");
          })
        ),
      })
    );
  }
  body.appendChild(storedTable(section, { swatches: true }));
  return panel({ title, note, body, method });
}

/** What became of earlier work: one bar per share, over the lines it was measured on. */
function becameCard(section) {
  const title = t("review.section.became");
  const note = t("review.became.note");
  if (section.empty) {
    return panel({ title, note, body: storedEmpty(section.empty), method: methodNotes(section.notes ?? []) });
  }

  const rows = shareRows(section);
  const body = el("div", { class: "stack" });
  if (rows.length) {
    body.appendChild(
      shareBars({
        rows,
        caption: list(rows.map((one) => t("review.headline.section", one.label, one.text))),
      })
    );
    body.appendChild(
      el("div", { class: "legend" }, [
        el("span", { class: "key", text: t("review.coverageUnderlay") }),
      ])
    );
  }
  return panel({ title, note, body, method: methodNotes(section.notes ?? [], storedTable(section)) });
}

/** Each figure of the outcome section, with the value the engine printed for it. */
function shareRows(section) {
  return shares(section).map((one) => ({
    label: one.label,
    text: one.text,
    // A count is not a share and draws no bar, so `lines followed` is a figure with an
    // empty track rather than a bar the full width of the card.
    value: one.share ? one.value : null,
    underlay: one.share ? one.coverage : null,
    colour: /rework/i.test(one.label) ? "var(--o-rework)" : "var(--o-alive)",
    foot: one.coverageText ? t("chart.coverageIs", one.coverageText) : "",
  }));
}

/** Observations: the sentence in the reader's language, and the two sides as bars. */
function observationsCard(section, names) {
  const title = t("section.observations");
  const note = t("review.observations.note");
  const method = methodNotes(section.notes ?? []);
  if (section.empty) return panel({ title, note, body: storedEmpty(section.empty), method });

  const body = el("div", { class: "stack" });
  for (const pair of observationPairs(section)) {
    body.appendChild(observationBlock(pair, names));
  }

  // Design rule 3: the sentence above was composed from the review's own numbers, so
  // the engine's own English stays one click away as the thing to check it against.
  const stored = el("details", { class: "method" });
  stored.appendChild(el("summary", { text: t("review.observations.stored") }));
  stored.appendChild(storedTable(section));
  body.appendChild(stored);

  return panel({ title, note, body, method });
}

/**
 * Is this review over the whole store rather than one project?
 *
 * The engine writes the literal `all projects` into `app_review.project` when there is
 * no single one, so this is a comparison against an engine constant rather than a null
 * check. It is matched here in one place so the screen and its subtitle agree.
 */
export function wholeStore(project) {
  return project === null || project === undefined || String(project) === "all projects";
}

function observationBlock(pair, names) {
  // A review written before the engine stored the two group sizes has `withN === null`,
  // and composing from it printed "your null sessions that ran tests". The founder's own
  // review is one of those. Where the counts are missing the engine's own stored English
  // is the honest thing to show: it was written when the numbers were still there.
  const composable = pair.withN !== null && pair.withoutN !== null;
  const sentence = composable
    ? observationSentence({
        project: names.get(pair.repoKey) ?? pair.repoKey,
        repo_key: pair.repoKey,
        pooled: pair.repoKey === POOLED,
        fact: pair.fact,
        outcome: pair.outcome,
        with_n: pair.withN,
        without_n: pair.withoutN,
        with_value: pair.withValue,
        without_value: pair.withoutValue,
      })
    : pair.sentence;
  // One colour for both sides. Colour is which outcome is being measured, never which
  // side of the split came out higher: rule 2, and the reason the two bars are told
  // apart by their labels rather than by their ink.
  const colour = pair.outcome === "rework" ? "var(--o-rework)" : "var(--o-alive)";
  const sides = [
    {
      label: t("observation.side.did"),
      text: percent(pair.withValue),
      value: pair.withValue,
      colour,
      foot: pair.withN === null ? "" : sessionPhrase(pair.withN),
    },
    {
      label: t("observation.side.didNot"),
      text: percent(pair.withoutValue),
      value: pair.withoutValue,
      colour,
      foot: pair.withoutN === null ? "" : sessionPhrase(pair.withoutN),
    },
  ];
  const block = el("div", { class: "obs-block" }, [
    el("div", { class: "obs-sentence", text: sentence }),
    shareBars({
      rows: sides,
      caption: list(sides.map((side) => t("review.headline.section", side.label, side.text))),
    }),
  ]);
  if (pair.coverage !== null) {
    block.appendChild(
      el("div", { class: "coverage-chip", text: t("chart.coverageIs", percent(pair.coverage)) })
    );
  }
  return block;
}

/** Compared with the previous period: one card per figure, with the pair behind it. */
function comparedCard(section) {
  const title = t("review.section.compared");
  const note = t("review.compared.note");
  if (section.empty) {
    return panel({ title, note, body: storedEmpty(section.empty), method: methodNotes(section.notes ?? []) });
  }

  const grid = el("div", { class: "compare-grid" });
  for (const one of comparisons(section)) {
    const card = el("div", { class: "compare-card" }, [
      el("div", { class: "k", text: one.label }),
      el("div", { class: "v", text: one.nowText }),
      el("div", { class: "prev", text: t("compare.previous", one.previousText) }),
      el("span", { class: "chip", text: t("compare.change", one.changeText) }),
    ]);
    const pair = twin(one);
    if (pair) card.appendChild(pair);
    grid.appendChild(card);
  }
  return panel({ title, note, body: grid, method: methodNotes(section.notes ?? [], storedTable(section)) });
}

/**
 * The two periods as two small bars.
 *
 * Only when the review stored both as numbers. The prototype read them back out of the
 * printed text with a regular expression, which turns `713938k` into 713,938; a review
 * too old to carry `previous_value` gets no picture rather than a parsed one.
 */
function twin(one) {
  if (one.nowValue === null || one.previousValue === null) return null;
  const max = Math.max(Math.abs(one.nowValue), Math.abs(one.previousValue));
  if (!(max > 0)) return null;
  const wrap = el("div", { class: "twin" });
  // Which period, not which is better: the ink is fixed and does not answer to the
  // direction of the change (rule 2).
  for (const bar of [
    { value: one.previousValue, colour: "var(--text-3)", label: t("compare.previousShort") },
    { value: one.nowValue, colour: "var(--accent)", label: t("compare.nowShort") },
  ]) {
    const mark = document.createElement("i");
    mark.style.height = `${Math.max((Math.abs(bar.value) / max) * 20, 2)}px`;
    mark.style.background = bar.colour;
    mark.title = bar.label;
    wrap.appendChild(mark);
  }
  return wrap;
}

/** Last time's suggestions: the stored table, or the sentence saying there are none. */
function suggestionsCard(section) {
  const title = t("review.section.suggestions");
  const note = t("review.suggestions.note");
  const method = methodNotes(section.notes ?? []);
  if (section.empty) return panel({ title, note, body: storedEmpty(section.empty), method });
  return panel({ title, note, body: storedTable(section), method });
}

/** A section this build has no layout for: its stored table, and a line saying so. */
function unknownCard(section) {
  return panel({
    title: section.title ?? section.key,
    note: t("review.unknownSection"),
    body: section.empty ? storedEmpty(section.empty) : storedTable(section),
    method: methodNotes(section.notes ?? []),
  });
}

/** What a model made of the figures, and everything needed to judge it. */
function segmentCard(stored) {
  const card = el("div", { class: "card segment" }, [
    el("div", { class: "card-title", text: t("review.whatThisMeans") }),
  ]);
  const paragraphs = segmentParagraphs(stored);
  if (!paragraphs.length) {
    card.appendChild(el("p", { class: "panel-note", text: t("review.segment.none") }));
    return card;
  }
  for (const part of paragraphs) card.appendChild(el("p", { text: part }));
  card.appendChild(
    el("div", { class: "segment-foot" }, [
      el("span", {
        class: "chip",
        text: t("review.writtenBy", String(stored.segment_model ?? t("common.dash"))),
      }),
      el("span", { text: stamp(stored.segment_created_at) }),
      el("span", { text: t("review.segment.checked") }),
    ])
  );
  return card;
}

/* --- the screen ---------------------------------------------------------------------- */

/** One draw function per section key. A key not here is drawn from its stored table. */
const CARDS = {
  did: didCard,
  became: becameCard,
  compared: comparedCard,
  suggestions: suggestionsCard,
};

/**
 * Everything under the head, for one review.
 *
 * @param {any} data the whole payload, for the repository names an observation's key
 *   cannot supply on its own
 * @param {Record<string, any>|null} chosenReview
 * @param {string|null} project the project picker's answer, which scoped the list
 */
export function reviewCards(data, chosenReview, project) {
  if (!chosenReview) {
    return [
      project === null
        ? emptyState(t("review.empty.title"), t("review.empty.detail"))
        : emptyState(
            t("review.emptyForProject.title", project),
            t("review.emptyForProject.detail", project)
          ),
    ];
  }

  const { readable, sections, figures } = bodyOf(chosenReview);
  const out = [headlineCard(chosenReview, figures)];
  if (!readable) {
    out.push(emptyState(t("review.unreadable.title"), t("review.unreadable.detail")));
    return out;
  }

  const names = projectNames(data, chosenReview);
  for (const section of sections) {
    if (section.key === "observations") out.push(observationsCard(section, names));
    else if (CARDS[section.key]) out.push(CARDS[section.key](section));
    else out.push(unknownCard(section));
  }

  out.push(segmentCard(chosenReview));
  if (figures !== null) {
    out.push(el("p", { class: "provenance", text: t("review.provenance", count(figures)) }));
  }
  return out;
}

/**
 * @param {import("./screens.js").ScreenState} state
 * @returns {Element}
 */
export function review(state) {
  const { data, project } = state;
  const screen = el("div", { class: "screen-body" });

  // The project picker scopes the list. The range picker does not: a stored review
  // carries its own two windows, and dropping one for being older than the charts look
  // back would hide the record rather than filter it.
  const stored = reviewsFor(data, { project });

  const note = el("div", { class: "screen-note" });
  note.hidden = true;
  const button = el("button", { class: "btn primary", type: "button", text: t("menu.reviewNow") });
  button.addEventListener("click", () => {
    if (REVIEW_NOW.run) {
      REVIEW_NOW.run();
      return;
    }
    note.textContent = t("review.notWired");
    note.hidden = false;
  });

  const head = el("div", { class: "review-head" });
  const body = el("div", { class: "stack" });

  // Which review is shown is this screen's own business and lives in the tree it is
  // building, not in module state: a redraw from the window starts at the newest review
  // again, which is the right answer after an ingest and is what the page contract's
  // "keeps no state between renders" asks for.
  const draw = (id) => {
    body.innerHTML = "";
    for (const node of reviewCards(data, chosen(stored, id), project)) body.appendChild(node);
  };

  if (stored.length > 1) {
    const select = /** @type {HTMLSelectElement} */ (
      el("select", { class: "select", "aria-label": t("review.picker") })
    );
    for (const row of stored) {
      select.appendChild(
        el("option", {
          value: String(row.id),
          text: t("review.option", String(row.id), formatDay(String(row.range_end).slice(0, 10))),
        })
      );
    }
    select.value = String(stored[0].id);
    select.addEventListener("change", () => draw(select.value));
    head.appendChild(select);
  }
  head.appendChild(button);
  screen.appendChild(head);
  screen.appendChild(note);

  /* Whether writing one now would produce anything, above the one that is stored.
     Hidden until the engine answers: it is a subprocess, and an empty line reserving
     space for a sentence nobody has said yet is worse than the sentence arriving. */
  const ready = el("div", { class: "screen-note readiness" });
  ready.hidden = true;
  screen.appendChild(ready);
  if (REVIEW_NOW.readiness) {
    // Through `store/readiness.js`, which decides when the engine is asked at all: asking
    // on every draw closes a loop with the store watcher, and that file holds the story.
    readiness(data, () => /** @type {() => Promise<any>} */ (REVIEW_NOW.readiness)())
      .then((found) => {
        const said = readinessSentence(found);
        if (!said) return;
        ready.textContent = said;
        // The engine's own English line, under the pointer, to check the composed one by.
        ready.title = readinessSource(found);
        ready.hidden = false;
      })
      // Silent, and deliberately: a Review screen that cannot reach the engine still has
      // the stored review on it, which is the thing the screen is for. `wiring.js` writes
      // the reason to the shell's standard error.
      .catch(() => {});
  }

  draw(null);
  screen.appendChild(body);
  return screen;
}
