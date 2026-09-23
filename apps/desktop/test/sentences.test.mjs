/* The composed sentence, against the engine's own.
 *
 * Design rule 3: a sentence is composed in each language, never translated. English is
 * the case with an answer key, because the engine writes the same sentence and stores it
 * on the row. **Every row of the fixture, word for word.** If this fails, either the
 * interface's composition drifted or `store/observations.py` changed its phrasing, and
 * the difference printed below says which.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import * as Str from "../src/text/strings.js";
import { observationCaveat, observationSentence } from "../src/text/sentences.js";

const here = dirname(fileURLToPath(import.meta.url));
const app = join(here, "..");
const FIXTURE = join(app, "fixtures/store.db");

for (const language of Str.LANGUAGES) {
  Str.load(
    language,
    JSON.parse(readFileSync(join(app, `src/text/strings.${language}.json`), "utf8"))
  );
}

/** The fixture's own rows, read with `sqlite3` so the test depends on no driver. */
function observations() {
  const sql = `SELECT project, pooled, fact, outcome, with_n, without_n,
                      with_value, without_value, coverage, fact_commits,
                      inferred_commits, sentence
               FROM app_observation;`;
  const out = execFileSync("sqlite3", ["-json", FIXTURE, sql], { encoding: "utf8" }).trim();
  return out ? JSON.parse(out) : [];
}

const rows = observations();

test("the fixture has observations to compare against", () => {
  assert.ok(rows.length > 0, "no rows in app_observation; regenerate the fixture");
});

test("the composed English equals the engine's own sentence, for every row", () => {
  Str.setLang("en");
  const wrong = [];
  for (const row of rows) {
    const ours = observationSentence(row);
    if (ours !== row.sentence) wrong.push({ fact: row.fact, ours, engine: row.sentence });
  }
  assert.deepEqual(
    wrong,
    [],
    wrong.map((w) => `\n  ${w.fact}\n    ours:   ${w.ours}\n    engine: ${w.engine}`).join("")
  );
});

test("the Chinese says the same thing in its own words", () => {
  Str.setLang("zh-Hans");
  for (const row of rows) {
    const chinese = observationSentence(row);
    assert.notEqual(chinese, row.sentence, `${row.fact} was not composed in Chinese`);
    // The figures are the same figures, whatever the words around them.
    const share = `${Math.round(row.with_value * 100)}%`;
    assert.ok(
      chinese.includes(share) || chinese.includes(`${Math.round(row.with_value * 100) - 1}%`),
      `${row.fact}: the Chinese sentence does not carry its own share`
    );
  }
  Str.setLang("en");
});

test("the caveat carries the coverage and both methods", () => {
  Str.setLang("en");
  for (const row of rows) {
    const caveat = observationCaveat(row);
    assert.match(caveat, /coverage \d+%/);
    assert.ok(caveat.includes(`${row.fact_commits} fact`), caveat);
    assert.ok(caveat.includes(`${row.inferred_commits} inferred`), caveat);
  }
});

/* --- the two waste facts (test_fix_loops, giant_turns) ------------------------------------
 *
 * The fixture predates both: it has no `app_observation` row for either fact, so there is
 * no engine `sentence` column to diff against here. The English below is instead copied
 * from `Split.did` in `store/observations.py` by hand, the same way `sentences.js`'s own
 * `SPLITS` array copies it; if the engine's wording ever moves, this and that array drift
 * together and both need the same fix.
 */

/** Mirrors `Split.did` for the two newest facts (`store/observations.py`, `SPLITS`). */
const ENGINE_DID = {
  test_fix_loops: "that went through five or more test-fix loops",
  giant_turns: "that had a turn above five million tokens",
};

/** A minimal `app_observation` row for a fact the fixture does not carry yet. */
function syntheticRow(fact, over = {}) {
  return {
    project: "demo",
    pooled: 0,
    fact,
    outcome: "alive_head",
    with_n: 12,
    without_n: 30,
    with_value: 0.64,
    without_value: 0.38,
    coverage: 0.9,
    fact_commits: 10,
    inferred_commits: 2,
    ...over,
  };
}

test("test_fix_loops composes in English exactly as the engine words it", () => {
  Str.setLang("en");
  const sentence = observationSentence(syntheticRow("test_fix_loops"));
  assert.equal(
    sentence,
    "In demo, your 12 sessions that went through five or more test-fix loops still have " +
      "64% of their lines at head (median); the 30 that did not, 38%."
  );
});

test("test_fix_loops composes in Chinese in its own words", () => {
  Str.setLang("zh-Hans");
  const sentence = observationSentence(syntheticRow("test_fix_loops"));
  assert.notEqual(sentence, ENGINE_DID.test_fix_loops);
  assert.ok(sentence.includes("测试-修复循环"), sentence);
  assert.ok(sentence.includes("64%"), sentence);
  Str.setLang("en");
});

test("giant_turns composes in English exactly as the engine words it", () => {
  Str.setLang("en");
  const sentence = observationSentence(
    syntheticRow("giant_turns", { outcome: "rework", with_value: 0.55, without_value: 0.2 })
  );
  assert.equal(
    sentence,
    "In demo, your 12 sessions that had a turn above five million tokens reworked 55% of " +
      "their lines (median); the 30 that did not, 20%."
  );
});

test("giant_turns composes in Chinese in its own words", () => {
  Str.setLang("zh-Hans");
  const sentence = observationSentence(
    syntheticRow("giant_turns", { outcome: "rework", with_value: 0.55, without_value: 0.2 })
  );
  assert.ok(sentence.includes("五百万"), sentence);
  assert.ok(sentence.includes("55%"), sentence);
  Str.setLang("en");
});

/* Every fact `store/observations.py`'s `SPLITS` tuple carries, in that file's own order.
 * A fact the engine adds and this composer forgets should turn into a red test here
 * rather than a silent "with <fact>" (English) or "带有 <fact>" (Chinese) in the app. */
const ENGINE_SPLITS = [
  "sittings",
  "files_edited_unread",
  "formatter_runs",
  "test_runs",
  "tests_before_commit",
  "commit_attempts_per_commit",
  "repeated_errors",
  "subagent_used",
  "compactions",
  "context_resets",
  "prompts_per_active_hour",
  "hand_edits_between_turns",
  "test_fix_loops",
  "giant_turns",
];

test("no fact the engine splits on falls through to the raw-key sentence", () => {
  // The fallback ("with <fact>" in English, "带有 <fact>" in Chinese) is the tell: a
  // real phrase is prose and never contains its own snake_case key. Some real phrases do
  // contain the fact's own English word ("sittings" says "...three or more sittings"),
  // so the check is for the unknown-key template's exact shape, not a bare substring.
  const unknown = { en: (fact) => `with ${fact}`, "zh-Hans": (fact) => `带有 ${fact}` };
  for (const language of Str.LANGUAGES) {
    Str.setLang(language);
    for (const fact of ENGINE_SPLITS) {
      const sentence = observationSentence(syntheticRow(fact));
      assert.ok(
        !sentence.includes(unknown[language](fact)),
        `${language}/${fact}: fell through to the raw-key sentence`
      );
    }
  }
  Str.setLang("en");
});
