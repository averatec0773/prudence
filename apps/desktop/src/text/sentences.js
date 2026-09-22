/* Sentences the interface composes, in each language, from the row's own columns.
 *
 * Design rule 3: **a composed sentence is composed, never translated.** The engine writes
 * one English sentence per observation and stores it on the row; the interface rebuilds
 * it from the same columns so that it can be read in the reader's language. English is
 * therefore not free composition: it must come out **character for character equal to
 * `app_observation.sentence`**, and `test/sentences.test.mjs` checks that for every row
 * of the fixture. Chinese has no English to match and uses the reader's own words.
 *
 * This is a restatement of `src/prudence/store/observations.py`. When that file's phrases
 * change, the catalog's `observation.*` keys change with it and the test says so.
 */

import { count, day, list, percent, purposeInSentence, relative, stamp } from "./fmt.js";
import { lang as currentLang, t } from "./strings.js";

/** @typedef {import("./strings.js").Language} Language */

/**
 * The twelve behaviour facts the engine splits on. A fact not in this list is not an
 * error: the engine may grow one, and the sentence says "with <fact>" rather than
 * inventing a phrase for it.
 */
const SPLITS = [
  "commit_attempts_per_commit",
  "compactions",
  "context_resets",
  "files_edited_unread",
  "formatter_runs",
  "hand_edits_between_turns",
  "prompts_per_active_hour",
  "repeated_errors",
  "sittings",
  "subagent_used",
  "test_runs",
  "tests_before_commit",
];

/** `In beta`, or `Across your projects` for a row computed over all of them. */
function where(row) {
  if (row.pooled) return t("observation.where.pooled");
  return t("observation.where.project", row.project ?? row.repo_key ?? "");
}

/** What the sessions on the with-side of the split did. */
function didPhrase(fact, language) {
  if (typeof fact === "string" && fact.startsWith("purpose:")) {
    return t("observation.split.purpose", purposeInSentence(fact.slice("purpose:".length), language));
  }
  if (SPLITS.includes(fact)) return t(`observation.split.${fact}`);
  return t("observation.split.unknown", fact);
}

/** And what the ones on the other side did not. */
function didNotPhrase(fact) {
  if (typeof fact === "string" && fact.startsWith("purpose:")) {
    return t("observation.split.purpose.didNot");
  }
  if (SPLITS.includes(fact)) return t("observation.didNot");
  return t("observation.split.unknown.didNot");
}

/**
 * The observation, as one sentence.
 *
 * The two counts are **plain ungrouped integers**, not `Fmt.count`: the engine writes
 * `f"{n}"` and a thousands separator would break the comparison. The two shares go
 * through `Fmt.percent`, which rounds half to even for the same reason.
 *
 * @param {Record<string, any>} row one row of `app_observation`
 * @param {Language} [language]
 */
export function observationSentence(row, language) {
  const key = row.outcome === "rework" ? "observation.sentence.rework" : "observation.sentence.alive";
  return t(
    key,
    where(row),
    String(row.with_n),
    didPhrase(row.fact, language ?? currentLang()),
    percent(row.with_value, language),
    String(row.without_n),
    didNotPhrase(row.fact),
    percent(row.without_value, language)
  );
}

/**
 * The caveat under it: how much of the work the figure covers and how it was established.
 *
 * This is the one line the interface still assembles out of three columns of the same
 * row rather than reading whole. A `caveat` column beside `sentence` would remove it;
 * it is parked for contract 4 (the phase-1 plan, section 7).
 *
 * @param {Record<string, any>} row
 * @param {Language} [language]
 */
export function observationCaveat(row, language) {
  return t(
    "observation.methodLine",
    percent(row.coverage, language),
    String(row.fact_commits ?? 0),
    String(row.inferred_commits ?? 0)
  );
}

/**
 * A stored review, as one line.
 *
 * `app_review.headline` carries the engine's own English. This composes the reader's,
 * which is design rule 3 again. The Review screen's fuller wording is batch 6a's.
 *
 * @param {Record<string, any>} review
 * @param {Language} [language]
 */
export function reviewLine(review, language) {
  // The reader's own date, not the stored `yyyy-MM-dd`. The Review screen's head builds
  // the same key with `fmt.day` and the panel built it with a slice, so one review read
  // "Review 1, Sep 7, 2026 to Sep 21, 2026" in the window and "Review 1, 2026-09-07 to
  // 2026-09-21" in the panel, two feet apart on the same screen.
  const range = [review.range_start, review.range_end].map((value) =>
    day(String(value ?? "").slice(0, 10), language)
  );
  const scope = review.project ?? t("review.scope.everyProject");
  return t("review.headline.project", String(review.id), range[0], range[1], scope);
}

/**
 * Whether writing a review now would produce one, as one line.
 *
 * **The two halves are not the same kind of sentence, on purpose.** A review that is ready
 * gets the engine's own words, because the rule is the engine's and `prudence status`
 * states it in one line that the app should not reword; the app's own sentence is only the
 * fallback for an engine that printed none. A review that is not ready is composed here
 * out of the four numbers, in the reader's own language, because there the numbers are the
 * answer and an English clause in the middle of a Chinese screen is not.
 *
 * Null for no answer at all, which is what an engine that does not carry readiness gives:
 * saying "not ready" then would be the app inventing a verdict.
 *
 * @param {{ ready?: boolean, sentence?: string|null, newSessions?: number,
 *           requiredSessions?: number, maturedCommits?: number,
 *           requiredCommits?: number } | null | undefined} found
 * @param {Language} [language]
 * @returns {string}
 */
export function readinessSentence(found, language) {
  if (!found) return "";
  if (found.ready) return String(found.sentence || t("review.readiness.ready"));
  return t(
    "review.readiness.needs",
    count(Number(found.newSessions ?? 0), language),
    count(Number(found.requiredSessions ?? 0), language),
    count(Number(found.maturedCommits ?? 0), language),
    count(Number(found.requiredCommits ?? 0), language)
  );
}

/** `21 Sep 01:45 (13 hours ago)`, both halves in the reader's locale. */
/**
 * @param {string | number | Date | null | undefined} value
 * @param {Date} [now]
 * @param {Language} [language]
 */
export function stampedAgo(value, now, language) {
  if (!value) return t("menu.never");
  return t("menu.stamped", stamp(value, language), relative(value, now, language));
}

export { list };
