/* The Review screen, and what it reads.
 *
 * The rows come from the same fixture store `test/sentences.test.mjs` uses, read with
 * `sqlite3` so the test depends on no driver. They are the engine's own output, so a
 * test here fails when the engine changes shape, which is the point: this screen prints
 * the engine's numbers and nothing else, and a fixture written by hand would only
 * confirm what this file already believes.
 *
 * The synthetic rows below are the three states the fixture cannot show, each of which
 * the founder's own store has: a null coverage, sections that will not parse, and a
 * store that has never been reviewed.
 *
 *     pnpm test
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { installDom } from "./dom.mjs";

installDom();

const here = dirname(fileURLToPath(import.meta.url));
const app = join(here, "..");
const FIXTURE = join(app, "fixtures/store.db");

const { readPayload } = await import("../src/store/payload.js");
const Str = await import("../src/text/strings.js");
const { observationSentence } = await import("../src/text/sentences.js");
const {
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
} = await import("../src/store/review.js");
// `any`, deliberately: the tree the screen returns is the shim's, and asking it for
// `find` is the whole point of the shim. Typing it as `Element` would be a lie.
const { REVIEW_NOW, review, reviewCards } = /** @type {any} */ (
  await import("../src/ui/review.js")
);
const { forget } = /** @type {any} */ (await import("../src/store/readiness.js"));

for (const language of Str.LANGUAGES) {
  Str.load(
    language,
    JSON.parse(readFileSync(join(app, `src/text/strings.${language}.json`), "utf8"))
  );
}
Str.setLang("en");

/** One view of the fixture store, as arrays of objects. */
function rows(view) {
  const out = execFileSync("sqlite3", ["-json", FIXTURE, `SELECT * FROM ${view};`], {
    encoding: "utf8",
  }).trim();
  return out ? JSON.parse(out) : [];
}

const data = readPayload({
  reviews: rows("app_review"),
  observations: rows("app_observation"),
  projects: [],
});

/** The whole state a screen is handed, with only what this screen reads filled in. */
function state(over = {}) {
  return {
    data,
    info: {},
    project: null,
    range: "8w",
    week: null,
    onWeek: () => {},
    redraw: () => {},
    ...over,
  };
}

/** Every text in a rendered tree, as one string, for "does the page say X". */
function textOf(node) {
  return node.textContent;
}

test("the fixture carries two stored reviews with every section filled", () => {
  assert.equal(data.reviews.length, 2, "the fixture should hold two reviews");
  for (const row of data.reviews) {
    assert.ok(Array.isArray(row.sections), "sections should arrive parsed");
    assert.ok(Array.isArray(row.numbers), "numbers should arrive parsed");
  }
  assert.deepEqual(
    data.reviews[0].sections.map((section) => section.key),
    ["did", "became", "observations", "compared", "suggestions"]
  );
});

/* --- what the reader selects --------------------------------------------------------- */

test("the project picker scopes the list and keeps the view's order", () => {
  assert.deepEqual(
    reviewsFor(data, { project: null }).map((row) => row.id),
    [2, 1],
    "newest first, as app_review orders them"
  );
  assert.deepEqual(
    reviewsFor(data, { project: "alpha" }).map((row) => row.id),
    [1],
    "only the review scoped to that project"
  );
  assert.deepEqual(reviewsFor(data, { project: "nobody" }), []);
});

test("the chosen review is the one asked for, and the newest when none is", () => {
  const list = reviewsFor(data, {});
  assert.equal(chosen(list, null).id, 2);
  assert.equal(chosen(list, "1").id, 1, "the select's value is a string");
  assert.equal(chosen(list, 99).id, 2, "an id that is gone falls back to the newest");
  assert.equal(chosen([], null), null);
});

test("a review whose sections will not parse is unreadable, not empty", () => {
  const broken = readPayload({ reviews: [{ id: 3, sections: "{oops", numbers: "[" }] });
  const body = bodyOf(broken.reviews[0]);
  assert.equal(body.readable, false);
  assert.deepEqual(body.sections, []);
  assert.equal(body.figures, null, "an unreadable numbers list is unknown, not zero");

  const none = bodyOf({ id: 4, sections: [], numbers: [] });
  assert.equal(none.readable, true, "a review that found nothing is still readable");
  assert.equal(none.figures, 0);
});

