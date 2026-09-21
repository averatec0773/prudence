/* Numbers and dates on their way to a screen, through the reader's locale.

   The port of `PrudenceUI/Fmt.swift`, function for function. The engine-facing half (what
   the CLI prints, what a UTC stamp means) is not here and is not this layer's business.

   **Two things deliberately do not go through the locale**, and both are marked where
   they are: the `%.0f%%` share and the plain ungrouped integer inside an observation
   sentence, which have to match `store/observations.py` character for character or the
   word-for-word test against `app_observation.sentence` fails. Everything else does. */

(function (global) {
  "use strict";

  var Str = global.Str;

  function locale() {
    return Str.lang();
  }

  /* --- counts ------------------------------------------------------------------- */

  /** `1,248`, `1 248`: whatever the locale groups with. */
  function count(value) {
    return new Intl.NumberFormat(locale(), { maximumFractionDigits: 0 }).format(value);
  }

  /** The same integer with no grouping at all. Only inside an observation sentence,
      where the engine writes `f"{n}"` and the English output has to equal it. */
  function plain(value) {
    return String(value);
  }

  function decimal(value, places) {
    return new Intl.NumberFormat(locale(), {
      minimumFractionDigits: places,
      maximumFractionDigits: places,
    }).format(value);
  }

  /** `1.2M`, `43.1k`, `812`. The unit letters are not translated: they are the same in
      both languages the app ships, and the mockups print them the same way. */
  function tokens(value) {
    if (value >= 1000000) return decimal(value / 1000000, 1) + "M";
    if (value >= 1000) return decimal(value / 1000, 1) + "k";
    return count(value);
  }

  function hours(value) {
    return decimal(value, 1);
  }

  /* --- shares ------------------------------------------------------------------- */

  /** `88%`, the way the CLI prints a share and the way an observation sentence must.
      Deliberately not `Intl.NumberFormat(style: "percent")`, which writes `88 %` in some
      locales and would break the word-for-word test. */
  function percent(share) {
    if (share === null || share === undefined || Number.isNaN(share)) return Str.t("common.dash");
    return Math.round(share * 100) + "%";
  }

  /** The distance between two shares, in points. Neutral: a gap has no sign. */
  function points(gap) {
    return String(Math.round(Math.abs(gap) * 100));
  }

  function pointsValue(gap) {
    return Math.round(Math.abs(gap) * 100);
  }

  /* --- time --------------------------------------------------------------------- */

  function asDate(value) {
    if (value instanceof Date) return value;
    if (typeof value === "number") return new Date(value);
    if (typeof value !== "string") return null;
    var parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }

  /** A `yyyy-MM-dd` day as a local Date at midnight, which is what the engine means by a
      day. `new Date("2026-09-21")` would be UTC midnight and can land on the day before. */
  function fromDay(day) {
    var parts = String(day).slice(0, 10).split("-");
    if (parts.length !== 3) return null;
    var date = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
    return Number.isNaN(date.getTime()) ? null : date;
  }

  /** `20 Sep 18:04`, `9月20日 18:04`. */
  function stamp(value) {
    var date = asDate(value);
    if (!date) return Str.t("common.dash");
    return new Intl.DateTimeFormat(locale(), {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(date);
  }

  /** `4 minutes ago`, `4 分钟前`, `never`, `just now`. */
  function relative(value, now) {
    var date = asDate(value);
    if (!date) return Str.t("menu.never");
    var reference = asDate(now) || new Date();
    var seconds = (reference.getTime() - date.getTime()) / 1000;
    if (seconds < 60) return Str.t("menu.justNow");

    var formatter = new Intl.RelativeTimeFormat(locale(), { numeric: "auto", style: "long" });
    var units = [
      ["year", 31536000],
      ["month", 2592000],
      ["week", 604800],
      ["day", 86400],
      ["hour", 3600],
      ["minute", 60],
    ];
    for (var i = 0; i < units.length; i += 1) {
      var size = units[i][1];
      if (Math.abs(seconds) >= size) {
        // Truncated, not rounded: `RelativeDateTimeFormatter` says "13 hours ago" for
        // thirteen and a half, and a panel that says 14 beside one that says 13 on the
        // same data reads as a bug in one of them.
        return formatter.format(-Math.trunc(seconds / size), units[i][0]);
      }
    }
    return Str.t("menu.justNow");
  }

  /** `20 Sep 2026`, `2026年9月20日`. */
  function day(value) {
    var date = fromDay(value);
    if (!date) return String(value);
    return new Intl.DateTimeFormat(locale(), {
      day: "numeric",
      month: "short",
      year: "numeric",
    }).format(date);
  }

  /** The axis form: `8 Sep`, `9月8日`. No year, because every axis here spans weeks. */
  function shortDay(value) {
    var date = fromDay(value);
    if (!date) return String(value);
    return new Intl.DateTimeFormat(locale(), { day: "numeric", month: "short" }).format(date);
  }

  /** `20 Sep 2026 (yesterday)`. Both halves go through the locale. A day is midnight, so
      "0 hours ago" for something written this morning is noise: the relative half counts
      in days and the absolute half carries the precision. */
  function writtenOn(value, now) {
    var absolute = day(value);
    var date = fromDay(value);
    if (!date) return absolute;
    var reference = asDate(now) || new Date();
    var startOfToday = new Date(
      reference.getFullYear(),
      reference.getMonth(),
      reference.getDate()
    );
    var days = Math.round((startOfToday.getTime() - date.getTime()) / 86400000);
    var text = new Intl.RelativeTimeFormat(locale(), { numeric: "auto", style: "long" }).format(
      -days,
      "day"
    );
    return Str.t("common.dateWithRelative", absolute, text);
  }

  /* --- phrases built from a count ----------------------------------------------- */

  /** The four that carry a count go through the plural entries, so English says
      "1 session" and "3 sessions" and Chinese says "1 个会话" either way. */
  function sessions(value) {
    return Str.plural("unit.sessions", value, count(value));
  }
  function commits(value) {
    return Str.plural("unit.commits", value, count(value));
  }
  function edits(value) {
    return Str.plural("unit.edits", value, count(value));
  }
  function projects(value) {
    return Str.plural("unit.projects", value, count(value));
  }

  /** These two carry a measure rather than a count: `6.2k tokens`, `0.1 hours`. A plural
      rule has nothing to choose on once the value has been rounded to `6.2k`. */
  function tokenPhrase(value) {
    return Str.t("unit.tokens", tokens(value));
  }
  function hourPhrase(value) {
    return Str.t("unit.hours", hours(value));
  }

  /** Join the way the language joins a list: `a, b, c` and `a，b，c`. */
  function list(parts) {
    return parts.join(Str.t("common.listSeparator"));
  }

  var PURPOSES = ["development", "research", "debugging", "conversation", "mixed", "unknown"];

  /** The purpose the reader sees. `unknown` is "other", never "unknown". A key this build
      has never heard of is printed as it came, never dropped. */
  function purpose(key) {
    return PURPOSES.indexOf(key) >= 0 ? Str.t("purpose." + key) : key;
  }

  /** The purpose **inside an observation sentence**. English keeps the engine's own
      label, because that sentence has to equal `app_observation.sentence` word for word
      and the engine writes `labelled unknown` where the interface says "other". Every
      other language gets the reader's word, since there is no English to match. */
  function purposeInSentence(key) {
    return Str.lang() === "en" ? key : purpose(key);
  }

  function weekday(key) {
    return Str.t("weekday." + key);
  }

  global.Fmt = {
    PURPOSES: PURPOSES,
    count: count,
    plain: plain,
    decimal: decimal,
    tokens: tokens,
    hours: hours,
    percent: percent,
    points: points,
    pointsValue: pointsValue,
    stamp: stamp,
    relative: relative,
    day: day,
    shortDay: shortDay,
    writtenOn: writtenOn,
    sessions: sessions,
    commits: commits,
    edits: edits,
    projects: projects,
    tokenPhrase: tokenPhrase,
    hourPhrase: hourPhrase,
    list: list,
    purpose: purpose,
    purposeInSentence: purposeInSentence,
    weekday: weekday,
    fromDay: fromDay,
  };
})(window);
