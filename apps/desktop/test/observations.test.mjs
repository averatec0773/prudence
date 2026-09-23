/* The Observations screen, and the reader under it.
 *
 * These guard requirements, not shapes. In order: the scope rule (a pooled row is never
 * filtered out), the order (presentation, and stated), the two floors the empty state
 * has to explain, the threshold on a store that predates `threshold_op`, and the four
 * design rules as far as a test can reach them: no colour keyed to `direction`, every
 * share with the n it is over, the method stated, the numbers only ever the engine's.
 *
 * The screen is exercised against a small DOM of this file's own. There is no jsdom in
 * this project and there is not going to be one: `design/dom.js` uses five methods, and
 * a stub of five methods is cheaper to read than a dependency, and it makes the rule
 * "a screen returns one element and appends nothing to the page" checkable.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import * as Str from "../src/text/strings.js";
import { forScope, gap, groupsOf, isPooled, projectOf, scoped } from "../src/store/observations.js";

const here = dirname(fileURLToPath(import.meta.url));
const app = join(here, "..");
const FIXTURE = join(app, "fixtures/store.db");

for (const language of Str.LANGUAGES) {
  Str.load(
    language,
    JSON.parse(readFileSync(join(app, `src/text/strings.${language}.json`), "utf8"))
  );
}
Str.setLang("en");

/* --- a DOM, in as many lines as `design/dom.js` actually uses ----------------------- */

class Node {
  constructor(name) {
    this.nodeName = name;
    this.className = "";
    this.attributes = {};
    this.children = [];
    this.style = {};
    this.listeners = [];
    this.own = "";
  }

  appendChild(child) {
    this.children.push(child);
    return child;
  }

  setAttribute(name, value) {
    if (name === "class") this.className = String(value);
    else this.attributes[name] = String(value);
  }

  getAttribute(name) {
    return name === "class" ? this.className : (this.attributes[name] ?? null);
  }

  addEventListener(name, handler) {
    this.listeners.push([name, handler]);
  }

  set textContent(value) {
    this.own = String(value);
    this.children = [];
  }

  get textContent() {
    return this.own + this.children.map((child) => child.textContent).join("");
  }

  /** Every descendant carrying a class, the one thing these tests look things up by. */
  all(className) {
    const out = [];
    const walk = (node) => {
      if (String(node.className).split(/\s+/).includes(className)) out.push(node);
      for (const child of node.children) walk(child);
    };
    walk(this);
    return out;
  }

  tagged(name) {
    const out = [];
    const walk = (node) => {
      if (node.nodeName === name) out.push(node);
      for (const child of node.children) walk(child);
    };
    walk(this);
    return out;
  }
}

// `any`, because this is five methods of a DOM and not a DOM. `tsc` checks the modules
// under test against the real `lib.dom` types; it has nothing to gain from checking the
// stub they are handed here against them too.
globalThis.document = /** @type {any} */ ({
  createElement: (name) => new Node(name),
  createElementNS: (_ns, name) => new Node(name),
  createTextNode: (text) => {
    const node = new Node("#text");
    node.own = String(text);
    return node;
  },
  documentElement: { setAttribute() {} },
});

const { observations, shortLabel, thresholdLine } = await import(
  "../src/ui/observations.js"
);

/* --- rows ---------------------------------------------------------------------------- */

/** One row of `app_observation`, with the columns a contract 3 store answers with. */
function row(over = {}) {
  return {
    repo_key: "root:beatos",
    project: "beatos",
    pooled: 0,
    fact: "compactions",
    threshold_text: "compactions > 0",
    outcome: "alive_head",
    direction: "lower",
    with_n: 16,
    without_n: 33,
    with_value: 0.73,
    without_value: 0.93,
    coverage: 0.92,
    fact_commits: 642,
    inferred_commits: 25,
    fact_version: 1,
    observation_id: 1,
    sentence: "",
    threshold_value: 0,
    threshold_op: ">",
    ...over,
  };
}

/** The screen, as the `Node` above rather than as the `Element` the contract declares. */
function screenFor(rows, project = null, status = { observation_fact_version: 1 }) {
  return /** @type {any} */ (
    observations({
      data: { observations: rows, status, contract: 3 },
      info: null,
      project,
      range: "30d",
      bucket: null,
      onBucket() {},
      redraw() {},
    })
  );
}

