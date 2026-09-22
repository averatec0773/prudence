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
import { SCREENS, screenExists, screenFor } from "./screens.js";

/** The four entries, in the order the sidebar shows them and Cmd-1 to Cmd-4 follow.
 *  The keys are what the shell remembers, so they are not display strings. */
/** The sidebar's rows, and the keyboard's order, are the route table's order. */
export const SECTIONS = SCREENS;

const state = {
  section: "overview",
  /** `shell_info`, handed to every screen: the platform, the language, the material. */
  info: /** @type {any} */ (null),
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
  return screenExists(key);
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
  // A screen that does not read the pickers must not show them: a control that changes
  // nothing is worse than no control. The route table says which do.
  // Rebuilt on every change of screen, not only on a redraw: which pickers exist is a
  // property of the screen, so moving between screens has to re-ask. Without this the
  // range picker stayed on screens that declare they do not read it.
  fillScope();
  nodes.scope.hidden = screenFor(next).scope.length === 0;
  nodes.screen.classList.remove("is-probe");
  nodes.screen.innerHTML = "";

  // Every screen is drawn the same way: the route table names the function, and the
  // function is handed everything it needs. Nothing here knows what any screen contains.
  nodes.screen.appendChild(screenFor(next).render(screenState()));

  nodes.screen.scrollTop = state.scroll[next] ?? 0;
  if (remember) Bridge.setSection(next);
}

/** Redraw the current screen in place, keeping the scroll position. */
function redraw() {
  const where = nodes.screen.scrollTop;
  // `show` rebuilds the pickers, which is what carries the state just changed: without
  // that the range buttons kept whatever `aria-checked` they were built with at start-up.
  show(state.section, { remember: false });
  nodes.screen.scrollTop = where;
}

/** Everything a screen is handed. One place builds it, so the route table's `render` and
 *  `subtitle` cannot be given different views of the same moment. */
function screenState() {
  return {
    data: state.data,
    info: state.info,
    project: state.project,
    range: state.range,
    week: state.week,
    onWeek: (week) => {
      state.week = week;
      redraw();
    },
    redraw,
  };
}

/** The screen's own line, or nothing. Not the screen's name: the heading already says it. */
function subtitleFor(section) {
  const screen = screenFor(section);
  return screen.subtitle ? screen.subtitle(screenState()) : "";
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

  // No Review now button here. The Review screen owns one, wired to its own seam, and
  // two buttons with one label that do different things is worse than one in one place.
  return el("div", { class: "content-head" }, [
    titles,
    el("div", { class: "toolbar" }, [nodes.scope]),
  ]);
}

/** The pickers are rebuilt whenever the data behind them changes. */
function fillScope() {
  const wanted = screenFor(state.section).scope;
  nodes.scope.innerHTML = "";
  if (wanted.includes("project")) nodes.scope.appendChild(projectPicker());
  if (wanted.includes("range")) nodes.scope.appendChild(rangePicker());
}

function titlebar() {
  const brand = mark(14);
  brand.classList.add("brand-mark");
  return el("div", { class: "titlebar" }, [
    brand,
    el("span", { class: "name", text: PRODUCT_NAME }),
  ]);
}

/** `render` runs again on every store change, and `container.innerHTML = ""` clears the
 *  DOM, not listeners on `document`. Once is once. */
let listening = false;
let firstDraw = true;

function keyboard() {
  if (listening) return;
  listening = true;
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
      // The action lives on the Review screen, so the shortcut goes there rather than
      // keeping a second copy of it here.
      show("review");
    }
  });
}

/** Driven by the shell through `window.eval`, and only in a build with the `harness`
 *  feature. Registered in `DESIGN.md` as the one channel that is not `bridge.js`. */
/**
 * Press a button once it exists, rather than once a timer says it might.
 *
 * The engine block draws itself twice: a waiting state, then the answer with its buttons,
 * once the shell has asked the executable for its version. A press fired at first draw
 * finds nothing. This waits for the button itself, which is the actual condition, and
 * gives up with a line in the log rather than silently.
 *
 * **Not `requestAnimationFrame`.** The first version polled frames, and against a window
 * that was not frontmost it never fired at all and logged nothing either: WebKit throttles
 * animation frames for an occluded window and can stop delivering them altogether. A
 * screenshot or a scripted run is exactly the case where the window may not be in front,
 * so the deadline is wall-clock and the poll is a timer.
 *
 * Harness only: `info.press` is `None` in a release build.
 */
const PRESS_DEADLINE = 30_000;

function pressWhenItExists(label, startedAt = Date.now()) {
  const waited = Date.now() - startedAt;
  if (Stress.press(label)) {
    Bridge.log(`[harness] press ${JSON.stringify(label)}: pressed after ${waited} ms`);
    return;
  }
  if (waited >= PRESS_DEADLINE) {
    Bridge.log(`[harness] press ${JSON.stringify(label)}: no such button after ${waited} ms`);
    return;
  }
  setTimeout(() => pressWhenItExists(label, startedAt), 50);
}

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
  /**
   * Press a button by the text on it, and say whether one was found.
   *
   * The engine's actions are the one path a script could not reach: the run happens in
   * the shell, the report happens on the page, and the only thing that connects them is
   * a click. Everything else about the wiring is covered by a Rust test that really
   * spawns the engine and by the bridge test that pins the command names, but nobody had
   * pressed the button. Harness only, like the rest of this object.
   */
  press(label) {
    const wanted = String(label);
    for (const button of document.querySelectorAll("button")) {
      if ((button.textContent ?? "").trim() === wanted) {
        button.click();
        return true;
      }
    }
    return false;
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
    state.info = info;
    nodes.screen = el("div", { class: "screen" });
    // No shell-level note any more. It existed for `notYet`, and each screen now owns
    // whatever it has to say about an action it cannot perform yet.
    const content = el("div", { class: "content" }, [contentHead(), nodes.screen]);
    const split = el("div", { class: "split" }, [sidebar(), content]);

    container.innerHTML = "";
    container.appendChild(el("div", { class: "window" }, [titlebar(), split]));

    fillScope();
    keyboard();
    // Only on the first draw. `render` runs again on every store change with the same
    // `info` captured at boot, so this line used to throw the reader back to the section
    // the *previous* launch ended on, every time an ingest landed.
    const restore = firstDraw && info?.section ? info.section : state.section;
    firstDraw = false;
    show(restore, { remember: false });

    // A screenshot of a screen taller than the window. Never set in a release build.
    if (info?.scroll) nodes.screen.scrollTop = info.scroll;

    // A button a script asked to have pressed, once everything is drawn. Never set in a
    // release build. The result is logged, so a script that asked for a button that is
    // not there learns that rather than waiting for something that will not happen.
    if (info?.press) pressWhenItExists(String(info.press));

    if (info?.harness) /** @type {any} */ (globalThis).Stress = Stress;
  },
};
