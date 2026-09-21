/* The window: a sidebar, a head row, and one screen at a time.
 *
 * The screens are placeholders until batches 5 to 8. They are deliberately the shape wry
 * issue 1848 reports the compositor giving up on: a tall scroll container per screen,
 * switched between by the sidebar. `Scripts/stress.py` drives exactly that.
 */

import * as Bridge from "../bridge.js";
import { el } from "../design/dom.js";
import { icon } from "../design/icons.js";
import { mark } from "../design/brand.js";
import { PRODUCT_NAME, t } from "../text/strings.js";
import { RANGES } from "../store/overview.js";
import { overview } from "./overview.js";

/** The four entries, in the order the sidebar shows them and Cmd-1 to Cmd-4 follow.
 *  The keys are what the shell remembers, so they are not display strings. */
export const SECTIONS = /** @type {const} */ ([
  { key: "overview", label: "section.overview" },
  { key: "review", label: "section.review" },
  { key: "observations", label: "section.observations" },
  { key: "settings", label: "section.settings" },
]);

const state = {
  section: "overview",
  /** null is "all projects". */
  project: /** @type {string|null} */ (null),
  range: "8w",
  /** A week selected in the stacked bars, which filters the three cards. */
  week: /** @type {string|null} */ (null),
  scroll: /** @type {Record<string, number>} */ ({}),
  data: /** @type {any} */ (null),
};
const nodes = /** @type {Record<string, any>} */ ({});

function labelOf(key) {
  return (SECTIONS.find((entry) => entry.key === key) ?? SECTIONS[0]).label;
}

function exists(key) {
  return SECTIONS.some((entry) => entry.key === key);
}

/** One placeholder row, for the screens batches 6a to 8 still owe. Deterministic: two
 *  screenshots of the same screen are the same picture, and nothing animates. */
function placeholderRow(section, index) {
  const share = ((index * 37) % 90) + 8;
  const fill = document.createElement("i");
  fill.style.width = `${share}%`;
  return el("div", { class: "placeholder" }, [
    el("span", { class: "k", text: `${section} placeholder row ${index + 1}` }),
    el("div", { class: "bar" }, [fill]),
    el("span", {
      class: "k",
      text: "Batch 1 draws the shell, not the screen. This row is here to make the container tall.",
    }),
  ]);
}

