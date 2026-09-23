/* The localisation rules, rescued from the Swift suite.
 *
 * `UITests` asserts these about the String Catalog; the catalog is now two JSON files and
 * a small runtime, so the same questions are asked of those. The wording of each test is
 * the Swift one's, because it is the rule that matters and not the implementation.
 *
 *     pnpm test
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const app = join(here, "..");

const LANGUAGES = ["en", "zh-Hans"];
const tables = Object.fromEntries(
  LANGUAGES.map((language) => [
    language,
    JSON.parse(readFileSync(join(app, `src/text/strings.${language}.json`), "utf8")),
  ])
);

const strings = Object.fromEntries(
  LANGUAGES.map((language) => [language, tables[language].strings])
);

function values(entry) {
  return typeof entry === "string" ? [entry] : Object.values(entry);
}

/** The numbered placeholders a template uses, as a sorted set: `["1", "2"]`. */
function placeholders(template) {
  return [...template.matchAll(/%(\d+)\$[@a-z]+/g)].map((m) => m[1]).sort();
}

test("every key is translated in both languages", () => {
  const en = Object.keys(strings.en);
  // A floor, not an exact count. The exact number was a magic constant that had to be
  // edited every time a string was added, which made it a chore rather than a check: it
  // failed for correct changes and told you nothing when it did. What it was really
  // guarding is that the generator does not silently drop a table, and a floor does
  // that. The assertion that matters is the key-set equality below.
  assert.ok(en.length > 200, `the catalog has only ${en.length} keys`);
  for (const language of LANGUAGES) {
    assert.deepEqual(
      Object.keys(strings[language]).sort(),
      en.slice().sort(),
      `${language} has a different key set`
    );
    for (const [key, entry] of Object.entries(strings[language])) {
      for (const value of values(entry)) {
        assert.equal(typeof value, "string", `${language} ${key} is not a string`);
        assert.notEqual(value.trim(), "", `${language} ${key} is empty`);
        assert.notEqual(value, key, `${language} ${key} resolves to its own key`);
      }
    }
  }
});

/* Which keys share their text, as a list that has to be kept up to date.
 *
 * `apps/mac/DESIGN.md` says a test asserts "that no two read the same". **It does not**:
 * the Swift suite has `everyKeyIsTranslatedInBothLanguages` and `theChineseIsNotTheEnglish`
 * and nothing else about duplication, and the catalog has nine pairs that share their text
 * in one language or the other. Every one of them is two separate decisions that happen to
 * read alike today: a chart's axis label and a card's caption, a menu line and an empty
 * state, a phrase inside a composed sentence and a legend's name.
 *
 * So the rule is not "no two read the same". It is **no two read the same by accident**,
 * and the only way to assert that is to write the list down and make a new one fail.
 */
const SHARED_TEXT = {
  en: [
    // What a reply did, and a column header the engine writes on a review's comparison
    // table. The first is this app's word for a bucket; the second changes when the engine
    // changes it.
    ["bucket.change", "review.header.change"],
    ["chart.hours", "overview.activeHours"],
    // A chart's short axis word, and the unit a progress counter counts in. The Chinese
    // is not the same in the two places (`会话` against `个会话`), which is what makes
    // them two decisions rather than one written twice.
    ["chart.sessionsShort", "engine.unit.sessions"],
    // The unit a chart's value axis is in, and the label the engine writes on a review's
    // own table. One is this app's word for a scale it draws; the other is a header row
    // the engine printed and this app only translates, and it changes when the engine
    // changes it.
    ["chart.unit.tokens", "review.header.tokens"],
    ["common.dateWithRelative", "menu.stamped"],
    ["menu.noReview", "review.empty.title"],
    ["observation.outcome.rework", "overview.legend.reworkName"],
    ["observation.where.pooled", "observations.group.pooled"],
    // A heat cell labelled with its hours, and a review's section labelled with its
    // finding. Same punctuation, two unrelated decisions.
    ["overview.dayHours", "review.headline.section"],
    ["overview.legend.coverageName", "review.tag.coverage"],
    ["section.settings", "settings.title"],
  ],
  "zh-Hans": [
    // A reply that neither wrote, ran nor read, and a session the retired purpose rule
    // labelled a conversation. The founder chose 对话 for the bucket; the purpose word is
    // still on stored reviews and observations, and the two go separate ways when the
    // purpose label is dropped.
    ["bucket.talk", "purpose.conversation"],
    ["chart.hours", "overview.activeHours"],
    // As above: a chart's own unit, and a header the engine wrote.
    ["chart.unit.tokens", "review.header.tokens"],
    ["common.dateWithRelative", "menu.stamped"],
    // The panel's range caption ("最近 30 天") and the Overview's summary sentence's own
    // window phrase ("...，最近 30 天，..."): the same words, because Chinese has no case
    // to tell a heading from a phrase inside a sentence apart. English does: "Last %1$@"
    // against "last %1$@", a capital the heading needs and the sentence must not have.
    ["menu.lastRangeDays", "overview.window.last"],
    ["menu.noReview", "review.empty.title"],
    ["observation.didNot", "observation.side.didNot"],
    ["observation.outcome.rework", "overview.legend.reworkName"],
    // A heat cell labelled with its hours, and a review's section labelled with its
    // finding. Same punctuation, two unrelated decisions.
    ["overview.dayHours", "review.headline.section"],
    ["overview.legend.coverageName", "review.tag.coverage"],
    ["review.tag.scope", "scope.range"],
    ["section.settings", "settings.title"],
  ],
};