/* --- the scope ------------------------------------------------------------------------ */

test("a pooled row survives a project filter, because it is the only answer there is", () => {
  const rows = [
    row({ repo_key: "root:beatos", project: "beatos", fact: "compactions" }),
    row({ repo_key: "root:other", project: "other", fact: "test_runs" }),
    row({ repo_key: "*", project: null, pooled: 1, fact: "sittings" }),
  ];
  assert.deepEqual(
    forScope(rows, "beatos").map((one) => one.fact),
    ["compactions", "sittings"]
  );
  assert.deepEqual(
    forScope(rows, null).map((one) => one.fact),
    ["compactions", "test_runs", "sittings"]
  );
});

test("a row is pooled by its flag or by its key, and belongs to no project either way", () => {
  assert.equal(isPooled(row({ pooled: 1, repo_key: "root:beatos" })), true);
  assert.equal(isPooled(row({ pooled: 0, repo_key: "*" })), true);
  assert.equal(projectOf(row({ pooled: 1, project: "beatos" })), null);
  // No project name in the view: the key is what there is, and it is printed rather
  // than left blank.
  assert.equal(projectOf(row({ project: null, repo_key: "root:x" })), "root:x");
});

test("the pooled rows and each project's own come out separately, projects in name order", () => {
  const found = scoped({
    observations: [
      row({ repo_key: "root:zeta", project: "zeta" }),
      row({ repo_key: "root:alpha", project: "alpha" }),
      row({ repo_key: "*", project: null, pooled: 1 }),
    ],
  });
  assert.equal(found.pooled.length, 1);
  // Alphabetical, not by gap: ordering the projects by their observations would rank
  // the projects, which is a score by another name.
  assert.deepEqual(
    found.projects.map((one) => one.project),
    ["alpha", "zeta"]
  );
});

/* --- the order ------------------------------------------------------------------------ */

test("cards come widest gap first, and a card's place is its largest gap", () => {
  const groups = groupsOf([
    row({ fact: "compactions", outcome: "alive_head", with_value: 0.5, without_value: 0.62 }),
    row({ fact: "compactions", outcome: "rework", with_value: 0.1, without_value: 0.5 }),
    row({ fact: "test_runs", outcome: "alive_head", with_value: 0.2, without_value: 0.45 }),
  ]);
  // compactions' largest gap is 0.40 and test_runs' is 0.25, so the card with the one
  // interesting bar leads even though its other bar is the narrowest of the three.
  assert.deepEqual(
    groups.map((one) => one.fact),
    ["compactions", "test_runs"]
  );
  // And inside a card, the same rule.
  assert.deepEqual(
    groups[0].rows.map((one) => one.outcome),
    ["rework", "alive_head"]
  );
});

test("two rows of one behaviour meet only when they are about the same scope", () => {
  const groups = groupsOf([
    row({ repo_key: "root:beatos", project: "beatos", fact: "compactions" }),
    row({ repo_key: "*", project: null, pooled: 1, fact: "compactions" }),
  ]);
  assert.equal(groups.length, 2, "a project's own row must never join a pooled one");
});

test("a row with an unreadable median sorts last rather than poisoning the order", () => {
  const groups = groupsOf([
    row({ fact: "broken", with_value: null, without_value: null }),
    row({ fact: "compactions", with_value: 0.2, without_value: 0.4 }),
  ]);
  assert.equal(gap(row({ with_value: null })), null);
  assert.deepEqual(
    groups.map((one) => one.fact),
    ["compactions", "broken"]
  );
});

test("the same rows in any order draw the same page", () => {
  const rows = [
    row({ fact: "compactions", with_value: 0.2, without_value: 0.4 }),
    row({ fact: "test_runs", with_value: 0.1, without_value: 0.3 }),
    row({ fact: "sittings", with_value: 0.5, without_value: 0.7 }),
  ];
  const first = groupsOf(rows).map((one) => one.key);
  const second = groupsOf([...rows].reverse()).map((one) => one.key);
  assert.deepEqual(first, second, "three equal gaps must not depend on the row order");
});

/* --- the threshold, on both contracts --------------------------------------------------- */