/* --- the figures, as the engine formatted them ---------------------------------------- */

const first = reviewsFor(data, { project: "alpha" })[0];
const sectionOf = (key) => bodyOf(first).sections.find((section) => section.key === key);
const did = sectionOf("did");
const became = sectionOf("became");
const observations = sectionOf("observations");
const compared = sectionOf("compared");

test("the purpose mix is the engine's values, bucketed by the fixed purpose list", () => {
  const mix = purposeTokens(did);
  assert.equal(mix.development, 18320);
  assert.equal(mix.research, 5080);
  assert.equal(mix.debugging, 2040);
  assert.equal(mix.conversation, 0, "a purpose the review did not measure is absent, not null");
  // The total is the engine's own `did.tokens`, never a sum made here: the app owns no
  // numbers, and the composition bar takes its own denominator.
  assert.equal(numbersOf(did).get("did.tokens").text, "25k");
});

test("a purpose this build has not heard of folds into other rather than being dropped", () => {
  const mix = purposeTokens({
    key: "did",
    numbers: [
      { key: "did.tokens.development", value: 10 },
      { key: "did.tokens.vibecoding", value: 7 },
    ],
  });
  assert.equal(mix.unknown, 7);
  assert.equal(mix.development, 10);
});

test("a count in the outcome section draws no bar; a share does", () => {
  const out = shares(became);
  const byLabel = Object.fromEntries(out.map((one) => [one.label, one]));
  assert.equal(byLabel["lines followed"].share, false, "400 lines is not a share");
  assert.equal(byLabel["lines followed"].text, "400");
  assert.equal(byLabel["alive at 30 days"].share, true);
  assert.equal(byLabel["alive at 30 days"].value, 0.74);
  // The denominator the engine printed with the share. Every share carries what it is
  // over, and here that is the engine's own text rather than anything recomputed.
  assert.equal(byLabel["alive at 30 days"].text, "74% (260)");
  assert.equal(byLabel["alive at 30 days"].coverageText, "88%");
});

test("the two sides of an observation are paired by key, never by position", () => {
  const pairs = observationPairs(observations);
  assert.equal(pairs.length, 2);
  assert.deepEqual(
    pairs.map((one) => [one.fact, one.outcome, one.withN, one.withoutN]),
    [
      ["test_runs", "rework", 7, 9],
      ["sittings", "alive_head", 6, 11],
    ]
  );

  // A review whose two entries do not name the same split loses its bars and keeps its
  // table, rather than drawing one observation's value against another's.
  const mismatched = observationPairs({
    key: "observations",
    rows: [["a sentence", "a caveat"]],
    numbers: [
      { key: "observation.alpha|test_runs|rework.with", value: 0.1, with_n: 1, without_n: 2 },
      { key: "observation.alpha|sittings|rework.without", value: 0.2 },
    ],
  });
  assert.deepEqual(mismatched, []);
});

test("the comparison takes both periods from the engine, never from the printed text", () => {
  const out = comparisons(compared);
  const tokens = out.find((one) => one.label === "tokens");
  assert.equal(tokens.nowText, "25k");
  assert.equal(tokens.nowValue, 25440, "the engine's value, not 25 read back out of `25k`");
  assert.equal(tokens.previousValue, 19120);

  const alive = out.find((one) => one.label === "alive at 7 days");
  assert.equal(alive.previousText, "-", "the engine's dash, printed as stored");
  assert.equal(alive.previousValue, null, "a dash is unknown, never zero");
});

test("a review too old to carry the previous value gets no comparison bars", () => {
  const out = comparisons({
    key: "compared",
    rows: [["sessions", "4", "0", "+4"]],
    numbers: [{ key: "compared.sessions.now", text: "4", value: null }],
  });
  assert.equal(out[0].nowValue, null);
  assert.equal(out[0].previousValue, null);
});

