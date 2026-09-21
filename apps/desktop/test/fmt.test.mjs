/* The formatters, called rather than read.
 *
 * The previous version of this file asserted that a particular expression appeared in
 * `fmt.js`, which pinned an implementation that was wrong and called itself the guard
 * against that defect. These call the functions.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import * as Fmt from "../src/text/fmt.js";
import * as Str from "../src/text/strings.js";

const here = dirname(fileURLToPath(import.meta.url));
const app = join(here, "..");

for (const language of Str.LANGUAGES) {
  Str.load(
    language,
    JSON.parse(readFileSync(join(app, `src/text/strings.${language}.json`), "utf8"))
  );
}
Str.setLang("en");

/* The share and the plain integer are the two values that do not go through the locale,
   because an observation sentence has to equal `app_observation.sentence` character for
   character. The engine writes them with Python's `%` operator, which rounds **half to
   even**; `Math.round` rounds half away from zero and disagrees on every exact half. */
test("a share rounds the way the engine rounds", () => {
  // Exact halves: the only inputs on which the two rules differ.
  assert.equal(Fmt.percent(0.125), "12%", "12.5 rounds to even");
  assert.equal(Fmt.percent(0.135), "14%", "13.5 rounds to even");
  assert.equal(Fmt.percent(0.865), "86%", "86.5 rounds to even");
  assert.equal(Fmt.percent(0.875), "88%", "87.5 rounds to even");
  // Everything else is ordinary.
  assert.equal(Fmt.percent(0.1249), "12%");
  assert.equal(Fmt.percent(0.1251), "13%");
  assert.equal(Fmt.percent(0), "0%");
  assert.equal(Fmt.percent(1), "100%");
});

test("a share with nothing measured is a dash, not a zero", () => {
  assert.equal(Fmt.percent(null), "-");
  assert.equal(Fmt.percent(undefined), "-");
  assert.equal(Fmt.percent(Number.NaN), "-");
});

test("a gap is neutral: no sign, and the same either way round", () => {
  assert.equal(Fmt.points(0.17), Fmt.points(-0.17));
  assert.equal(Fmt.points(0.17), "17");
});

test("tokens abbreviate the way the mockups print them", () => {
  assert.equal(Fmt.tokens(812), "812");
  assert.equal(Fmt.tokens(5955), "6.0k");
  assert.equal(Fmt.tokens(43_100), "43.1k");
  assert.equal(Fmt.tokens(1_200_000), "1.2M");
  // A real store reaches here. The rung was missing until the Overview was drawn against
  // a copy of one and an axis label read "1,316.1M".
  assert.equal(Fmt.tokens(1_316_100_000), "1.3B");
  assert.equal(Fmt.tokens(9_669_002_000), "9.7B");
  // Each rung takes over exactly where the one below it stops.
  assert.equal(Fmt.tokens(999_999_999), "1,000.0M");
  assert.equal(Fmt.tokens(1_000_000_000), "1.0B");
});

test("an axis of token values reads in one unit, with one number of decimals", () => {
  // Per-value units made one axis read "1.5B, 1.1B, 750.0M, 375.0M", which asks the
  // reader to convert between two units to compare four gridlines.
  const billions = Fmt.tokenScale(1_500_000_000);
  assert.deepEqual(
    [0, 0.25, 0.5, 0.75, 1].map((q) => billions(1_500_000_000 * q)),
    ["0", "0.4B", "0.8B", "1.1B", "1.5B"]
  );
  // And the decimals come from the top of the scale, or one axis reads "9.0k, 12k".
  const thousands = Fmt.tokenScale(12_000);
  assert.deepEqual(
    [0, 0.25, 0.5, 0.75, 1].map((q) => thousands(12_000 * q)),
    ["0", "3k", "6k", "9k", "12k"]
  );
  // Small scales stay plain counts rather than becoming "0.1k".
  const few = Fmt.tokenScale(8);
  assert.deepEqual([0, 4, 8].map(few), ["0", "4", "8"]);
});

test("a count carries its language's grouping", () => {
  assert.equal(Fmt.count(1248, "en"), "1,248");
  assert.equal(Fmt.count(1248, "zh-Hans"), "1,248");
});

/* English chooses a plural form, Chinese does not have one to choose. */
test("a count in words agrees with its language", () => {
  assert.equal(Fmt.sessions(1, "en"), "1 session");
  assert.equal(Fmt.sessions(3, "en"), "3 sessions");
  assert.equal(Fmt.sessions(1, "zh-Hans"), "1 个会话");
  assert.equal(Fmt.sessions(3, "zh-Hans"), "3 个会话");
});

test("a measure does not pretend to be a count", () => {
  assert.equal(Fmt.tokenPhrase(5955, "en"), "6.0k tokens");
  assert.equal(Fmt.hourPhrase(0.14, "en"), "0.1 hours");
});

test("a list joins the way its language joins one", () => {
  Str.setLang("en");
  assert.equal(Fmt.list(["a", "b"]), "a, b");
  Str.setLang("zh-Hans");
  assert.equal(Fmt.list(["a", "b"]), "a，b");
  Str.setLang("en");
});

/* A day is a local day. `new Date("2026-09-21")` is UTC midnight and lands on the day
   before for anyone west of Greenwich, which is where the founder is. */
test("a day is the local day the engine meant", () => {
  const date = Fmt.fromDay("2026-09-21");
  assert.equal(date.getFullYear(), 2026);
  assert.equal(date.getMonth(), 8);
  assert.equal(date.getDate(), 21);
});

test("a relative time truncates, and says never when there is nothing", () => {
  const now = new Date("2026-09-21T12:00:00Z");
  // Thirteen and a half hours reads as thirteen, not fourteen.
  assert.match(Fmt.relative(new Date("2026-09-20T22:30:00Z"), now, "en"), /13 hours ago/);
  assert.equal(Fmt.relative(new Date("2026-09-21T11:59:30Z"), now, "en"), "just now");
  assert.equal(Fmt.relative(null, now, "en"), "never");
});

/* `unknown` is "other" to the reader and never the word "unknown"; a purpose this build
   has never heard of folds into it rather than vanishing. */
test("a purpose the reader sees is never the engine's raw label", () => {
  Str.setLang("en");
  assert.equal(Fmt.purpose("unknown"), "other");
  assert.equal(Fmt.purpose("something_new"), "other");
  assert.equal(Fmt.purpose("development"), "development");
  Str.setLang("zh-Hans");
  assert.equal(Fmt.purpose("development"), "开发");
  Str.setLang("en");
});

/* Inside an observation sentence English keeps the engine's own raw label, because that
   sentence is compared with the engine's word for word. */
test("inside a sentence, English keeps the engine's word and Chinese does not", () => {
  assert.equal(Fmt.purposeInSentence("unknown", "en"), "unknown");
  assert.equal(Fmt.purposeInSentence("unknown", "zh-Hans"), "其他");
});

/* Every formatter takes a language, so a test never has to mutate global state to check
   one. The Swift original had the same parameter and the first port dropped it. */
test("every formatter can be called at a named language", () => {
  Str.setLang("en");
  assert.equal(Fmt.sessions(3, "zh-Hans"), "3 个会话", "asking for Chinese gives Chinese");
  assert.equal(Str.lang(), "en", "and does not change the language in force");
});