test("contract 3 words the threshold itself, in the reader's language", () => {
  Str.setLang("en");
  assert.equal(thresholdLine(row({ threshold_op: ">", threshold_value: 2 })), "more than 2");
  assert.equal(thresholdLine(row({ threshold_op: ">=", threshold_value: 3 })), "at least 3");
  assert.equal(thresholdLine(row({ threshold_op: "==", threshold_value: 1 })), "exactly 1");
  // A rate is printed as the engine chose it, not rounded. "more than 5.2" states a
  // split that never ran: a session at 5.19 prompts an hour is on the with-side while
  // the card says it is not.
  assert.equal(
    thresholdLine(row({ threshold_op: ">", threshold_value: 5.17369 })),
    "more than 5.17369"
  );
  Str.setLang("zh-Hans");
  assert.equal(thresholdLine(row({ threshold_op: ">", threshold_value: 2 })), "多于 2");
  Str.setLang("en");
});

test("contract 3 words the threshold for the two newest waste facts", () => {
  // test_fix_loops and giant_turns are both `at_least` splits (observations.py SPLITS),
  // so the generic operator/value words already cover them; this pins their own numbers.
  assert.equal(
    thresholdLine(row({ fact: "test_fix_loops", threshold_op: ">=", threshold_value: 5 })),
    "at least 5"
  );
  assert.equal(
    thresholdLine(row({ fact: "giant_turns", threshold_op: ">=", threshold_value: 1 })),
    "at least 1"
  );
});

test("a row with no number for its split prints the engine's own words", () => {
  assert.equal(
    thresholdLine(row({ threshold_op: null, threshold_value: null })),
    "compactions > 0"
  );
  // And an operator this build has never heard of is not guessed at.
  assert.equal(thresholdLine(row({ threshold_op: "<", threshold_value: 4 })), "compactions > 0");
});

test("nothing on the screen says undefined, with or without the split's number", () => {
  const bare = row({ threshold_op: null, threshold_value: null });
  for (const rows of [[row()], [bare]]) {
    const text = screenFor(rows).textContent;
    assert.equal(text.includes("undefined"), false, text);
    assert.equal(text.includes("NaN"), false, text);
    assert.equal(text.includes("null"), false, text);
  }
});

/* --- the short label ----------------------------------------------------------------------- */

test("a behaviour is named in the words a bar has room for, in both languages", () => {
  Str.setLang("en");
  assert.equal(shortLabel("commit_attempts_per_commit"), "3+ commit attempts");
  Str.setLang("zh-Hans");
  assert.equal(shortLabel("commit_attempts_per_commit"), "提交尝试 3 次以上");
  Str.setLang("en");
});

test("a purpose used as a split is named as a purpose, not as a raw label", () => {
  assert.equal(shortLabel("purpose:research"), "labelled research");
  // `unknown` is "other" everywhere the reader sees it. Neither store on this machine
  // has a purpose observation yet, so nothing but this test covers the branch.
  assert.equal(shortLabel("purpose:unknown"), "labelled other");
});

test("a behaviour this build has never heard of falls back to the engine's key", () => {
  // Ugly and readable, never blank: the engine may grow a thirteenth split before this
  // app learns a word for it.
  assert.equal(shortLabel("some_new_fact"), "some_new_fact");
});

/* --- the chart -------------------------------------------------------------------------- */

test("every pair is drawn on the same axis, so two cards can be compared", () => {
  // The axis top used to be a quarter, a half, three quarters or the whole, whichever
  // first held the taller bar, and nothing on the card said which: on the founder's own
  // store that drew a 19% bar physically longer than an 84% bar two cards below it.
  const widths = (over) =>
    screenFor([row(over)])
      .tagged("rect")
      .map((node) => Number(node.getAttribute("width")))
      .filter((width) => width !== 1000);
  const [smallWith] = widths({ with_value: 0.19, without_value: 0.08 });
  const [largeWith] = widths({ with_value: 0.94, without_value: 0.84 });
  assert.ok(
    smallWith < largeWith,
    `19% drew ${smallWith} and 94% drew ${largeWith} on a 1000-unit track`
  );
});

/* The distance between the two medians is a quantity the **engine** owns:
   `store/observations.py` has `MIN_GAP = 0.10` and takes it on the unrounded values as
   the floor an observation must clear to exist at all. A second one printed from the two
   rounded shares is a second definition of one number, and they disagree: with 0.9051
   against 0.8050 the engine has 10.01 points and the rounded shares give 11. Both
   medians are on the card, and the engine's own sentence states them. */
