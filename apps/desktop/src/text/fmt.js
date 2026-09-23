/* Numbers and dates on their way to a screen, in the reader's locale.
 *
 * This layer answers to `store/observations.py` and to `Intl`, in that order. It is
 * **not** a translation of `PrudenceUI/Fmt.swift`: an earlier version said it was "the
 * port, function for function", and carrying the shape rather than the requirement is
 * how it ended up rounding differently from the engine (see `percent`) and describing
 * date orders it does not produce.
 *
 * Every function takes an optional `language`, so a test can format at a fixed language
 * without touching global state. The Swift original did the same and the first port
 * dropped it, which is most of why none of these had a test.
 */

import { LANGUAGES, plural, tIn, lang as currentLang } from "./strings.js";
import { PURPOSES, known } from "../design/purposes.js";

/** @typedef {import("./strings.js").Language} Language */

function langOf(language) {
  return language ?? currentLang();
}

/* --- counts ------------------------------------------------------------------------ */

/** `1,248`, `1 248`: whatever the locale groups with. */
export function count(value, language) {
  return new Intl.NumberFormat(langOf(language), { maximumFractionDigits: 0 }).format(value);
}

export function decimal(value, places, language) {
  return new Intl.NumberFormat(langOf(language), {
    minimumFractionDigits: places,
    maximumFractionDigits: places,
  }).format(value);
}

/** `1.2M`, `43.1k`, `812`. The unit letters are not translated: they are the same in
 *  both languages the app ships. */
export function tokens(value, language) {
  // Billions are not hypothetical: the founder's own store holds 9.7 billion tokens, and
  // without this rung a single week reads "1,316.1M" on a chart axis. Found by drawing
  // the Overview against a copy of the real store rather than the fixture.
  if (value >= 1_000_000_000) return `${decimal(value / 1_000_000_000, 1, language)}B`;
  if (value >= 1_000_000) return `${decimal(value / 1_000_000, 1, language)}M`;
  if (value >= 1_000) return `${decimal(value / 1_000, 1, language)}k`;
  return count(value, language);
}

/**
 * A scale of token values that all read in the same unit.
 *
 * `tokens` picks a unit per value, which is right in a sentence and wrong on an axis: a
 * chart whose labels ran "1.5B, 1.1B, 750.0M, 375.0M" made the reader convert between
 * two units to compare four gridlines. The unit comes from the largest value and every
 * label uses it.
 *
 * @param {number} max the top of the scale
 * @param {string} [language]
 * @returns {(value: number) => string}
 */
export function tokenScale(max, language) {
  const [size, suffix] =
    max >= 1_000_000_000
      ? [1_000_000_000, "B"]
      : max >= 1_000_000
        ? [1_000_000, "M"]
        : max >= 1_000
          ? [1_000, "k"]
          : [1, ""];
  // The number of decimals comes from the top of the scale, not from each value, or one
  // axis reads "3.0k, 6.0k, 9.0k, 12k".
  const places = max / size < 10 ? 1 : 0;
  return (value) => {
    if (value === 0) return count(0, language);
    return size === 1 ? count(value, language) : `${decimal(value / size, places, language)}${suffix}`;
  };
}

export function hours(value, language) {
  return decimal(value, 1, language);
}

/* --- shares ------------------------------------------------------------------------ */

/**
 * Round half to even, which is what C's `%.0f` and Python's `%` operator do.
 *
 * The engine writes an observation's shares with `f"{x:.0f}%"`, and the interface has to
 * rebuild that sentence character for character or the comparison against
 * `app_observation.sentence` fails. `Math.round` rounds half **away from zero**, so it
 * disagrees on every exact half: the engine says `12%` for 12.5 and `Math.round` says
 * `13%`. Only exact halves differ, which is why nothing caught it by eye.
 */
function roundHalfToEven(value) {
  const floor = Math.floor(value);
  const rest = value - floor;
  if (rest > 0.5) return floor + 1;
  if (rest < 0.5) return floor;
  return floor % 2 === 0 ? floor : floor + 1;
}

