/* Overview: what the window is over, then the figures, then the four charts.
 *
 * One column, and the reader's frame first. Every figure comes from a view, every share
 * carries the number it is over, and colour is identity rather than judgement.
 *
 * ## What the reader is told, and where
 *
 * Read against the founder's own store on 2026-09-22, this screen stated its method well
 * and its subject badly: the window was named once, in grey, in the subtitle, and every
 * figure below it had lost its time frame; two full tables repeated the two charts row for
 * row and were open by default; and one card carried two charts, two legends, a 70-word
 * note, a method and a table.
 *
 * So: the **summary line** at the top says what the figures are over, in one sentence, and
 * the three figures underneath are one strip rather than three cards. The **tables live
 * behind the disclosure that already says "how this is measured"**, which is the same
 * promise ("check this figure yourself") kept in the same drawer. And "What became of each
 * week's work" is **two cards**, one per question.
 */

import { heatStrip, linesWithGaps, niceMax, stackedBars } from "../design/charts.js";
import { el } from "../design/dom.js";
import { disclosure, emptyState, panel } from "../design/components.js";
import { BUCKETS, bucketColour } from "../design/buckets.js";
import {
  WEEKDAYS,
  buckets as readBuckets,
  cards as readCards,
  grainOf,
  heat as readHeat,
  heuristicTokens,
  outcomes as readOutcomes,
  projectColour,
  rangeOf,
  weekAxis,
} from "../store/overview.js";
import {
  bucket as bucketName,
  count,
  day as formatDay,
  shortDay,
  hourPhrase,
  hours as formatHours,
  list,
  monthName,
  percent,
  rangeName,
  sessions,
  commits as commitPhrase,
  tokenScale,
  tokens,
} from "../text/fmt.js";
import { plural, t } from "../text/strings.js";

/** Swatch and label per bucket, in the fixed order, wrapping. */
function bucketLegend(present) {
  const legend = el("div", { class: "legend" });
  for (const key of BUCKETS) {
    if (!present.has(key)) continue;
    const item = el("span", { class: "key" });
    const swatch = document.createElement("i");
    swatch.style.background = bucketColour(key);
    item.appendChild(swatch);
    item.appendChild(document.createTextNode(bucketName(key)));
    legend.appendChild(item);
  }
  return legend;
}

/**
 * A time slot's own name, in full: a day is its date, a week is the week it starts.
 *
 * One function, because every place a slot is named has to name it the same way: the
 * table, the hover line, the caption and the filter note.
 */
function slotName(key, grain) {
  return grain === "week" ? t("overview.weekOf", formatDay(key)) : formatDay(key);
}

/** The same numbers the picture has, as a table a reader can check: one row per day or
 *  week, one column per bucket, and the slot's total, which is where the per-slot totals
 *  are read now that the chart no longer prints them under itself. */
function bucketTable(buckets, grain) {
  const table = el("table", { class: "data" });
  const head = el("tr", {}, [el("th", { text: t("chart.period") })]);
  const present = BUCKETS.filter((key) => buckets.some((one) => one.byBucket[key] > 0));
  for (const key of present) head.appendChild(el("th", { text: bucketName(key) }));
  head.appendChild(el("th", { text: t("chart.value") }));
  table.appendChild(el("thead", {}, [head]));

  const body = el("tbody");
  for (const one of buckets) {
    const row = el("tr", { class: one.measured ? "" : "unmeasured" }, [
      el("td", { text: slotName(one.bucket, grain) }),
    ]);
    for (const key of present) {
      row.appendChild(
        el("td", { text: one.byBucket[key] ? tokens(one.byBucket[key]) : t("common.dash") })
      );
    }
    // A bucket with no row at all has no total either. Printing 0 here would say the work
    // was measured and came to nothing, which is the one thing the chart above is careful
    // not to say.
    row.appendChild(el("td", { text: one.measured ? tokens(one.total) : t("common.dash") }));
    body.appendChild(row);
  }
  table.appendChild(body);
  return table;
}

/** "3 measured weeks", through the catalogue's plural entry. */
function measuredWeeksPhrase(howMany) {
  return plural("unit.measuredWeeks", howMany, count(howMany));
}

