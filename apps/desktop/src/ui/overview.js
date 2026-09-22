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
  cards as readCards,
  heat as readHeat,
  outcomes as readOutcomes,
  projectColour,
  weeks as readWeeks,
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

/** The same numbers the picture has, as a table a reader can check. */
function weekTable(weeks) {
  const table = el("table", { class: "data" });
  const head = el("tr", {}, [el("th", { text: t("chart.period") })]);
  const present = PURPOSES.filter((key) => weeks.some((week) => week.byPurpose[key] > 0));
  for (const key of present) head.appendChild(el("th", { text: purpose(key) }));
  head.appendChild(el("th", { text: t("chart.value") }));
  table.appendChild(el("thead", {}, [head]));

  const body = el("tbody");
  for (const week of weeks) {
    const row = el("tr", { class: week.measured ? "" : "unmeasured" }, [
      el("td", { text: t("overview.weekOf", formatDay(week.week)) }),
    ]);
    for (const key of present) {
      row.appendChild(
        el("td", { text: week.byPurpose[key] ? tokens(week.byPurpose[key]) : t("common.dash") })
      );
    }
    // A week with no row at all has no total either. Printing 0 here would say the work
    // was measured and came to nothing, which is the one thing the chart above is careful
    // not to say.
    row.appendChild(el("td", { text: week.measured ? tokens(week.total) : t("common.dash") }));
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
 * @param {{ data: any, project: string|null, range: string, week: string|null,
 *           onWeek: (week: string|null) => void }} state
 */
export function overview(state) {
  const { data, project, range, week } = state;
  const screen = el("div", { class: "screen-body" });

  /* --- the three totals ---------------------------------------------------------- */

  const totals = readCards(data, { project, range, week });
  const weeks = readWeeks(data, { project, range });
  // One list of weeks, both charts. Ruling 1 of the delivery A review: the x axis is the
  // range's complete week list, so a week is in the same place in each chart.
  const axis = weeks.map((one) => one.week);
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

  // Clicking a week filters the three cards, and says so, with one way back.
  if (week) {
    const note = el("div", { class: "filter-note" }, [
      // The week's own token total, which is what the bar the user clicked represents.
      // This printed `totals.commits` through the token abbreviator and called it tokens.
      el("span", {
        text: t(
          "overview.weekFilter",
          formatDay(week),
          tokens(weeks.find((one) => one.week === week)?.total ?? 0)
        ),
      }),
    ]);
    const back = el("button", { class: "btn", type: "button", text: t("overview.showAllWeeks") });
    back.addEventListener("click", () => state.onWeek(null));
    note.appendChild(back);
    screen.appendChild(note);
  }

  /* --- tokens by purpose, per week ------------------------------------------------ */

  const hover = el("div", { class: "hover-value", text: t("chart.hint.weeks") });

  if (!weeks.some((week) => week.measured)) {
    screen.appendChild(
      panel({
        title: t("overview.tokensByPurpose"),
        note: t("overview.tokensByPurpose.note2"),
        body: emptyState(t("overview.noTokens.title"), t("overview.noTokens.detail")),
        extra: null,
        method: t("overview.tokensByPurpose.method"),
      })
    );
  } else {
    const present = new Set(PURPOSES.filter((key) => weeks.some((w) => w.byPurpose[key] > 0)));
    const say = (which) => {
      if (!which) {
        hover.textContent = t("chart.hint.weeks");
        return;
      }
      const found = weeks.find((w) => w.week === which);
      if (!found) return;
      const parts = [...present]
        .filter((key) => found.byPurpose[key] > 0)
        .map((key) => `${purpose(key)} ${tokens(found.byPurpose[key])}`);
      hover.textContent = t(
        "overview.weekReading",
        t("overview.weekOf", formatDay(found.week)),
        tokens(found.total),
        list(parts)
      );
    };

    const chart = stackedBars({
      weeks,
      selected: week,
      label: shortDay,
      axisFormat: tokenScale(niceMax(Math.max(0, ...weeks.map((one) => one.total)))),
      caption: list(
        weeks
          .filter((w) => w.measured)
          .map((w) => `${t("overview.weekOf", formatDay(w.week))} ${tokens(w.total)}`)
      ),
      onHover: say,
      onSelect: state.onWeek,
    });

    screen.appendChild(
      panel({
        title: t("overview.tokensByPurpose"),
        note: t("overview.tokensByPurpose.note2"),
        body: el("div", {}, [chart, hover, purposeLegend(present), weekTable(weeks)]),
        extra: null,
        method: t("overview.tokensByPurpose.method"),
      })
    );
  }

  /* --- what became of each week's work -------------------------------------------- */

  const series = readOutcomes(data, { project, range });
  // The same axis the bars above use, so a week sits at the same x in both charts.
  const allWeeks = axis;
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
        note: t("overview.whatBecame.note2"),
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
        note: t("overview.whatBecame.note2"),
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
        note: t("overview.whatBecame.note2"),
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
