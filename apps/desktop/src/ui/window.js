/* The window: a sidebar, a head row, and one screen at a time.
 *
 * The screens are placeholders until batches 5 to 8. They are deliberately the shape wry
 * issue 1848 reports the compositor giving up on: a tall scroll container per screen,
 * switched between by the sidebar. `Scripts/stress.py` drives exactly that.
 */

import * as Bridge from "../bridge.js";
import { el } from "../design/dom.js";
import { mark } from "../design/brand.js";
import { PRODUCT_NAME, t } from "../text/strings.js";

/** The four entries, in the order the sidebar shows them and Cmd-1 to Cmd-4 follow.
 *  The keys are what the shell remembers, so they are not display strings. */
export const SECTIONS = /** @type {const} */ ([
  { key: "overview", label: "section.overview" },
  { key: "review", label: "section.review" },
  { key: "observations", label: "section.observations" },
  { key: "settings", label: "section.settings" },
]);

const state = { section: "overview", scroll: /** @type {Record<string, number>} */ ({}) };
const nodes = /** @type {Record<string, any>} */ ({});

function labelOf(key) {
  return (SECTIONS.find((entry) => entry.key === key) ?? SECTIONS[0]).label;
}

function exists(key) {
  return SECTIONS.some((entry) => entry.key === key);
}

/** One placeholder row. Deterministic: two screenshots of the same screen are the same
 *  picture, and nothing animates. */
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
  nodes.screen.classList.remove("is-probe");
  nodes.screen.innerHTML = "";
  for (let i = 0; i < 40; i += 1) nodes.screen.appendChild(placeholderRow(next, i));
  nodes.screen.scrollTop = state.scroll[next] ?? 0;

  if (remember) Bridge.setSection(next);
}

function notYet(what) {
  nodes.note.textContent = `${what}: arrives with the engine wiring, in batch 7.`;
  nodes.note.hidden = false;
}

function sidebar() {
  const aside = el("aside", { class: "sidebar" });
  nodes.buttons = SECTIONS.map((entry, index) => {
    const button = el("button", {
      type: "button",
      text: t(entry.label),
      title: `Cmd-${index + 1}`,
    });
    button.dataset.section = entry.key;
    button.addEventListener("click", () => show(entry.key));
    aside.appendChild(button);
    return button;
  });
  return aside;
}

/** The heading and the screen's controls on one row, fixed above the scroll area, on the
 *  material. The content below it is opaque, which is design rule 1. */
function contentHead() {
  nodes.title = el("h1", { text: "" });
  const titles = el("div", { class: "titles" }, [
    nodes.title,
    el("div", { class: "sub", text: "Placeholder. The screens arrive in batches 5 to 8." }),
  ]);

  const review = el("button", { class: "btn", type: "button", text: t("menu.reviewNow") });
  review.addEventListener("click", () => notYet(t("menu.reviewNow")));

  return el("div", { class: "content-head" }, [titles, el("div", { class: "toolbar" }, [review])]);
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
  render(container, { info }) {
    nodes.screen = el("div", { class: "screen" });
    nodes.note = el("div", { class: "note", text: "" });
    nodes.note.hidden = true;

    const content = el("div", { class: "content" }, [contentHead(), nodes.screen, nodes.note]);
    const split = el("div", { class: "split" }, [sidebar(), content]);

    container.innerHTML = "";
    container.appendChild(el("div", { class: "window" }, [titlebar(), split]));

    keyboard();
    show(info?.section ?? "overview", { remember: false });

    if (info?.harness) /** @type {any} */ (globalThis).Stress = Stress;
  },
};
