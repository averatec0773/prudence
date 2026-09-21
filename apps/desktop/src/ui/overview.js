/* Overview: the three totals, then the three charts.
 *
 * One column, cards first, which is variant A. Every figure comes from a view, every
 * share carries the number it is over, and colour is identity rather than judgement.
 */

import { heatStrip, linesWithGaps, stackedBars } from "../design/charts.js";
import { el } from "../design/dom.js";
import { PURPOSES } from "../design/purposes.js";
import {
  cards as readCards,
  heat as readHeat,
  outcomes as readOutcomes,
  projectColour,
  weeks as readWeeks,
} from "../store/overview.js";
import { count, day as formatDay, hours as formatHours, list, percent, purpose, sessions, tokens } from "../text/fmt.js";
import { t } from "../text/strings.js";

/** A figure with its caption above and its qualification below. */
function statCard(caption, value, detail) {
  return el("div", { class: "card stat" }, [
    el("div", { class: "label", text: caption }),
    el("div", { class: "value", text: value }),
    el("div", { class: "foot", text: detail ?? "" }),
  ]);
}

function panel(title, note, body, extra) {
  const head = el("div", { class: "panel-head" }, [el("h2", { text: title })]);
  if (extra) head.appendChild(extra);
  return el("div", { class: "card panel" }, [
    head,
    el("p", { class: "panel-note", text: note }),
    body,
  ]);
}

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
    const row = el("tr", {}, [el("td", { text: t("overview.weekOf", formatDay(week.week)) })]);
    for (const key of present) {
      row.appendChild(el("td", { text: week.byPurpose[key] ? tokens(week.byPurpose[key]) : t("common.dash") }));
    }
    row.appendChild(el("td", { text: tokens(week.total) }));
    body.appendChild(row);
  }
  table.appendChild(body);
  return table;
}

function emptyState(title, detail) {
  return el("div", { class: "empty" }, [
    el("div", { class: "empty-title", text: title }),
    el("div", { class: "empty-detail", text: detail }),
  ]);
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
      el("span", { text: t("overview.weekFilter", formatDay(week), tokens(totals.commits)) }),
    ]);
    const back = el("button", { class: "btn", type: "button", text: t("overview.showAllWeeks") });
    back.addEventListener("click", () => state.onWeek(null));
    note.appendChild(back);
    screen.appendChild(note);
  }

  /* --- tokens by purpose, per week ------------------------------------------------ */

  const weeks = readWeeks(data, { project, range });
  const hover = el("div", { class: "hover-value", text: t("chart.hint.weeks") });

  if (!weeks.length) {
    screen.appendChild(
      panel(
        t("overview.tokensByPurpose"),
        t("overview.tokensByPurpose.note"),
        emptyState(t("overview.noTokens.title"), t("overview.noTokens.detail"))
      )
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
      hover.textContent = `${t("overview.weekOf", formatDay(found.week))}: ${tokens(found.total)}. ${list(parts)}`;
    };

    const chart = stackedBars({
      weeks,
      selected: week,
      label: formatDay,
      caption: list(
        weeks.map((w) => `${t("overview.weekOf", formatDay(w.week))} ${tokens(w.total)}`)
      ),
      onHover: say,
      onSelect: state.onWeek,
    });

    screen.appendChild(
      panel(
        t("overview.tokensByPurpose"),
        t("overview.tokensByPurpose.note"),
        el("div", {}, [chart, hover, purposeLegend(present), weekTable(weeks)])
      )
    );
  }

  /* --- what became of each week's work -------------------------------------------- */

  const series = readOutcomes(data, { project, range });
  const allWeeks = [...new Set(series.flatMap((s) => s.points.map((p) => p.week)))].sort();
  const names = data.projects.map((row) => String(row.name));

  if (!series.length || !allWeeks.length) {
    screen.appendChild(
      panel(
        t("overview.whatBecame"),
        t("overview.whatBecame.note"),
        emptyState(t("overview.noOutcomes.title"), t("overview.noOutcomes.detail"))
      )
    );
  } else {
    const alive = linesWithGaps({
      weeks: allWeeks,
      series: series.map((one) => ({
        project: one.project,
        colour: projectColour(one.project, names),
        runs: one.runs.alive.map((run) => run.map((p) => ({ week: p.week, value: p.alive }))),
      })),
      coverage: series.flatMap((one) =>
        one.runs.alive.map((run) =>
          run.filter((p) => p.coverage !== null).map((p) => ({ week: p.week, value: p.coverage }))
        )
      ),
      caption: outcomeCaption(series, "alive"),
    });
    const rework = linesWithGaps({
      weeks: allWeeks,
      dashed: true,
      series: series.map((one) => ({
        project: one.project,
        colour: projectColour(one.project, names),
        runs: one.runs.rework.map((run) => run.map((p) => ({ week: p.week, value: p.rework }))),
      })),
      caption: outcomeCaption(series, "rework"),
    });

    const legend = el("div", { class: "legend" }, [
      el("span", { class: "key", text: t("overview.legend.alive") }),
      el("span", { class: "key", text: t("overview.legend.rework") }),
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
      panel(
        t("overview.whatBecame"),
        t("overview.whatBecame.note"),
        el("div", {}, [alive, rework, legend, outcomeTable(series)])
      )
    );
  }

  /* --- where the hours went -------------------------------------------------------- */

  const strip = readHeat(data, { project, range });
  if (!strip.weeks.length || strip.max <= 0) {
    screen.appendChild(
      panel(
        t("overview.whereTime"),
        t("overview.whereTime.note"),
        emptyState(t("overview.noHours.title"), t("overview.noHours.detail"))
      )
    );
  } else {
    const measured = strip.weeks
      .flatMap((column) => column.days)
      .filter((cell) => cell.hours !== null && cell.hours > 0);
    screen.appendChild(
      panel(
        t("overview.whereTime"),
        t("overview.whereTime.note"),
        heatStrip({
          weeks: strip.weeks,
          max: strip.max,
          title: (dayKey, hours) =>
            `${formatDay(dayKey)}: ${hours === null ? t("common.dash") : formatHours(hours)}`,
          caption: list(
            measured.map((cell) => `${formatDay(cell.day)} ${formatHours(cell.hours)}`)
          ),
        })
      )
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
      parts.push(`${one.project} ${formatDay(point.week)} ${percent(point[key])} ${t("chart.sampleSize", count(over))}`);
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
