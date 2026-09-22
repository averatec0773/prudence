/* What the Review screen reads out of a stored review.
 *
 * A review is not derived here: the engine wrote it once, `prudence review` printed it,
 * and the row carries the finished page. Every figure on the screen is a `text` the
 * engine formatted, and this module only **selects and reshapes** them. It performs no
 * arithmetic at all, which is a stricter rule than `store/overview.js` keeps, because
 * there is nothing left to compute: a sum here would be a second opinion about a number
 * the engine has already published.
 *
 * Two shapes it has to survive, both seen in the founder's own store:
 *
 * - **`sections` and `numbers` may be null.** `store/payload.js` parses the two JSON
 *   columns and hands back null when they will not parse. A review whose body cannot be
 *   read is a review that says so, not one that looks empty.
 * - **A review may predate a field.** Review version 2 added `with_n`, `without_n` and
 *   `previous_value` to a number; a row written before that simply has neither, and an
 *   absent field is unknown rather than zero (the engine's architecture rule 10).
 */

import { emptyBuckets, known } from "../design/purposes.js";

/** One figure of a review, as the engine stored it. Everything but the key is optional
 *  here because a review written by an earlier version has fewer fields, and an absent
 *  field is unknown rather than zero.
 *  @typedef {{key: string, label?: string, text?: string, value?: number|null,
 *             coverage?: number|null, with_n?: number|null, without_n?: number|null,
 *             previous_value?: number|null}} ReviewNumber */
/** One block of a review. Optional for the same reason a number's fields are: the
 *  engine adds a field with a review version, and a section stored before it has none.
 *  @typedef {{key: string, title?: string, headers?: string[], rows?: string[][],
 *             notes?: string[], numbers?: ReviewNumber[], empty?: string|null}} ReviewSection */

/**
 * The stored reviews, newest first, for the project in scope.
 *
 * `app_review` is already ordered by id descending, and the order is preserved rather
 * than re-sorted: ids come from the store and the view is the one that decides.
 *
 * @param {any} data the whole store payload
 * @param {{ project?: string|null }} [scope]
 * @returns {Record<string, any>[]}
 */
export function reviewsFor(data, { project = null } = {}) {
  const rows = data?.reviews ?? [];
  if (project === null) return rows;
  return rows.filter((row) => row.project === project);
}

/**
 * The review to show: the one asked for, or the newest of the list.
 *
 * @param {Record<string, any>[]} list
 * @param {number|string|null} id
 */
export function chosen(list, id) {
  if (!list.length) return null;
  const found = list.find((row) => String(row.id) === String(id));
  return found ?? list[0];
}

/**
 * The review's body: its sections, and whether they could be read at all.
 *
 * `readable` is false only when the stored JSON would not parse. An empty list of
 * sections is a different thing and is readable: it is a review that found nothing.
 *
 * @param {Record<string, any>|null} review
 * @returns {{ readable: boolean, sections: ReviewSection[], figures: number|null }}
 */
export function bodyOf(review) {
  if (!review) return { readable: false, sections: [], figures: null };
  const sections = Array.isArray(review.sections) ? review.sections : null;
  const numbers = Array.isArray(review.numbers) ? review.numbers : null;
  return {
    readable: sections !== null,
    sections: sections ?? [],
    // The count the engine's own closing line prints, so the page and the Markdown
    // report agree about how many figures the review rests on.
    figures: numbers === null ? null : numbers.length,
  };
}

/** A section's numbers, by key. Absent numbers are an empty map, never a throw. */
export function numbersOf(section) {
  /** @type {Map<string, ReviewNumber>} */
  const out = new Map();
  for (const number of section?.numbers ?? []) out.set(String(number.key), number);
  return out;
}

/**
 * Tokens per purpose, for the composition bar over the activity section.
 *
 * The values are the engine's own, bucketed by `design/purposes.js` so a purpose this
 * build has not heard of folds into `other` rather than being dropped. Nothing is added
 * up: the bar's own primitive takes the total it needs, and the figures printed beside
 * it are the section's stored row texts.
 *
 * @param {ReviewSection|null} section
 */
export function purposeTokens(section) {
  const out = emptyBuckets();
  for (const number of section?.numbers ?? []) {
    const match = /^did\.tokens\.(.+)$/.exec(String(number.key));
    if (!match) continue;
    const value = Number(number.value);
    if (!Number.isFinite(value) || value <= 0) continue;
    out[known(match[1])] += value;
  }
  return out;
}

/**
 * The outcome section's rows, each with the engine's four cells and the value behind
 * the first of them.
 *
 * `share` says whether a bar may be drawn. It is the engine's own value that decides: a
 * share is a fraction of one and a count is not, so `lines followed` (53,166 in the
 * founder's store) draws no bar while `alive at 30 days` (0.61) does. A review whose
 * followed lines came to exactly one would draw one meaningless full bar; the figure
 * printed beside it is still the engine's text, so nothing wrong is stated.
 *
 * @param {ReviewSection|null} section
 */
