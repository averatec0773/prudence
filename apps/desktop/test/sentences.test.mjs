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
const FIXTURE = join(app, "../mac/PrudenceKit/Tests/PrudenceKitTests/Fixtures/store.db");

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