/**
 * The method, and the table, in one drawer.
 *
 * A table that repeats a chart row for row exists so a figure can be checked without a
 * pointer, which is right; being open by default is what made this screen unreadable. At
 * 365 days the two tables were about 210 rows and most of the page's height. The summary
 * line says the table is in there, with the number of rows, so nothing is hidden by
 * accident.
 *
 * The table is built when the drawer is first opened, not when the screen is drawn. At 365
 * days it is up to two hundred rows nobody has asked to see yet.
 *
 * @param {string} method the card's own method sentence
 * @param {() => HTMLElement} table
 * @param {number} rows how many rows the table has
 */
function methodAndTable(method, table, rows) {
  return disclosure({
    summary: t("chart.methodAndTable", plural("unit.tableRows", rows, count(rows))),
    body: [el("p", { text: method })],
    deferred: () => [table()],
  });
}

/**
 * What the whole screen is over, in one sentence, above everything it frames.
 *
 * The window used to be stated once, in the subtitle, in grey, and three captions said "in
 * range" instead of naming it. Here it is said in the reader's own words, with the three
 * figures in the same breath, so that a reader four screens down has still been told what
 * the numbers are over.
 */
function summaryLine(totals, { project, range }) {
  const scope = project ?? t("scope.allProjects");
  const window =
    rangeOf(range).days === null
      ? t("overview.window.all")
      : t("overview.window.last", rangeName(rangeOf(range)));
  // Nothing about the hours where nothing measured them. A sentence cannot say "no active
  // hours" without claiming a measurement; the strip under it draws the dash, which is the
  // statement that belongs to a figure and not to prose.
  const figures = list([
    sessions(totals.sessions),
    ...(totals.hours === null ? [] : [t("overview.activeHoursPhrase", formatHours(totals.hours))]),
    commitPhrase(totals.commits),
  ]);
  return el("p", { class: "screen-summary", text: t("overview.summary", scope, window, figures) });
}

/**
 * The three figures, as one strip.
 *
 * Three cards took a full row to carry three numbers above charts that were starved of
 * width. Each figure carries its own unit, because "50.3" over the caption "Active hours"
 * is a unit one step away from the number, and the two words the engine lends this screen
 * (a sitting, and a commit that is fact or inferred) are glossed in the strip's own
 * drawer rather than left to be guessed.
 */
function figureStrip(totals) {
  const figure = (value, foot) =>
    el("div", { class: "figure" }, [
      el("div", { class: "value", text: value }),
      el("div", { class: "foot", text: foot }),
    ]);

  const strip = el("div", { class: "card figures" }, [
    el("div", { class: "figure-row" }, [
      figure(sessions(totals.sessions), ""),
      figure(
        totals.hours === null
          ? t("common.dash")
          : t("overview.activeHoursPhrase", formatHours(totals.hours)),
        t("overview.sittingsNote")
      ),
      figure(
        commitPhrase(totals.commits),
        t("overview.factInferred", count(totals.fact), count(totals.inferred))
      ),
    ]),
  ]);
  strip.appendChild(
    disclosure({
      summary: t("chart.method"),
      body: [el("p", { text: t("overview.figures.method") })],
    })
  );
  return strip;
}

/**
 * @param {{ data: any, project: string|null, range: string, bucket: string|null,
 *           onBucket: (bucket: string|null) => void }} state
 */