function show(section, { remember = true } = {}) {
  const next = exists(section) ? section : "overview";
  if (nodes.screen) state.scroll[state.section] = nodes.screen.scrollTop;
  state.section = next;

  for (const button of nodes.buttons) {
    if (button.dataset.section === next) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
  nodes.title.textContent = t(labelOf(next));
  nodes.sub.textContent = subtitleFor(next);
  nodes.scope.hidden = next !== "overview";
  nodes.screen.classList.remove("is-probe");
  nodes.screen.innerHTML = "";

  if (next === "overview") {
    nodes.screen.appendChild(
      overview({
        data: state.data,
        project: state.project,
        range: state.range,
        week: state.week,
        onWeek: (week) => {
          state.week = week;
          redraw();
        },
      })
    );
  } else {
    for (let i = 0; i < 40; i += 1) nodes.screen.appendChild(placeholderRow(next, i));
  }

  nodes.screen.scrollTop = state.scroll[next] ?? 0;
  if (remember) Bridge.setSection(next);
}

/** Redraw the current screen in place, keeping the scroll position. */
function redraw() {
  const where = nodes.screen.scrollTop;
  show(state.section, { remember: false });
  nodes.screen.scrollTop = where;
}

function subtitleFor(section) {
  if (section !== "overview") return "Placeholder. The screens arrive in batches 6a to 8.";
  const scope = state.project ?? t("scope.allProjects");
  const range = RANGES.find((one) => one.key === state.range) ?? RANGES[0];
  return t("scope.subtitle", scope, t(range.label));
}

function notYet(what) {
  nodes.note.textContent = `${what}: arrives with the engine wiring, in batch 7.`;
  nodes.note.hidden = false;
}

function sidebar() {
  const card = el("div", { class: "sidebar-card" });
  nodes.buttons = SECTIONS.map((entry, index) => {
    const button = el("button", { type: "button", title: `Cmd-${index + 1}` });
    button.appendChild(icon(entry.key));
    button.appendChild(el("span", { text: t(entry.label) }));
    button.dataset.section = entry.key;
    button.addEventListener("click", () => show(entry.key));
    card.appendChild(button);
    return button;
  });
  return el("aside", { class: "sidebar" }, [card]);
}

/** A pop-up button: the project picker. Native `<select>` rather than a redrawn menu,
 *  because a redrawn menu is a control the system no longer owns. */
function projectPicker() {
  const select = /** @type {HTMLSelectElement} */ (
    el("select", { class: "select", "aria-label": t("scope.project") })
  );
  select.title = t("scope.project.help");
  const all = el("option", { value: "", text: t("scope.allProjects") });
  select.appendChild(all);
  for (const row of state.data?.projects ?? []) {
    select.appendChild(el("option", { value: String(row.name), text: String(row.name) }));
  }
  select.value = state.project ?? "";
  select.addEventListener("change", () => {
    state.project = select.value || null;
    // A week selected in one project's chart means nothing in another's.
    state.week = null;
    redraw();
  });
  return select;
}

/** A segmented control: the range. */
function rangePicker() {
  const group = el("div", { class: "segmented", role: "radiogroup", "aria-label": t("scope.range") });
  group.title = t("scope.range.help");
  for (const range of RANGES) {
    const button = el("button", { type: "button", role: "radio", text: t(range.label) });
    button.setAttribute("aria-checked", String(range.key === state.range));
    button.addEventListener("click", () => {
      state.range = range.key;
      state.week = null;
      redraw();
    });
    group.appendChild(button);
  }
  return group;
}

/** The heading and the screen's controls on one row, fixed above the scroll area, on the
 *  material. The content below it is opaque, which is design rule 1. */
function contentHead() {
  nodes.title = el("h1", { text: "" });
  nodes.sub = el("div", { class: "sub", text: "" });
  const titles = el("div", { class: "titles" }, [nodes.title, nodes.sub]);

  nodes.scope = el("div", { class: "scope" });

  const review = el("button", { class: "btn", type: "button", text: t("menu.reviewNow") });
  review.addEventListener("click", () => notYet(t("menu.reviewNow")));

  return el("div", { class: "content-head" }, [
    titles,
    el("div", { class: "toolbar" }, [nodes.scope, review]),
  ]);
}

/** The pickers are rebuilt whenever the data behind them changes. */
function fillScope() {
  nodes.scope.innerHTML = "";
  nodes.scope.appendChild(projectPicker());
  nodes.scope.appendChild(rangePicker());
}

function titlebar() {
  const brand = mark(14);
  brand.classList.add("brand-mark");
  return el("div", { class: "titlebar" }, [
    brand,
    el("span", { class: "name", text: PRODUCT_NAME }),
  ]);
}

function keyboard() {
  document.addEventListener("keydown", (event) => {
    if (!event.metaKey) return;
    const index = ["1", "2", "3", "4"].indexOf(event.key);
    if (index >= 0) {
      event.preventDefault();
      show(SECTIONS[index].key);
      return;
    }
    if (event.key === ",") {
      event.preventDefault();
      show("settings");
      return;
    }
    if (event.key.toLowerCase() === "r") {
      event.preventDefault();
      notYet(t("menu.reviewNow"));
    }
  });
}

/** Driven by the shell through `window.eval`, and only in a build with the `harness`
 *  feature. Registered in `DESIGN.md` as the one channel that is not `bridge.js`. */
export const Stress = {
  step(round) {
    show(SECTIONS[round % SECTIONS.length].key, { remember: false });
    const room = nodes.screen.scrollHeight - nodes.screen.clientHeight;
    nodes.screen.scrollTop = room > 0 ? (round * 137) % room : 0;
  },
  finish() {
    show("overview", { remember: false });
    nodes.screen.scrollTop = 0;
  },
  scroll(offset) {
    nodes.screen.scrollTop = Number(offset) || 0;
  },
  probe(colour) {
    nodes.screen.classList.add("is-probe");
    let fill = nodes.screen.querySelector(".probe-fill");
    if (!fill) {
      fill = document.createElement("div");
      fill.className = "probe-fill";
      nodes.screen.appendChild(fill);
    }
    fill.style.background = colour;
  },
};

export const page = {
  name: "main window",
  /** @param {HTMLElement} container */
  render(container, { info, data }) {
    state.data = data;
    nodes.screen = el("div", { class: "screen" });
    nodes.note = el("div", { class: "note", text: "" });
    nodes.note.hidden = true;

    const content = el("div", { class: "content" }, [contentHead(), nodes.screen, nodes.note]);
    const split = el("div", { class: "split" }, [sidebar(), content]);

    container.innerHTML = "";
    container.appendChild(el("div", { class: "window" }, [titlebar(), split]));

    fillScope();
    keyboard();
    show(state.section === "overview" && info?.section ? info.section : state.section, {
      remember: false,
    });

    // A screenshot of a screen taller than the window. Never set in a release build.
    if (info?.scroll) nodes.screen.scrollTop = info.scroll;

    if (info?.harness) /** @type {any} */ (globalThis).Stress = Stress;
  },
};