test("no card prints a distance between the two medians", () => {
  const screen = screenFor([row(), row({ outcome: "rework", observation_id: 2 })]);
  for (const word of ["point", "个百分点"]) {
    assert.equal(screen.textContent.includes(word), false, `a card prints a gap: ${word}`);
  }
  // Nor in the accessible caption, which is where it lived last.
  for (const figure of screen.tagged("figure")) {
    assert.equal((figure.getAttribute("aria-label") ?? "").includes("point"), false);
  }
});

test("colour is the outcome's identity and is never keyed to direction", () => {
  // The same two values, the same outcome, opposite directions: the fills must match.
  const higher = screenFor([row({ outcome: "rework", direction: "higher" })]);
  const lower = screenFor([row({ outcome: "rework", direction: "lower" })]);
  const fills = (node) =>
    node
      .tagged("rect")
      .map((rect) => rect.getAttribute("fill"))
      .join(" ");
  assert.equal(fills(higher), fills(lower));
  assert.ok(fills(higher).includes("var(--o-rework)"), fills(higher));
  assert.equal(fills(higher).includes("var(--o-alive)"), false);

  // And the two outcomes are told apart by colour, which is what identity means.
  const alive = screenFor([row({ outcome: "alive_head" })]);
  assert.ok(fills(alive).includes("var(--o-alive)"));
});

test("every share on the screen carries the number of sessions it is over", () => {
  const screen = screenFor([row({ with_n: 16, without_n: 33 })]);
  const values = screen.all("paired-value").map((node) => node.textContent);
  assert.deepEqual(values, ["73% of 16 sessions", "93% of 33 sessions"]);
  // Once more under the pair, so a reader who skipped the bars still has both sizes.
  assert.ok(screen.textContent.includes("16 sessions did, 33 did not"), screen.textContent);
});

test("the figure carries its own numbers in words, for a reader with no pointer", () => {
  const screen = screenFor([row()]);
  const figure = screen.tagged("figure")[0];
  const caption = figure.getAttribute("aria-label");
  assert.equal(
    caption,
    "compacted context: 73% of 16 sessions. did not: 93% of 33 sessions."
  );
  assert.equal(figure.tagged("figcaption")[0].textContent, caption);
});

test("the coverage and the commit mix sit with the numbers they qualify", () => {
  const screen = screenFor([row({ coverage: 0.92, fact_commits: 642, inferred_commits: 25 })]);
  const chips = screen.all("coverage-chip").map((node) => node.textContent);
  assert.deepEqual(chips, ["coverage 92%, method: 642 fact, 25 inferred"]);
});

test("a coverage the engine never produced reads as a dash, not as zero", () => {
  const screen = screenFor([row({ coverage: null })]);
  assert.ok(screen.all("coverage-chip")[0].textContent.startsWith("coverage -"));
});

/* --- the method, and the sort rule, stated ------------------------------------------------ */

test("the card states its method in words and names its view behind a disclosure", () => {
  const screen = screenFor([row()]);
  // In words, on the card: the threshold that made the split.
  assert.ok(screen.textContent.includes("Threshold: more than 0"), screen.textContent);
  const how = screen.tagged("details")[0];
  assert.ok(how.textContent.includes("app_observation"), how.textContent);
  // The engine's own clause, so the reworded one above can be checked against it.
  assert.ok(how.textContent.includes("compactions > 0"), how.textContent);
});

test("the page says how it is ordered, and that the range above does not reach it", () => {
  const text = screenFor([row()]).textContent;
  assert.ok(text.includes("furthest apart comes first"), text);
  assert.ok(text.includes("not a ranking"), text);
  assert.ok(text.includes("every session on record"), text);
});

test("the page describes blocks only when it has drawn some", () => {
  const blocks = "each project's own follow under its name";
  const one = screenFor([row({ project: "beatos", repo_key: "root:beatos" })]).textContent;
  assert.equal(one.includes(blocks), false, "described an arrangement that is not on screen");

  const two = screenFor([
    row({ project: "beatos", repo_key: "root:beatos" }),
    row({ project: "other", repo_key: "root:other" }),
  ]).textContent;
  assert.ok(two.includes(blocks), two);
});