export function overview(state) {
  const { data, project, range, bucket } = state;
  const grain = grainOf(range);
  const screen = el("div", { class: "screen-body" });

  /* --- what this is over, and the three figures ----------------------------------- */

  // The summary line always states the whole window, because that is the frame the screen
  // is read in; the strip states the bucket when one is chosen. The same read serves both
  // when nothing is chosen, which is every draw but one.
  const whole = readCards(data, { project, range });
  const totals = bucket ? readCards(data, { project, range, bucket }) : whole;
  const buckets = readBuckets(data, { project, range });
  screen.appendChild(summaryLine(whole, { project, range }));
  screen.appendChild(figureStrip(totals));

  // Clicking a bucket filters the three figures, and says so, with one way back. The
  // summary line above keeps the whole window, which is what the figures go back to.
  if (bucket) {
    const note = el("div", { class: "filter-note" }, [
      // The bucket's own token total, which is what the bar the user clicked represents.
      // This printed `totals.commits` through the token abbreviator and called it tokens.
      el("span", {
        text: t(
          "overview.bucketFilter",
          slotName(bucket, grain),
          tokens(buckets.find((one) => one.bucket === bucket)?.total ?? 0)
        ),
      }),
    ]);
    const back = el("button", { class: "btn", type: "button", text: t("overview.showWholeRange") });
    back.addEventListener("click", () => state.onBucket(null));
    note.appendChild(back);
    screen.appendChild(note);
  }

  /* --- tokens by what each reply did, per day or week ------------------------------ */

  // The chart's own title, note, method and hint all say which grain is on the axis,
  // because "per day" and "per week" are different pictures and the reader has to know
  // which one they have. The title and the hint were the only two that switched: under a
  // daily chart the note said "What each week's tokens went on" and the method said the
  // figures were summed into the ISO week each day falls in, which is what the weekly
  // chart does and not what this one does.
  const chartTitle = grain === "week" ? "overview.tokensByBucket" : "overview.tokensByBucketDay";
  const chartNote =
    grain === "week" ? "overview.tokensByBucket.note2" : "overview.tokensByBucket.note2Day";
  const chartMethod =
    grain === "week" ? "overview.tokensByBucket.method" : "overview.tokensByBucket.methodDay";
  const hint = grain === "week" ? "chart.hint.weeks" : "chart.hint.days";
  const hover = el("div", { class: "hover-value", text: t(hint) });

  if (!buckets.some((one) => one.measured)) {
    screen.appendChild(
      panel({
        title: t(chartTitle),
        note: t(chartNote),
        body: emptyState(t("overview.noTokens.title"), t("overview.noTokens.detail")),
        extra: null,
        method: t(chartMethod),
      })
    );
  } else {
    const present = new Set(BUCKETS.filter((key) => buckets.some((w) => w.byBucket[key] > 0)));
    const say = (which) => {
      if (!which) {
        hover.textContent = t(hint);
        return;
      }
      const found = buckets.find((w) => w.bucket === which);
      if (!found) return;
      const parts = [...present]
        .filter((key) => found.byBucket[key] > 0)
        .map((key) => `${bucketName(key)} ${tokens(found.byBucket[key])}`);
      hover.textContent = t(
        "overview.bucketReading",
        slotName(found.bucket, grain),
        tokens(found.total),
        list(parts)
      );
    };

    const chart = stackedBars({
      buckets,
      selected: bucket,
      label: shortDay,
      axisFormat: tokenScale(niceMax(Math.max(0, ...buckets.map((one) => one.total)))),
      axisUnit: t("chart.unit.tokens"),
      caption: list(
        buckets
          .filter((w) => w.measured)
          .map((w) => `${slotName(w.bucket, grain)} ${tokens(w.total)}`)
      ),
      onHover: say,
      onSelect: state.onBucket,
    });

    // The tokens whose bucket is a guess from a tool's name, said quietly under the legend
    // when there are any and not at all when there are none: a line reading "0 tokens were
    // guessed" on every range would be noise about a thing that did not happen.
    const guessed = heuristicTokens(buckets);
    const body = el("div", {}, [chart, hover, bucketLegend(present)]);
    if (guessed.tokens > 0) {
      body.appendChild(
        el("p", {
          class: "panel-note",
          text: t(
            "overview.tokensByBucket.heuristic",
            tokens(guessed.tokens),
            percent(guessed.share)
          ),
        })
      );
    }

    screen.appendChild(
      panel({
        title: t(chartTitle),
        note: t(chartNote),
        body,
        extra: null,
        method: methodAndTable(
          t(chartMethod),
          () => bucketTable(buckets, grain),
          buckets.length
        ),
      })
    );
  }

  /* --- what became of each week's work, as two cards --------------------------------
   *
   * One question per card. It was one card carrying two charts with different line styles,
   * a legend whose first entry was not a project, a seventy-word note, a method and a
   * table: the card a reader most needs and the one they were least likely to finish.
   *
   * Weekly under every range, because `app_outcomes_by_week` is the only view that carries
   * an outcome and it has one row per week. Each card's note says so under a daily range,
   * so that a reader on a seven-day range is not left comparing a daily chart above with a
   * weekly one here without being told which is which.
   */

  const series = readOutcomes(data, { project, range });
  const allWeeks = weekAxis(data, { range });
  // Every project that appears anywhere, not only those with a session: `data.projects`
  // comes from `app_session_list`, so a repository with counted commits and no session
  // would fall through `indexOf` to -1 and draw in the first project's colour.
  const names = [
    ...new Set([...data.projects.map((row) => String(row.name)), ...series.map((one) => one.project)]),
  ];

  for (const kind of /** @type {const} */ (["alive", "rework"])) {
    screen.appendChild(outcomeCard({ kind, series, allWeeks, names, grain }));
  }

  /* --- where the hours went -------------------------------------------------------- */

  const strip = readHeat(data, { project, range });
  if (!strip.weeks.length || strip.max <= 0) {
    screen.appendChild(
      panel({
        title: t("overview.whereTime"),
        note: t("overview.whereTime.note2"),
        body: emptyState(t("overview.noHours.title"), t("overview.noHours.detail")),
        extra: null,
        method: t("overview.whereTime.method"),
      })
    );
  } else {
    const measured = strip.weeks
      .flatMap((column) => column.days)
      .filter((cell) => cell.hours !== null && cell.hours > 0);
    screen.appendChild(
      panel({
        title: t("overview.whereTime"),
        note: t("overview.whereTime.note2"),
        body: heatStrip({
          weeks: strip.weeks,
          max: strip.max,
          // The axis the strip did not have. Seven rows of squares said nowhere which one
          // was Monday, and the day was only inside each cell's `title`, which a pointer
          // reaches and a screenshot does not.
          weekdays: WEEKDAYS.map((key) => t(`weekday.${key}`)),
          monthOf: (week) => monthName(week),
          // With the unit: the figcaption is the only place a screenshot reader can get
          // these values, and "Sep 16, 2026 1.5" does not say 1.5 of what.
          title: (dayKey, hours) =>
            t(
              "overview.dayHours",
              formatDay(dayKey),
              hours === null ? t("common.dash") : hourPhrase(hours)
            ),
          caption: list(
            measured.map((cell) => t("overview.dayHours", formatDay(cell.day), hourPhrase(cell.hours)))
          ),
        }),
        method: t("overview.whereTime.method"),
      })
    );
  }

  return screen;
}