test("a model segment is split into its own paragraphs, and an absent one is no paragraphs", () => {
  assert.deepEqual(segmentParagraphs({ segment_text: "one\n\n\ntwo\n" }), ["one", "two"]);
  assert.deepEqual(segmentParagraphs({ segment_text: "   " }), []);
  assert.deepEqual(segmentParagraphs({}), []);
});

/* --- design rule 3: the sentence is composed, and the engine's is the answer key ------ */

test("the observation sentence composed from a review's own numbers is the stored one", () => {
  Str.setLang("en");
  const names = projectNames(data, first);
  const wrong = [];
  for (const pair of observationPairs(observations)) {
    const ours = observationSentence({
      project: names.get(pair.repoKey) ?? pair.repoKey,
      repo_key: pair.repoKey,
      pooled: pair.repoKey === "*",
      fact: pair.fact,
      outcome: pair.outcome,
      with_n: pair.withN,
      without_n: pair.withoutN,
      with_value: pair.withValue,
      without_value: pair.withoutValue,
    });
    if (ours !== pair.sentence) wrong.push({ ours, engine: pair.sentence });
  }
  assert.deepEqual(
    wrong,
    [],
    wrong.map((one) => `\n  ours:   ${one.ours}\n  engine: ${one.engine}`).join("")
  );
});

/* --- the screen ----------------------------------------------------------------------- */

test("a store that has never been reviewed says what to do, and draws no card", () => {
  Str.setLang("en");
  const screen = review(state({ data: readPayload({ reviews: [] }) }));
  const empty = screen.find(".empty-title");
  assert.equal(empty.textContent, Str.t("review.empty.title"));
  assert.match(screen.find(".empty-detail").textContent, /prudence review/);
  assert.equal(screen.find(".card"), null, "nothing pretends to be a review");
  assert.equal(screen.find("select"), null, "no picker for a list of none");
});

test("a project with no review of its own says so, and says the others are still there", () => {
  const screen = review(state({ project: "nobody" }));
  assert.equal(screen.find(".empty-title").textContent, Str.t("review.emptyForProject.title", "nobody"));
  assert.match(screen.find(".empty-detail").textContent, /All projects/);
});

test("the picker appears only when there is more than one review to choose between", () => {
  assert.ok(review(state()).find("select"), "two reviews, a picker");
  assert.equal(review(state({ project: "alpha" })).find("select"), null, "one review, none");
});

test("choosing an earlier review redraws the cards and nothing else", () => {
  const screen = review(state());
  const select = screen.find("select");
  // Against the card's own title, not against the page text: the picker lists every
  // review by name, so /Review 2/ matches whatever the cards below it are showing. The
  // first version of this test asserted on the page text and passed with the body
  // emptied entirely.
  const cardTitle = () => screen.findAll(".card-title").map((node) => node.textContent);

  assert.ok(
    cardTitle().some((title) => title.startsWith("Review 2,")),
    `expected review 2's card, saw ${JSON.stringify(cardTitle())}`
  );
  select.value = "1";
  select.fire("change");
  assert.ok(
    cardTitle().some((title) => title.startsWith("Review 1,")),
    `expected review 1's card, saw ${JSON.stringify(cardTitle())}`
  );
  assert.equal(
    cardTitle().some((title) => title.startsWith("Review 2,")),
    false,
    "one review at a time"
  );
  assert.ok(screen.find("select"), "the picker survives its own change");
});

test("the head states the two windows separately and does not conflate them", () => {
  const cards = reviewCards(data, first, "alpha");
  const sub = cards[0].find(".card-sub").textContent;
  // 1 to 8 September is the period reviewed; 25 August to 1 September is the window the
  // outcomes were measured over. Both, in that order, in one composed sentence.
  assert.match(sub, /Sep 1, 2026/);
  assert.match(sub, /Sep 8, 2026/);
  assert.match(sub, /Aug 25, 2026/);
  assert.notEqual(
    String(first.range_start).slice(0, 10),
    String(first.outcome_range_start).slice(0, 10),
    "the fixture's two windows really are different, or this test proves nothing"
  );
});

