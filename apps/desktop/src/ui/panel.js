/* The menu bar panel: one column, a caption above every block, the actions at the foot.
 *
 * The variant the founder settled on (M4 plan, "Variant choices", and their clarification
 * the next day: content in the centre, not titles left and values right).
 *
 * Nothing in this file knows it is inside a Tauri window.
 */

import * as Bridge from "../bridge.js";
import { miniStack } from "../design/charts.js";
import { el } from "../design/dom.js";
import { mark } from "../design/brand.js";
import { hourPhrase, list, percent, purpose, sessions, commits, tokenPhrase, day } from "../text/fmt.js";
import { observationCaveat, observationSentence, reviewLine, stampedAgo } from "../text/sentences.js";
import { PRODUCT_NAME, t } from "../text/strings.js";
import { lastSevenDays, purposeShares, today } from "../store/payload.js";

/** Set by `render`, so the size report can run again when the content changes. */
let refit = () => {};

function text(content, className) {
  return el("span", { class: className ?? "", text: content });
}

/** A caption on its own line and the content full width under it. */
function block(caption, node) {
  return el("div", { class: "pop-block" }, [el("span", { class: "k", text: caption }), node]);
}

function head(data) {
  const bar = el("div", { class: "pop-head" });
  const brand = mark(18);
  brand.classList.add("brand-mark");
  bar.appendChild(brand);
  bar.appendChild(el("span", { class: "name", text: PRODUCT_NAME }));
  bar.appendChild(
    el("span", { class: "ver", text: `prudence ${data.status?.engine_version ?? ""}` })
  );
  return bar;
}

function todayBlock(data) {
  const now = today(data);
  const counted = now.sessions > 0 || now.commits > 0;
  const wrap = el("div");
  wrap.appendChild(
    el("div", {
      class: counted ? "headline" : "obs-line",
      text: counted ? list([sessions(now.sessions), commits(now.commits)]) : t("menu.noSessionsToday"),
    })
  );
  wrap.appendChild(el("div", { class: "headline-sub", text: day(now.day) }));
  return wrap;
}

function weekBlock(data) {
  const week = lastSevenDays(data);
  const shares = purposeShares(week);
  const summary = shares.length
    ? list(shares.map((part) => `${purpose(part.purpose)} ${percent(part.share)}`))
    : t("menu.noTokensThisWeek");

  const wrap = el("div", { class: "week-row" });
  wrap.appendChild(text(summary, "obs-line"));
  wrap.appendChild(
    miniStack({
      byPurpose: week.byPurpose,
      height: 8,
      caption: `${t("menu.thisWeek")}: ${summary} (${tokenPhrase(week.total)}, ${sessions(week.sessions)})`,
    })
  );
  if (week.total) {
    wrap.appendChild(
      el("div", { class: "week-figures" }, [
        text(tokenPhrase(week.total)),
        text(sessions(week.sessions)),
        text(hourPhrase(week.hours)),
      ])
    );
  }

  const legend = el("div", { class: "legend" });
  for (const part of shares) {
    const key = el("span", { class: "key" });
    const swatch = document.createElement("i");
    swatch.style.background = `var(--p-${part.purpose})`;
    key.appendChild(swatch);
    key.appendChild(document.createTextNode(purpose(part.purpose)));
    legend.appendChild(key);
  }
  wrap.appendChild(legend);
  return wrap;
}

function observationBlock(data) {
  const row = data.observations[0];
  if (!row) return text(t("menu.noObservation"), "obs-line");
  const wrap = el("div");
  wrap.appendChild(text(observationSentence(row), "obs-sentence"));
  wrap.appendChild(el("div", { class: "coverage-chip", text: observationCaveat(row) }));
  return wrap;
}

/** Batch 7 replaces this with the engine's own answer. Until then the panel says which
 *  batch rather than swallowing the press, and it re-measures, because the note is a
 *  line of content and the window is only as tall as its content. */
function notYet(what) {
  const line = document.getElementById("pop-note");
  if (!line) return;
  line.textContent = `${what}: arrives with the engine wiring, in batch 7.`;
  line.hidden = false;
  refit();
}

/** The button grid: the primary full width, two equal cells under it, and one baseline
 *  carrying the two quiet actions out to the block's own edges. */
function footer() {
  const open = el("button", { class: "btn primary wide", type: "button", text: t("menu.openPrudence") });
  const review = el("button", { class: "btn", type: "button", text: t("menu.reviewNow") });
  const ingest = el("button", { class: "btn", type: "button", text: t("menu.ingestNow") });
  const settings = el("button", { class: "btn plain", type: "button", text: t("menu.settings") });
  const quit = el("button", { class: "btn plain", type: "button", text: t("menu.quit") });

  open.addEventListener("click", () => Bridge.openWindow());
  settings.addEventListener("click", () => Bridge.openWindow());
  review.addEventListener("click", () => notYet(t("menu.reviewNow")));
  ingest.addEventListener("click", () => notYet(t("menu.ingestNow")));
  quit.addEventListener("click", () => Bridge.quit());

  const note = el("div", { class: "coverage-chip", text: "" });
  note.id = "pop-note";
  note.hidden = true;

  return el("div", { class: "pop-foot" }, [
    note,
    open,
    el("div", { class: "buttons-row" }, [review, ingest]),
    el("div", { class: "buttons-row spread" }, [settings, quit]),
  ]);
}

export const page = {
  name: "panel",
  /** @param {HTMLElement} container */
  render(container, { data }) {
    const pop = el("div", { class: "popover" }, [head(data)]);

    const body = el("div", { class: "pop-body" }, [
      block(t("menu.today"), todayBlock(data)),
      block(t("menu.thisWeek"), weekBlock(data)),
      el("div", { class: "pop-sep" }),
      block(t("menu.latestObservation"), observationBlock(data)),
      el("div", { class: "pop-sep" }),
      block(t("menu.lastIngest"), text(stampedAgo(data.status?.last_ingest_at), "obs-line")),
      block(
        t("menu.lastReview"),
        text(data.reviews[0] ? reviewLine(data.reviews[0]) : t("menu.noReview"), "obs-line")
      ),
    ]);

    pop.appendChild(body);
    pop.appendChild(footer());

    container.innerHTML = "";
    container.appendChild(pop);

    /* A popover is as tall as what is in it. The stretch that pins the footer to the
       bottom is lifted for one measurement, or the window's own height is what gets
       measured and the panel can only ever grow. */
    refit = () => {
      if (!Bridge.attached()) return;
      const stretch = pop.style.minHeight;
      pop.style.minHeight = "0";
      const height = Math.ceil(pop.getBoundingClientRect().height);
      pop.style.minHeight = stretch;
      if (height > 0) Bridge.fitPanel(360, height);
      return height;
    };
    refit();

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") Bridge.hidePanel();
    });
  },
};