/* --- one outcome, one card -------------------------------------------------------- */

/** The two questions this pair of cards asks, and everything that differs between them. */
const OUTCOMES = {
  alive: {
    title: "overview.stillAlive",
    note: "overview.stillAlive.note2",
    noteWeekly: "overview.stillAlive.note2Weekly",
    method: "overview.stillAlive.method",
    column: "overview.legend.aliveName",
    /** The coverage band is drawn behind this one and not behind the other, because it is
     *  the context for what survived: how much of that week's committed work the sessions
     *  themselves wrote. */
    band: true,
    dashed: false,
  },
  rework: {
    title: "overview.reworkedLater",
    note: "overview.reworkedLater.note2",
    noteWeekly: "overview.reworkedLater.note2Weekly",
    method: "overview.reworkedLater.method",
    column: "overview.legend.reworkName",
    band: false,
    dashed: true,
  },
};

/**
 * One card: the question, the chart, who is who, and the figures in a table behind the
 * disclosure.
 *
 * @param {{ kind: "alive"|"rework", series: any[], allWeeks: string[], names: string[],
 *           grain: string }} options
 */
function outcomeCard({ kind, series, allWeeks, names, grain }) {
  const shape = OUTCOMES[kind];
  const title = t(shape.title);
  const note = t(grain === "week" ? shape.note : shape.noteWeekly);
  const table = () => outcomeTable(series, kind);
  const rows = series.reduce((sum, one) => sum + one.points.length, 0);

  // How many weeks actually carry a measurement of **this** question decides which of
  // three things the card is: an empty state, a sentence saying a trend needs two points,
  // or a chart.
  const measuredWeeks = new Set(
    series.flatMap((one) => one.points.filter((p) => p[kind] !== null).map((p) => p.week))
  );

  if (!series.length || measuredWeeks.size === 0) {
    return panel({
      title,
      note,
      body: emptyState(t("overview.noOutcomes.title"), t("overview.noOutcomes.detail")),
      extra: null,
      method: t(shape.method),
    });
  }

  if (measuredWeeks.size < 2) {
    // One dot in six hundred points of empty card is not a chart. Say it in words, and
    // keep the table, which is where the one measurement can actually be read.
    return panel({
      title,
      note,
      body: emptyState(
        t("overview.tooFewWeeks.title"),
        t("overview.tooFewWeeks.detail", measuredWeeksPhrase(measuredWeeks.size))
      ),
      extra: null,
      method: methodAndTable(t(shape.method), table, rows),
    });
  }

  const chart = linesWithGaps({
    weeks: allWeeks,
    label: shortDay,
    dashed: shape.dashed,
    series: series.map((one) => ({
      project: one.project,
      colour: projectColour(one.project, names),
      runs: one.runs[kind].map((run) => run.map((p) => ({ week: p.week, value: p[kind] }))),
    })),
    // Cut on coverage, not on alive. Filtering the nulls out of an alive run removed the
    // hole instead of honouring it, and the pale line was drawn straight across a week
    // whose coverage the engine never produced.
    coverage: shape.band
      ? series.flatMap((one) =>
          one.runs.coverage.map((run) => run.map((p) => ({ week: p.week, value: p.coverage })))
        )
      : [],
    caption: outcomeCaption(series, kind),
  });

  // The legend keeps only what a picture cannot: which colour is which project. The
  // coverage is drawn as the band it is, which is what it looks like in the chart, rather
  // than as a swatch in a row of projects, where it read as a project of its own.
  const legend = el("div", { class: "legend" });
  for (const one of series) {
    const item = el("span", { class: "key" });
    const swatch = document.createElement("i");
    swatch.style.background = projectColour(one.project, names);
    item.appendChild(swatch);
    item.appendChild(document.createTextNode(one.project));
    legend.appendChild(item);
  }
  if (shape.band) {
    const item = el("span", { class: "key" });
    const band = document.createElement("i");
    band.className = "band";
    band.style.background = "var(--coverage)";
    item.appendChild(band);
    item.appendChild(document.createTextNode(t("overview.legend.coverageName")));
    legend.appendChild(item);
  }

  return panel({
    title,
    note,
    body: el("div", {}, [chart, legend]),
    extra: null,
    method: methodAndTable(t(shape.method), table, rows),
  });
}

