/* Overview: the three totals, then the three charts.
 *
 * One column, cards first, which is variant A. Every figure comes from a view, every
 * share carries the number it is over, and colour is identity rather than judgement.
 */

import { heatStrip, linesWithGaps, niceMax, stackedBars } from "../design/charts.js";
import { el } from "../design/dom.js";
import { emptyState, panel, statCard } from "../design/components.js";
import { PURPOSES } from "../design/purposes.js";
import {
  buckets as readBuckets,
  cards as readCards,
  grainOf,
  heat as readHeat,
  outcomes as readOutcomes,
  projectColour,
  weekAxis,
} from "../store/overview.js";
import {
  count,
  day as formatDay,
  shortDay,
  hourPhrase,
  hours as formatHours,
  list,
  percent,
  purpose,
  sessions,
  tokenScale,
  tokens,
} from "../text/fmt.js";
import { plural, t } from "../text/strings.js";



/** Swatch and label per purpose, in the fixed order, wrapping. */
function purposeLegend(present) {
  const legend = el("div", { class: "legend" });
  for (const key of PURPOSES) {
    if (!present.has(key)) continue;
    const item = el("span", { class: "key" });
    const swatch = document.createElement("i");
    swatch.style.background = `var(--p-${key})`;
    item.appendChild(swatch);
    item.appendChild(document.createTextNode(purpose(key)));
    legend.appendChild(item);
  }
  return legend;
}

/**
 * A bucket's own name, in full: a day is its date, a week is the week it starts.
 *
 * One function, because every place a bucket is named has to name it the same way: the
 * table, the hover line, the caption and the filter note.
 */
function bucketName(key, grain) {
  return grain === "week" ? t("overview.weekOf", formatDay(key)) : formatDay(key);
}