/* --- the empty state ----------------------------------------------------------------------- */

test("an empty store says there are two floors, and names neither in numbers", () => {
  const text = screenFor([], null).textContent;
  assert.ok(text.includes("No observations yet"), text);
  // It says what the rule is about. Both floors are the engine's numbers
  // (`MIN_SESSIONS`, `MIN_GAP`) and it publishes its own sentence naming them, so a
  // second copy here would go stale the first time either moved, with nothing failing.
  assert.ok(text.includes("sessions on both sides"), text);
  assert.ok(text.includes("gap between the two medians"), text);
  for (const stale of ["five sessions", "ten points"]) {
    assert.equal(text.includes(stale), false, `a floor is stated as a number: ${stale}`);
  }
});

test("headings appear only when there is more than one block to tell apart", () => {
  const one = screenFor([row({ project: "beatos", repo_key: "root:beatos" })]);
  assert.deepEqual(one.all("obs-heading"), [], "one project needs no heading over it");

  const two = screenFor([
    row({ project: "beatos", repo_key: "root:beatos" }),
    row({ project: null, repo_key: "*", pooled: 1 }),
  ]);
  assert.deepEqual(
    two.all("obs-heading").map((node) => node.textContent),
    ["Across your projects", "beatos"]
  );
});

test("a project with nothing says so as a fact about that project", () => {
  const text = screenFor([row({ project: "beatos", repo_key: "root:beatos" })], "other")
    .textContent;
  assert.ok(text.includes("No observations for this project"), text);
});

/* --- the whole thing, against the engine's own store ---------------------------------------- */

/** The fixture's own rows, read with `sqlite3` so the test depends on no driver. */
function fixtureRows() {
  const sql = "SELECT * FROM app_observation ORDER BY observation_id;";
  const out = execFileSync("sqlite3", ["-json", FIXTURE, sql], { encoding: "utf8" }).trim();
  return out ? JSON.parse(out) : [];
}

const stored = fixtureRows();

test("the fixture has observations to draw", () => {
  assert.ok(stored.length > 0, "no rows in app_observation; regenerate the fixture");
});

test("every figure drawn is a column of the row, never something derived from it", () => {
  Str.setLang("en");
  const screen = screenFor(stored);
  const text = screen.textContent;
  for (const one of stored) {
    // The engine's own sentence is on the row. The screen composes its own so it can be
    // Chinese too, and `sentences.test.mjs` pins the English against this column; here
    // the point is that the sentence the reader sees is the one the store holds.
    assert.ok(text.includes(one.sentence), `missing: ${one.sentence}`);
  }
  // Each side's share appears exactly as the engine would print it.
  for (const one of stored) {
    const share = `${Math.round(one.with_value * 100)}% of ${one.with_n} session`;
    assert.ok(text.includes(share), `missing: ${share}`);
  }
});

test("the fixture's rows draw one card per behaviour and scope, widest gap first", () => {
  const groups = groupsOf(stored);
  const keys = new Set(stored.map((one) => `${one.repo_key}|${one.fact}`));
  assert.equal(groups.length, keys.size);
  const gaps = groups.map((one) => one.gap);
  assert.deepEqual(gaps, [...gaps].sort((a, b) => b - a));
});

test("the screen returns one element and appends nothing to the page", () => {
  const screen = screenFor(stored);
  assert.equal(screen.nodeName, "div");
  assert.equal(screen.className, "screen-body");
});

test("the whole screen draws in Chinese with no English left in it", () => {
  Str.setLang("zh-Hans");
  const screen = screenFor(stored);
  const text = screen.textContent;
  // The composed sentence is Chinese, not the engine's English copied across.
  for (const one of stored) {
    assert.equal(text.includes(one.sentence), false, `English sentence left in: ${one.sentence}`);
  }
  assert.ok(text.includes("覆盖率"), "the caveat is not in Chinese");
  assert.ok(text.includes("相差"), "the gap is not in Chinese");
  // The threshold too, which is the whole reason contract 3 stores it as a number.
  const withOp = stored.filter((one) => one.threshold_op);
  if (withOp.length) assert.ok(text.includes("多于") || text.includes("至少"), text);
  Str.setLang("en");
});