export function shares(section) {
  const numbers = numbersOf(section);
  return (section?.rows ?? []).map((row) => {
    // The engine keys a figure on its own label with the spaces turned into
    // underscores, and the comparison section is keyed the same way. Looking the number
    // up rather than pairing by position survives the two extra numbers (the commit
    // count and the mean coverage) the engine appends after the rows.
    const number = numbers.get(`became.${String(row[0] ?? "").replace(/ /g, "_")}`);
    // `numberOrNull`, not `Number`: the engine writes `{"text": "-", "value": null}` for
    // a survival whose denominator is zero (`views/outcomes.py`, "never zero by
    // default"), and `Number(null)` is 0, which is finite and inside [0, 1]. That made a
    // week nothing could be followed in draw an empty green track under an 88% coverage
    // underlay: a picture saying none of your lines survived, beside a printed dash.
    const value = numberOrNull(number?.value);
    return {
      label: row[0] ?? "",
      text: row[1] ?? "",
      coverageText: row[2] ?? "",
      method: row[3] ?? "",
      value,
      coverage: numberOrNull(number?.coverage),
      share: value !== null && value >= 0 && value <= 1,
    };
  });
}

/**
 * The observations, as the two sides of each split with the numbers behind them.
 *
 * The engine writes two numbers per row, the with-side then the without-side, and their
 * shared key carries `repo_key|fact|outcome`. Both are read: the key gives the screen
 * enough to compose the sentence in the reader's language (design rule 3), and the
 * stored row gives it the engine's own English to check that against.
 *
 * A row the two lists disagree about is left out rather than paired by position, so a
 * review written by a version that stored them differently loses its bars and keeps its
 * table instead of drawing somebody else's numbers.
 *
 * @param {ReviewSection|null} section
 */
export function observationPairs(section) {
  const numbers = section?.numbers ?? [];
  const rows = section?.rows ?? [];
  /** @type {{repoKey: string, fact: string, outcome: string, sentence: string,
   *          caveat: string, withN: number|null, withoutN: number|null,
   *          withValue: number|null, withoutValue: number|null,
   *          coverage: number|null}[]} */
  const out = [];
  for (let index = 0; index * 2 + 1 < numbers.length; index += 1) {
    const one = numbers[index * 2];
    const other = numbers[index * 2 + 1];
    const first = split(one?.key, ".with");
    const second = split(other?.key, ".without");
    if (!first || !second || first.join("|") !== second.join("|")) continue;
    const [repoKey, fact, outcome] = first;
    out.push({
      repoKey,
      fact,
      outcome,
      sentence: rows[index]?.[0] ?? "",
      caveat: rows[index]?.[1] ?? "",
      withN: numberOrNull(one.with_n),
      withoutN: numberOrNull(one.without_n),
      withValue: numberOrNull(one.value),
      withoutValue: numberOrNull(other.value),
      coverage: numberOrNull(one.coverage),
    });
  }
  return out;
}

/** `observation.<repo_key>|<fact>|<outcome>.with` into its three parts. */
function split(key, suffix) {
  const text = String(key ?? "");
  if (!text.startsWith("observation.") || !text.endsWith(suffix)) return null;
  const parts = text.slice("observation.".length, text.length - suffix.length).split("|");
  return parts.length === 3 ? parts : null;
}

function numberOrNull(value) {
  const number = Number(value);
  return value === null || value === undefined || !Number.isFinite(number) ? null : number;
}

/**
 * The comparison rows: the engine's four cells, and the two values behind them when the
 * review is new enough to have stored them.
 *
 * The prototype read the two bars back out of the printed text with a regular
 * expression, which turned `713938k` into 713,938 and is the app owning a number. The
 * engine stores `value` and `previous_value` on the now-cell for exactly this, and a
 * review written before it did has no bars rather than parsed ones.
 *
 * @param {ReviewSection|null} section
 */
export function comparisons(section) {
  const numbers = numbersOf(section);
  return (section?.rows ?? []).map((row) => {
    const label = row[0] ?? "";
    const now = numbers.get(`compared.${label.replace(/ /g, "_")}.now`);
    return {
      label,
      nowText: row[1] ?? "",
      previousText: row[2] ?? "",
      changeText: row[3] ?? "",
      nowValue: numberOrNull(now?.value),
      previousValue: numberOrNull(now?.previous_value),
    };
  });
}

/**
 * Repository key to the name a reader knows it by.
 *
 * An observation's key carries the repository key, and only the `app_observation` rows
 * and the review row itself can turn one into a name. A key neither of them knows keeps
 * the key, which is what `app_review` and `app_observation` both do with `COALESCE`.
 *
 * @param {any} data
 * @param {Record<string, any>|null} review
 */
export function projectNames(data, review) {
  /** @type {Map<string, string>} */
  const out = new Map();
  for (const row of data?.observations ?? []) {
    if (row.repo_key && row.project) out.set(String(row.repo_key), String(row.project));
  }
  if (review?.repo_key && review?.project) out.set(String(review.repo_key), String(review.project));
  return out;
}

/** The paragraphs of a model segment, as it was written. Empty when there is none. */
export function segmentParagraphs(review) {
  const text = review?.segment_text;
  if (typeof text !== "string" || !text.trim()) return [];
  return text
    .split(/\n\n+/)
    .map((part) => part.trim())
    .filter((part) => part.length > 0);
}