test("no two keys read the same by accident", () => {
  for (const language of LANGUAGES) {
    const byText = new Map();
    for (const [key, entry] of Object.entries(strings[language])) {
      if (typeof entry !== "string") continue;
      if (!byText.has(entry)) byText.set(entry, []);
      byText.get(entry).push(key);
    }
    const found = [...byText.values()]
      .filter((keys) => keys.length > 1)
      .map((keys) => keys.slice().sort())
      .sort((a, b) => a[0].localeCompare(b[0]));
    assert.deepEqual(
      found,
      SHARED_TEXT[language],
      `${language}: the set of keys sharing their text changed. If the new pair is two ` +
        "separate decisions, add it above with a reason; if it is one decision written " +
        "twice, delete one of the keys."
    );
  }
});

/* Every string that is not a number, a symbol or a technical token should differ between
   the two languages. The Swift test is `theChineseIsNotTheEnglish`. */
test("the Chinese is not the English", () => {
  const identical = [];
  for (const [key, english] of Object.entries(strings.en)) {
    if (typeof english !== "string") continue;
    const chinese = strings["zh-Hans"][key];
    if (english === chinese && /\p{Letter}/u.test(english)) identical.push(key);
  }
  assert.deepEqual(identical, [], `untranslated: ${identical.join(", ")}`);
});

/* The whole reason a placeholder is `%1$@` and not `%@`: Chinese puts them elsewhere. The
   set has to match, the order does not. */
test("placeholders are the same set in each language, in each language's own order", () => {
  for (const [key, english] of Object.entries(strings.en)) {
    const chinese = strings["zh-Hans"][key];
    if (typeof english === "string") {
      assert.deepEqual(
        placeholders(chinese),
        placeholders(english),
        `${key} does not carry the same placeholders`
      );
      continue;
    }
    for (const form of Object.keys(english)) {
      const other = chinese[form] ?? chinese.other;
      assert.deepEqual(
        placeholders(other),
        placeholders(english[form]),
        `${key}.${form} does not carry the same placeholders`
      );
    }
  }
});

/* English chooses a form, Chinese does not have one to choose. `Intl.PluralRules` is what
   the runtime asks, so it is what the test asks. */
test("plurals choose a form in English and do not in Chinese", () => {
  const plural = Object.entries(strings.en).filter(([, v]) => typeof v !== "string");
  assert.equal(plural.length, 8, "eight keys carry a count");

  for (const [key, english] of plural) {
    assert.deepEqual(
      Object.keys(english).sort(),
      ["one", "other"],
      `${key} should have an English one and other`
    );
    assert.deepEqual(
      Object.keys(strings["zh-Hans"][key]),
      ["other"],
      `${key} should have a single Chinese form`
    );
  }

  const en = new Intl.PluralRules("en");
  const zh = new Intl.PluralRules("zh-Hans");
  assert.equal(en.select(1), "one");
  assert.equal(en.select(0), "other");
  assert.equal(en.select(3), "other");
  assert.equal(zh.select(1), "other");
  assert.equal(zh.select(3), "other");
});

/* The two values that do not go through the locale used to be guarded here by asserting
   that a particular expression appeared in `fmt.js`. That pinned an implementation which
   was **wrong** (it rounded half away from zero where the engine rounds half to even) and
   called itself the guard against that defect. The rule is now asserted by calling the
   function: see `test/fmt.test.mjs`, "a share rounds the way the engine rounds", and
   `test/sentences.test.mjs`, which compares the whole sentence with the engine's own. */

/* Every key is read by something.

   A key nothing reads is a string nobody reviews: it is translated, kept in step with its
   pair and carried through every rename, and it says whatever it said when the screen
   that used it was deleted. Nineteen had piled up since the tables were generated from
   the Swift catalogue, and the purpose chart's six would have joined them at contract 4.

   A key is read when the source names it in quotes, or when it starts with a prefix the
   source completes at run time (`engine.step.${...}`); those prefixes are found in the
   source rather than listed here, so a new one needs no edit to this test. */
test("every key is read by something in the source", () => {
  const files = readdirSync(join(app, "src"), { recursive: true })
    .map(String)
    .filter((name) => /\.(js|html)$/.test(name));
  const source = files.map((name) => readFileSync(join(app, "src", name), "utf8")).join("\n");
  const prefixes = [...source.matchAll(/`([a-zA-Z][a-zA-Z.]*\.)\$\{/g)].map((m) => m[1]);
  assert.ok(prefixes.includes("weekday."), `the prefix scan found ${prefixes}`);

  const unread = Object.keys(strings.en).filter(
    (key) =>
      !["\"", "'", "`"].some((quote) => source.includes(`${quote}${key}${quote}`)) &&
      !prefixes.some((prefix) => key.startsWith(prefix))
  );
  assert.deepEqual(unread, [], `nothing reads: ${unread.join(", ")}`);
});

/* The tables say what they are: the source of truth, checked against each other here. */
test("both tables say they are the source of truth", () => {
  for (const language of LANGUAGES) {
    assert.equal(tables[language].language, language);
    assert.match(tables[language].note, /source of truth/);
  }
});