/** `88%`, the way the engine prints a share. Deliberately not
 *  `Intl.NumberFormat(style: "percent")`, which writes `88 %` in some locales. */
export function percent(share, language) {
  if (share === null || share === undefined || Number.isNaN(share)) {
    return tIn(langOf(language), "common.dash");
  }
  return `${roundHalfToEven(share * 100)}%`;
}

/* --- time -------------------------------------------------------------------------- */

function asDate(value) {
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;
  if (typeof value === "number") return new Date(value);
  if (typeof value !== "string") return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

/**
 * A `yyyy-MM-dd` day as a local `Date` at midnight, which is what the engine means by a
 * day. `new Date("2026-09-21")` is UTC midnight and lands on the day before in the
 * Americas.
 */
export function fromDay(day) {
  const parts = String(day).slice(0, 10).split("-");
  if (parts.length !== 3) return null;
  const date = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
  return Number.isNaN(date.getTime()) ? null : date;
}

/**
 * A time, in the order the reader's language writes one: `Sep 20, 18:04`, `9月20日 18:04`.
 *
 * The order is the locale's, not a fixed one. The Swift app asked ICU for a *template*
 * and got the same answer; an earlier version of this file used component options and
 * then claimed in a comment to produce `20 Sep 18:04`, which is the British form and not
 * what `en` resolves to.
 */
export function stamp(value, language) {
  const date = asDate(value);
  if (!date) return tIn(langOf(language), "common.dash");
  return new Intl.DateTimeFormat(langOf(language), {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

/**
 * `4 minutes ago`, `yesterday`, `4 分钟前`, `never`.
 *
 * `numeric: "auto"` is deliberate and is a difference from the Swift app, which says
 * "1 day ago": "yesterday" is what English actually says, and the standard is the app's
 * own quality rather than the other client's wording.
 *
 * Truncated rather than rounded, so thirteen and a half hours reads as thirteen.
 *
 * `style` is `Intl`'s own: `long` everywhere there is room, and `narrow` (`13h ago`) in the
 * window's status row, which has a sidebar's width for the whole line. Chinese writes the
 * same characters in all three.
 *
 * **Known limit:** the unit boundaries are fixed seconds, so "1 month ago" means thirty
 * days rather than a calendar month. Registered in `DESIGN.md`; it shows only for
 * timestamps months old, and the only one the app prints is the last ingest.
 *
 * @param {any} value
 * @param {any} [now]
 * @param {Language} [language]
 * @param {"long"|"short"|"narrow"} [style]
 */
export function relative(value, now, language, style = "long") {
  const date = asDate(value);
  if (!date) return tIn(langOf(language), "menu.never");
  const reference = asDate(now) ?? new Date();
  const seconds = (reference.getTime() - date.getTime()) / 1000;
  if (seconds < 60) return tIn(langOf(language), "menu.justNow");

  const formatter = new Intl.RelativeTimeFormat(langOf(language), {
    numeric: "auto",
    style,
  });
  /** @type {[Intl.RelativeTimeFormatUnit, number][]} */
  const units = [
    ["year", 31_536_000],
    ["month", 2_592_000],
    ["week", 604_800],
    ["day", 86_400],
    ["hour", 3_600],
    ["minute", 60],
  ];
  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size) return formatter.format(-Math.trunc(seconds / size), unit);
  }
  return tIn(langOf(language), "menu.justNow");
}

/** A day, in the order the reader's language writes one. */
export function day(value, language) {
  const date = fromDay(value);
  if (!date) return String(value);
  return new Intl.DateTimeFormat(langOf(language), {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(date);
}

/**
 * A day with the year left off: what goes under a bar on an axis.
 *
 * The full form is about eleven characters and there can be twenty of them across one
 * card. The year is the same for every label in a range anyway, and the card's own
 * subtitle carries the range, so it is the part that can go.
 */
export function shortDay(value, language) {
  const date = fromDay(value);
  if (!date) return String(value);
  return new Intl.DateTimeFormat(langOf(language), { day: "numeric", month: "short" }).format(date);
}

/**
 * A day as `2026-05-14` in both languages, for a column of days read against each other.
 *
 * Numeric and fixed width, not the reader's own order. `2026年5月14日` is eleven characters
 * that break anywhere, which put two dates on two lines each in the founder's screenshot
 * of the repositories list, and a column of days being compared reads better aligned than
 * idiomatic. The engine writes its timestamps in this order already, so the day is its own
 * first ten characters, checked through `fromDay` so that something that is not a day is a
 * dash rather than ten characters of anything.
 */
export function isoDay(value, language) {
  if (value === null || value === undefined || value === "") {
    return tIn(langOf(language), "common.dash");
  }
  const date = fromDay(String(value).slice(0, 10));
  if (!date) return tIn(langOf(language), "common.dash");
  const pad = (part) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/**
 * A month on its own, for the band under the heat strip: `Sep`, `9月`.
 *
 * The strip's columns are weeks and its band names the month each one starts in, so the
 * label carries no day and no year. The year is the same for every column of a range that
 * the strip can draw, and the caption under it carries every cell's full date anyway.
 */
export function monthName(value, language) {
  const date = fromDay(value);
  if (!date) return String(value);
  return new Intl.DateTimeFormat(langOf(language), { month: "short" }).format(date);
}

/* --- phrases built from a count ----------------------------------------------------- */

/** The ones that carry a count go through the catalog's plural entries. */
export function sessions(value, language) {
  return plural("unit.sessions", value, count(value, language), language);
}
export function commits(value, language) {
  return plural("unit.commits", value, count(value, language), language);
}
/** What a surface is over, where it is over all of them: `3 projects`. */
export function projects(value, language) {
  return plural("unit.projects", value, count(value, language), language);
}
/** What a survival share is over: `1,204 lines`. */
export function lines(value, language) {
  return plural("unit.lines", value, count(value, language), language);
}

/** These two carry a measure rather than a count: `6.2k tokens`, `0.1 hours`. A plural
 *  rule has nothing to choose on once the value has been rounded to `6.2k`. */
export function tokenPhrase(value, language) {
  return tIn(langOf(language), "unit.tokens", tokens(value, language));
}
export function hourPhrase(value, language) {
  return tIn(langOf(language), "unit.hours", hours(value, language));
}

/**
 * A range's own name on the picker: a day count in the reader's plural, or "All".
 *
 * Composed rather than listed as seven keys. Seven near-identical entries in each table is
 * seven chances for one of them to be worded differently from the rest, and English needs
 * the singular for one day where Chinese does not, which is exactly what a plural entry is
 * for. The count is formatted in the reader's locale first, so a year reads `365 days` and
 * not `365 days` beside a grouped figure somewhere else.
 *
 * @param {{ days: number|null }} range one row of `store/overview.js`'s `RANGES`
 * @param {Language} [language]
 */
export function rangeName(range, language) {
  if (range.days === null) return tIn(langOf(language), "range.all");
  return plural("unit.rangeDays", range.days, count(range.days, language), language);
}

/** Join the way the language joins a list: `a, b, c` and `a，b，c`. */
export function list(parts, language) {
  return parts.join(listSeparator(language));
}

/** The same separator, for a list whose parts are elements rather than strings. The panel
 *  colours each bucket in its own sentence, so the parts are spans and the joins are text
 *  nodes between them; the punctuation still comes from the language and not from JS. */
export function listSeparator(language) {
  return tIn(langOf(language), "common.listSeparator");
}

/** What a reply did, in the reader's word: `change`, `run`, `read`, `talk`. */
export function bucket(key, language) {
  return tIn(langOf(language), `bucket.${key}`);
}

/** The purpose the reader sees. `unknown` is "other", never "unknown". */
export function purpose(key, language) {
  return tIn(langOf(language), `purpose.${known(key)}`);
}

/**
 * The purpose **inside an observation sentence**. English keeps the engine's own raw
 * label, because that sentence has to equal `app_observation.sentence` word for word and
 * the engine writes `labelled unknown` where the interface says "other". Every other
 * language gets the reader's word, since there is no English to match.
 */
export function purposeInSentence(key, language) {
  return langOf(language) === "en" ? key : purpose(key, language);
}

export { LANGUAGES, PURPOSES };