test("a null coverage is a dash, never a zero and never a blank", () => {
  const withoutCoverage = { ...first, coverage: null };
  const meta = reviewCards(data, withoutCoverage, null)[0].findAll(".v");
  assert.ok(
    meta.some((node) => node.textContent === Str.t("common.dash")),
    `expected a dash among ${meta.map((n) => n.textContent).join(", ")}`
  );
  assert.ok(!meta.some((node) => node.textContent === "0%"), "a missing figure is not zero");
  // And the figure the engine did compute is still printed, from its own section.
  assert.equal(numbersOf(did).get("did.coverage").text, "91%");
});

test("the engine's dash survives into the table it is printed in", () => {
  const section = {
    key: "did",
    title: "What you did",
    headers: ["purpose", "sessions", "tokens", "active h"],
    rows: [["conversation", "2", "-", "0.0"]],
    notes: [],
    numbers: [],
    empty: null,
  };
  const card = reviewCards(
    data,
    { ...first, sections: [section], numbers: [] },
    null
  )[1];
  const cells = card.findAll("td").map((node) => node.textContent);
  assert.ok(cells.includes("-"), `expected the engine's dash in ${cells.join(" | ")}`);
  assert.ok(!cells.includes("0"), "a dash is never turned into a zero");
});

test("a review whose body cannot be read still shows its row, and says which part failed", () => {
  const broken = readPayload({
    reviews: [{ ...first, sections: "{oops", numbers: "[" }],
  }).reviews[0];
  const cards = reviewCards(data, broken, null);
  assert.equal(cards.length, 2, "the head, and the sentence saying the body is unreadable");
  assert.match(textOf(cards[0]), /Review 1/, "the row above is still true");
  assert.equal(cards[1].find(".empty-title").textContent, Str.t("review.unreadable.title"));
});

test("a section this build has no layout for is drawn from its stored table", () => {
  const section = {
    key: "whatever_comes_next",
    title: "Something new",
    headers: ["a", "b"],
    rows: [["one", "two"]],
    notes: [],
    numbers: [],
    empty: null,
  };
  const card = reviewCards(data, { ...first, sections: [section], numbers: [] }, null)[1];
  assert.equal(card.find("h2").textContent, "Something new");
  assert.match(textOf(card), /one/);
  assert.match(textOf(card.find(".panel-note")), /does not lay out/);
});

test("a section that found nothing prints the engine's own sentence, and no table", () => {
  const section = {
    key: "became",
    title: "What became of earlier work",
    headers: [],
    rows: [],
    notes: ["Commits made between A and B."],
    numbers: [],
    empty: "No commit in that span is credited with a line that could be followed.",
  };
  const card = reviewCards(data, { ...first, sections: [section], numbers: [] }, null)[1];
  assert.equal(card.find(".empty-detail").textContent, section.empty);
  assert.equal(card.find("table"), null);
});

/* --- rule 2: colour is identity, never judgement -------------------------------------- */

test("both sides of an observation carry one colour, whichever side came out higher", () => {
  const card = reviewCards(data, first, "alpha").find(
    (node) => node.find("h2")?.textContent === Str.t("section.observations")
  );
  const blocks = card.findAll(".obs-block");
  assert.equal(blocks.length, 2);
  // The marks are SVG since the bars moved to `design/charts.js`: the ink of a side is
  // its rectangle's `fill`, and the track behind it is not a side.
  const inksOf = (block) =>
    block
      .findAll("rect")
      .map((node) => node.getAttribute("fill"))
      .filter((fill) => fill !== "var(--surface-sunken)" && fill !== "var(--coverage)");
  for (const block of blocks) {
    const inks = inksOf(block);
    assert.equal(inks.length, 2);
    assert.equal(inks[0], inks[1], "the two sides of a split are not coloured against each other");
  }
  // The colour says which outcome is being measured. `test_runs` is a rework row and
  // `sittings` an alive row, so the two blocks differ and neither is a verdict.
  assert.equal(inksOf(blocks[0])[0], "var(--o-rework)");
  assert.equal(inksOf(blocks[1])[0], "var(--o-alive)");
});