/** Every measured point, with its denominator, in words. */
function outcomeCaption(series, key) {
  const parts = [];
  for (const one of series) {
    for (const point of one.points) {
      if (point[key] === null) continue;
      const over = key === "alive" ? point.measured30d : point.lines;
      parts.push(
        t("chart.pointReading", one.project, formatDay(point.week), percent(point[key]), count(over))
      );
    }
  }
  return list(parts);
}

/**
 * The table behind one card's disclosure, so a figure can be checked without a pointer.
 *
 * One card, one question, so one share column. The coverage is on the card that draws the
 * band and not on the other, for the same reason the band is.
 */
function outcomeTable(series, kind) {
  const head = el("tr", {}, [
    el("th", { text: t("scope.project") }),
    el("th", { text: t("chart.period") }),
    el("th", { text: t(OUTCOMES[kind].column) }),
  ]);
  if (OUTCOMES[kind].band) head.appendChild(el("th", { text: t("overview.legend.coverageName") }));

  const table = el("table", { class: "data" }, [el("thead", {}, [head])]);
  const body = el("tbody");
  for (const one of series) {
    for (const point of one.points) {
      const over = kind === "alive" ? point.measured30d : point.lines;
      const row = el("tr", {}, [
        el("td", { text: one.project }),
        el("td", { text: formatDay(point.week) }),
        el("td", {
          text:
            point[kind] === null
              ? t("common.dash")
              : t("chart.shareOver", percent(point[kind]), count(over)),
        }),
      ]);
      if (OUTCOMES[kind].band) {
        row.appendChild(
          el("td", { text: point.coverage === null ? t("common.dash") : percent(point.coverage) })
        );
      }
      body.appendChild(row);
    }
  }
  table.appendChild(body);
  return table;
}
