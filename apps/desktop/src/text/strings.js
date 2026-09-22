/* The interface's strings, from one source.
 *
 * `strings.en.json` and `strings.zh-Hans.json` were generated once from the Swift String
 * Catalog (`Scripts/strings.py`) and are the source of truth from then on. This is the
 * runtime: look a key up, fill its placeholders, choose a plural form.
 *
 * Three rules, each with a test in `test/strings.test.mjs`:
 *
 * - **A missing key is a bug, not a fallback.** `t` returns the key itself so a screen
 *   still draws, and the suite fails on it.
 * - **Placeholders are numbered and filled in each language's own order.** That is the
 *   whole reason they are `%1$@` and not `%@`.
 * - **Plurals are a plural entry.** The form comes from `Intl.PluralRules` in the
 *   language in force, so English says "1 session" and "3 sessions" and Chinese says
 *   "1 个会话" either way.
 */

/** @typedef {"en"|"zh-Hans"} Language */
/** @typedef {string | Record<string, string>} Entry */
/** @typedef {{ note: string, language: string, strings: Record<string, Entry> }} Table */

/** Both languages the app ships. The setting switches between them without a relaunch,
 *  so both tables are loaded at start-up. Thirty kilobytes, once. */
export const LANGUAGES = /** @type {readonly Language[]} */ (Object.freeze(["en", "zh-Hans"]));

/** The product is named in exactly two places: the bundle's display name and this.
 *  It is not a catalog key, because it is not translated, and the name research is
 *  still open, so renaming has to be two edits. */
export const PRODUCT_NAME = "Prudence";

/** @type {Partial<Record<Language, Table>>} */
const tables = {};
/** @type {Map<string, Intl.PluralRules>} */
const pluralRules = new Map();
/** @type {Language} */
let current = "en";

/** @param {Language} language @param {Table} payload */
export function load(language, payload) {
  tables[language] = payload;
}

/** Fetch both tables. The only reason this is here and not in the boot file is that the
 *  paths belong with the runtime that reads them. */
export async function loadAll(base = "text") {
  await Promise.all(
    LANGUAGES.map(async (language) => {
      const response = await fetch(`${base}/strings.${language}.json`);
      if (!response.ok) throw new Error(`strings.${language}: ${response.status}`);
      load(language, await response.json());
    })
  );
}

export function lang() {
  return current;
}

/** @param {string} next @returns {Language} */
export function setLang(next) {
  current = /** @type {Language} */ (
    LANGUAGES.includes(/** @type {Language} */ (next)) ? next : "en"
  );
  if (typeof document !== "undefined") document.documentElement.setAttribute("lang", current);
  return current;
}

/** @param {Language} [language] */
function table(language) {
  return tables[language ?? current]?.strings ?? {};
}

/** `%1$@`, `%2$@`, in whatever order this language wrote them. */
function fill(template, args) {
  if (!args.length) return template;
  return template.replace(/%(\d+)\$@/g, (whole, index) => {
    const value = args[Number(index) - 1];
    return value === undefined ? whole : String(value);
  });
}

/**
 * @param {string} key
 * @param {...(string|number)} args
 * @returns {string}
 */
export function t(key, ...args) {
  const value = table()[key];
  if (typeof value !== "string") return key;
  return fill(value, args);
}

/** The same lookup at a named language, for tests and for anything that has to render
 *  a string in a language other than the one in force. */
export function tIn(language, key, ...args) {
  const value = table(language)[key];
  if (typeof value !== "string") return key;
  return fill(value, args);
}

function rulesFor(language) {
  let rules = pluralRules.get(language);
  if (!rules) {
    rules = new Intl.PluralRules(language);
    pluralRules.set(language, rules);
  }
  return rules;
}

/**
 * A count in words. `formatted` is the count as the reader's locale writes it, because
 * the plural form is chosen on the number and printed with the grouping.
 *
 * @param {string} key
 * @param {number} count
 * @param {string} [formatted]
 * @param {Language} [language]
 */
export function plural(key, count, formatted, language) {
  const entry = table(language)[key];
  if (!entry || typeof entry === "string") return key;
  const form = rulesFor(language ?? current).select(count);
  const template = entry[form] ?? entry.other ?? entry.one;
  if (typeof template !== "string") return key;
  return template.replace(/%\d+\$lld/g, formatted === undefined ? String(count) : formatted);
}

/** @param {Language} language */
export function tableFor(language) {
  return table(language);
}