test("the comparison's two bars keep their ink whichever way the change went", () => {
  const section = {
    key: "compared",
    title: "Compared with the previous period",
    headers: ["figure", "this period", "previous period", "change"],
    rows: [
      ["sessions", "9", "3", "+6"],
      ["active hours", "3.0", "9.0", "-6.0"],
    ],
    notes: [],
    numbers: [
      { key: "compared.sessions.now", text: "9", value: 9, previous_value: 3 },
      { key: "compared.active_hours.now", text: "3.0", value: 3, previous_value: 9 },
    ],
    empty: null,
  };
  const card = reviewCards(data, { ...first, sections: [section], numbers: [] }, null)[1];
  const cards = card.findAll(".compare-card");
  assert.equal(cards.length, 2);
  for (const one of cards) {
    const inks = one.findAll(".twin")[0].children.map((bar) => bar.style.background);
    assert.deepEqual(
      inks,
      ["var(--text-3)", "var(--accent)"],
      "previous then now, the same ink whether the figure rose or fell"
    );
  }
});

/* --- the method is stated -------------------------------------------------------------- */

test("every card states its method for a reader and keeps the engine's notes behind it", () => {
  const cards = reviewCards(data, first, "alpha");
  const panels = cards.filter((node) => node.className.includes("panel"));
  assert.equal(panels.length, 5, "one card per section");
  for (const panel of panels) {
    const note = panel.find(".panel-note");
    assert.ok(note && note.textContent.length > 20, `${panel.find("h2").textContent} has no caption`);
    const summaries = panel.findAll(".method").map((node) => node.find("summary").textContent);
    assert.ok(
      summaries.includes(Str.t("chart.method")),
      `${panel.find("h2").textContent} folds the engine's own notes nowhere`
    );
  }
});

/* A caption borrowed from another screen has to be the same measure, not just the same
   word. The Review's `did.commits` is the commits credited to the period's sessions;
   the Overview's "Commits in range" is the commits made on the days of a range, and on
   the founder's own review 1 those are 18 and 32. This is the list of captions this
   screen shares with the Overview, and why each one is the same question. */
const SHARED_CAPTIONS = {
  // `did.sessions` used to be here, borrowing the Overview's "Sessions in range" for a card
  // that has no range. It has its own key now (`review.did.sessions`), and the Overview's
  // captions have gone with the three cards that carried them: its figures say "22
  // sessions" and its summary line says what window that is over.
  "did.hours": "overview.activeHours",
};