/** The same numbers the picture has, as a table a reader can check. */
function bucketTable(buckets, grain) {
  const table = el("table", { class: "data" });
  const head = el("tr", {}, [el("th", { text: t("chart.period") })]);
  const present = PURPOSES.filter((key) => buckets.some((one) => one.byPurpose[key] > 0));
  for (const key of present) head.appendChild(el("th", { text: purpose(key) }));
  head.appendChild(el("th", { text: t("chart.value") }));
  table.appendChild(el("thead", {}, [head]));

  const body = el("tbody");
  for (const one of buckets) {
    const row = el("tr", { class: one.measured ? "" : "unmeasured" }, [
      el("td", { text: bucketName(one.bucket, grain) }),
    ]);
    for (const key of present) {
      row.appendChild(
        el("td", { text: one.byPurpose[key] ? tokens(one.byPurpose[key]) : t("common.dash") })
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
 * @param {{ data: any, project: string|null, range: string, bucket: string|null,
 *           onBucket: (bucket: string|null) => void }} state
 */
export function overview(state) {
  const { data, project, range, bucket } = state;
  const grain = grainOf(range);
  const screen = el("div", { class: "screen-body" });

  /* --- the three totals ---------------------------------------------------------- */

  const totals = readCards(data, { project, range, bucket });
  const buckets = readBuckets(data, { project, range });
  const cardRow = el("div", { class: "card-row" }, [
    statCard(
      t("overview.sessionsInRange"),
      count(totals.sessions),
      totals.sessions ? t("chart.sessionsShort") : ""
    ),
    statCard(
      t("overview.activeHours"),
      totals.hours === null ? t("common.dash") : formatHours(totals.hours),
      t("overview.sittingsNote")
    ),
    statCard(
      t("overview.commitsInRange"),
      count(totals.commits),
      t("overview.factInferred", count(totals.fact), count(totals.inferred))
    ),
  ]);
  screen.appendChild(cardRow);

  // Clicking a bucket filters the three cards, and says so, with one way back.
  if (bucket) {
    const note = el("div", { class: "filter-note" }, [
      // The bucket's own token total, which is what the bar the user clicked represents.
      // This printed `totals.commits` through the token abbreviator and called it tokens.
      el("span", {
        text: t(
          "overview.bucketFilter",
          bucketName(bucket, grain),
          tokens(buckets.find((one) => one.bucket === bucket)?.total ?? 0)
        ),
      }),
    ]);
    const back = el("button", { class: "btn", type: "button", text: t("overview.showWholeRange") });
    back.addEventListener("click", () => state.onBucket(null));
    note.appendChild(back);
    screen.appendChild(note);
  }

  /* --- tokens by purpose, per bucket ---------------------------------------------- */

  // The chart's own title, note, method and hint all say which grain is on the axis,
  // because "per day" and "per week" are different pictures and the reader has to know
  // which one they have. The title and the hint were the only two that switched: under a
  // daily chart the note said "What each week's tokens went on" and the method said the
  // figures were summed into the ISO week each day falls in, which is what the weekly
  // chart does and not what this one does.
  const chartTitle = grain === "week" ? "overview.tokensByPurpose" : "overview.tokensByPurposeDay";
  const chartNote =
    grain === "week" ? "overview.tokensByPurpose.note2" : "overview.tokensByPurpose.note2Day";
  const chartMethod =
    grain === "week" ? "overview.tokensByPurpose.method" : "overview.tokensByPurpose.methodDay";
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
    const present = new Set(PURPOSES.filter((key) => buckets.some((w) => w.byPurpose[key] > 0)));
    const say = (which) => {
      if (!which) {
        hover.textContent = t(hint);
        return;
      }
      const found = buckets.find((w) => w.bucket === which);
      if (!found) return;
      const parts = [...present]
        .filter((key) => found.byPurpose[key] > 0)
        .map((key) => `${purpose(key)} ${tokens(found.byPurpose[key])}`);
      hover.textContent = t(
        "overview.bucketReading",
        bucketName(found.bucket, grain),
        tokens(found.total),
        list(parts)
      );
    };

    const chart = stackedBars({
      buckets,
      selected: bucket,
      label: shortDay,
      axisFormat: tokenScale(niceMax(Math.max(0, ...buckets.map((one) => one.total)))),
      caption: list(
        buckets
          .filter((w) => w.measured)
          .map((w) => `${bucketName(w.bucket, grain)} ${tokens(w.total)}`)
      ),
      onHover: say,
      onSelect: state.onBucket,
    });

    screen.appendChild(
      panel({
        title: t(chartTitle),
        note: t(chartNote),
        body: el("div", {}, [chart, hover, purposeLegend(present), bucketTable(buckets, grain)]),
        extra: null,
        method: t(chartMethod),
      })
    );
  }

  /* --- what became of each week's work --------------------------------------------
   *
   * Weekly under every range, because `app_outcomes_by_week` is the only view that carries
   * an outcome and it has one row per week. The card's note says so, so that a reader on a
   * seven-day range is not left comparing a daily chart above with a weekly one here
   * without being told which is which.
   */

  const series = readOutcomes(data, { project, range });
  const allWeeks = weekAxis(data, { range });
  // On a daily range the note is the one that says this card is still weekly. Two whole
  // keys rather than two glued together: a sentence is composed in each language, and
  // joining two with an ASCII space puts a space after a full-width full stop in Chinese.
  const becameNote = t(
    grain === "week" ? "overview.whatBecame.note2" : "overview.whatBecame.note2Weekly"
  );
  // Every project that appears anywhere, not only those with a usage row: `data.projects`
  // comes from `app_usage_by_purpose_day`, so a repository with counted commits and no
  // session usage fell through `indexOf` to -1 and drew in the first project's colour.
  const names = [
    ...new Set([...data.projects.map((row) => String(row.name)), ...series.map((one) => one.project)]),
  ];

  // How many weeks actually carry a measurement decides which of three things this card
  // is: an empty state, a sentence saying a trend needs two points, or a chart.
  const measuredWeeks = new Set(
    series.flatMap((one) =>
      one.points.filter((p) => p.alive !== null || p.rework !== null).map((p) => p.week)
    )
  );

  if (!series.length || measuredWeeks.size === 0) {
    screen.appendChild(
      panel({
        title: t("overview.whatBecame"),
        note: becameNote,
        body: emptyState(t("overview.noOutcomes.title"), t("overview.noOutcomes.detail")),
        extra: null,
        method: t("overview.whatBecame.method"),
      })
    );
  } else if (measuredWeeks.size < 2) {
    // One dot in six hundred points of empty card is not a chart. Say it in words, and
    // keep the table, which is where the one measurement can actually be read.
    screen.appendChild(
      panel({
        title: t("overview.whatBecame"),
        note: becameNote,
        body: el("div", {}, [
          emptyState(
            t("overview.tooFewWeeks.title"),
            t("overview.tooFewWeeks.detail", measuredWeeksPhrase(measuredWeeks.size))
          ),
          outcomeTable(series),
        ]),
        extra: null,
        method: t("overview.whatBecame.method"),
      })
    );
  } else {
    const alive = linesWithGaps({
      weeks: allWeeks,
      label: shortDay,
      series: series.map((one) => ({
        project: one.project,
        colour: projectColour(one.project, names),
        runs: one.runs.alive.map((run) => run.map((p) => ({ week: p.week, value: p.alive }))),
      })),
      // Cut on coverage, not on alive. Filtering the nulls out of an alive run removed
      // the hole instead of honouring it, and the pale line was drawn straight across a
      // week whose coverage the engine never produced.
      coverage: series.flatMap((one) =>
        one.runs.coverage.map((run) => run.map((p) => ({ week: p.week, value: p.coverage })))
      ),
      caption: outcomeCaption(series, "alive"),
    });
    const rework = linesWithGaps({
      weeks: allWeeks,
      label: shortDay,
      dashed: true,
      series: series.map((one) => ({
        project: one.project,
        colour: projectColour(one.project, names),
        runs: one.runs.rework.map((run) => run.map((p) => ({ week: p.week, value: p.rework }))),
      })),
      caption: outcomeCaption(series, "rework"),
    });

    // The two charts are separate pictures with the same furniture, so each says which
    // it is. The legend keeps only what a picture cannot: which colour is which project.
    const legend = el("div", { class: "legend" }, [
      el("span", { class: "key", text: t("overview.legend.coverage") }),
    ]);
    for (const one of series) {
      const item = el("span", { class: "key" });
      const swatch = document.createElement("i");
      swatch.style.background = projectColour(one.project, names);
      item.appendChild(swatch);
      item.appendChild(document.createTextNode(one.project));
      legend.appendChild(item);
    }

    screen.appendChild(
      panel({
        title: t("overview.whatBecame"),
        note: becameNote,
        body: el("div", {}, [
          el("h3", { class: "chart-name", text: t("overview.stillAlive") }),
          alive,
          el("h3", { class: "chart-name", text: t("overview.reworkedLater") }),
          rework,
          legend,
          outcomeTable(series),
        ]),
        extra: null,
        method: t("overview.whatBecame.method"),
      })
    );
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

/** The table under the chart, so a figure can be checked without a pointer. */
function outcomeTable(series) {
  const table = el("table", { class: "data" });
  table.appendChild(
    el("thead", {}, [
      el("tr", {}, [
        el("th", { text: t("scope.project") }),
        el("th", { text: t("chart.period") }),
        el("th", { text: t("overview.legend.aliveName") }),
        el("th", { text: t("overview.legend.reworkName") }),
        el("th", { text: t("overview.legend.coverageName") }),
      ]),
    ])
  );
  const body = el("tbody");
  for (const one of series) {
    for (const point of one.points) {
      body.appendChild(
        el("tr", {}, [
          el("td", { text: one.project }),
          el("td", { text: formatDay(point.week) }),
          el("td", {
            text:
              point.alive === null
                ? t("common.dash")
                : t("chart.shareOver", percent(point.alive), count(point.measured30d)),
          }),
          el("td", {
            text:
              point.rework === null
                ? t("common.dash")
                : t("chart.shareOver", percent(point.rework), count(point.lines)),
          }),
          el("td", { text: point.coverage === null ? t("common.dash") : percent(point.coverage) }),
        ])
      );
    }
  }
  table.appendChild(body);
  return table;
}

export { sessions };