test("a stat caption borrowed from another screen is the same measure", () => {
  const source = readFileSync(join(app, "src/ui/review.js"), "utf8");
  const stats = [...source.matchAll(/\["(did\.[a-z]+)", t\("([^"]+)"\)/g)];
  assert.equal(stats.length, 4, "the activity card shows four figures");
  for (const [, figure, caption] of stats) {
    if (caption.startsWith("review.")) continue;
    assert.equal(
      SHARED_CAPTIONS[figure],
      caption,
      `${figure} is captioned with ${caption}, which belongs to another screen. If the ` +
        "two are the same measure, add the pair above with the reason; if they are not, " +
        "this screen needs its own key."
    );
  }
});

test("the page closes with the count of figures the engine says it rests on", () => {
  const cards = reviewCards(data, first, "alpha");
  const last = cards[cards.length - 1];
  assert.ok(last.className.includes("provenance"));
  assert.match(last.textContent, new RegExp(String(first.numbers.length)));
});

/* --- the action ------------------------------------------------------------------------- */

test("Review now says where the action is until the wiring sets it", () => {
  REVIEW_NOW.run = null;
  const screen = review(state());
  const note = screen.find(".screen-note");
  assert.equal(note.hidden, true, "it says nothing until it is pressed");
  screen.find("button").fire("click");
  assert.equal(note.hidden, false);
  assert.equal(note.textContent, Str.t("review.notWired"));
});

test("Review now calls the wiring once it is there, and says nothing itself", () => {
  let ran = 0;
  REVIEW_NOW.run = () => {
    ran += 1;
  };
  try {
    const screen = review(state());
    screen.find("button").fire("click");
    assert.equal(ran, 1);
    assert.equal(screen.find(".screen-note").hidden, true);
  } finally {
    REVIEW_NOW.run = null;
  }
});

/* --- whether writing one now would produce anything ---------------------------------------
 *
 * The line above the stored review, composed from the engine's numbers in the reader's
 * own language whether or not a review is ready. The engine's own English sentence, when it
 * printed one, is the line's `title`: there to check the composed one against, and not in
 * the middle of a Chinese screen.
 */

const settled = () => new Promise(setImmediate);

async function withReadiness(answer) {
  // The answer is remembered against the store it was taken for, and every case here
  // draws the same store.
  forget();
  REVIEW_NOW.readiness = () => Promise.resolve(answer);
  try {
    const screen = review(state());
    await settled();
    return screen.find(".readiness");
  } finally {
    REVIEW_NOW.readiness = null;
  }
}

test("a review that is ready is said in the reader's language, from the engine's numbers", async () => {
  const said = "A review is ready: 151 new sessions so far and 697 commits crossed their 7-day mark.";
  const answer = {
    ready: true,
    sentence: said,
    newSessions: 151,
    requiredSessions: 5,
    maturedCommits: 697,
    requiredCommits: 1,
  };
  const line = await withReadiness(answer);
  assert.equal(line.hidden, false, "the line stayed hidden with an answer in hand");
  assert.equal(line.textContent, "A review is ready: 151 new sessions so far and 697 commits matured.");
  assert.equal(line.title, said, "the engine's own sentence is not kept to check against");

  Str.setLang("zh-Hans");
  try {
    const chinese = await withReadiness(answer);
    assert.equal(chinese.textContent, "可以写一次回顾了：目前有 151 个新会话，697 次提交已成熟。");
    assert.equal(chinese.title, said);
  } finally {
    Str.setLang("en");
  }
});

test("a review that is not ready says what is still needed, from the engine's numbers", async () => {
  const line = await withReadiness({
    ready: false,
    newSessions: 2,
    requiredSessions: 5,
    maturedCommits: 0,
    requiredCommits: 1,
  });
  assert.equal(line.textContent, Str.t("review.readiness.needs", "2", "5", "0", "1"));
  // The numbers are the engine's, and the sentence is the reader's.
  Str.setLang("zh-Hans");
  try {
    const chinese = await withReadiness({
      ready: false,
      newSessions: 2,
      requiredSessions: 5,
      maturedCommits: 0,
      requiredCommits: 1,
    });
    assert.equal(chinese.textContent, Str.tIn("zh-Hans", "review.readiness.needs", "2", "5", "0", "1"));
    assert.equal(chinese.textContent.includes("Not enough"), false);
  } finally {
    Str.setLang("en");
  }
});

/* An engine that does not answer the question gets no line. "Not ready" on no answer would
   be the screen inventing a verdict, and a review it declined to write is the one thing
   this line exists to explain. */
test("no answer is no line, and the stored review is still drawn", async () => {
  const line = await withReadiness(null);
  assert.equal(line.hidden, true);
  assert.equal(line.textContent, "");

  forget();
  REVIEW_NOW.readiness = null;
  const screen = review(state());
  await settled();
  assert.equal(screen.find(".readiness").hidden, true, "a line was drawn with no seam at all");
  assert.ok(screen.find(".card"), "the stored review is not on the screen");
});

/* --- the strings ------------------------------------------------------------------------- */

test("every key this screen asks for is in both tables", () => {
  const source = [
    readFileSync(join(app, "src/ui/review.js"), "utf8"),
    readFileSync(join(app, "src/store/review.js"), "utf8"),
  ].join("\n");
  const keys = [...source.matchAll(/\bt\(\s*"([^"]+)"/g)].map((match) => match[1]);
  assert.ok(keys.length > 20, `only found ${keys.length} keys in the screen`);
  for (const language of Str.LANGUAGES) {
    for (const key of keys) {
      assert.notEqual(
        Str.tIn(language, key),
        key,
        `${key} is missing from ${language}; add it to Scripts/strings.py`
      );
    }
  }
});

test("the screen draws in Chinese without falling back to a key", () => {
  Str.setLang("zh-Hans");
  try {
    const screen = review(state());
    const text = textOf(screen);
    assert.match(text, /回顾/, "the Chinese table is in use");
    assert.doesNotMatch(text, /review\.[a-z]+\./i, "a key leaked into the page");
  } finally {
    Str.setLang("en");
  }
});
