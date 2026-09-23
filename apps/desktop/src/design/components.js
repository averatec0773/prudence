/* The pieces more than one screen is built from.
 *
 * The page contract says a rule two screens want **moves** here rather than being copied.
 * These three arrived by that route: `statCard` and `emptyState` were byte-identical in
 * the Overview, Review and Observations screens, and `panel` differed only in how it took
 * its disclosure. Two copies of a card is two places for a card to change.
 *
 * Nothing here knows what any screen contains. A component takes what it draws and
 * returns one element.
 */

import { el } from "./dom.js";
import { count } from "../text/fmt.js";
import { t } from "../text/strings.js";

/** A figure with its caption above and its qualification below. */
export function statCard(caption, value, detail) {
  return el("div", { class: "card stat" }, [
    el("div", { class: "label", text: caption }),
    el("div", { class: "value", text: value }),
    el("div", { class: "foot", text: detail ?? "" }),
  ]);
}

/**
 * Something folded away, with the line that says what is in it.
 *
 * The card below builds one out of its `method` string. The Overview builds its own,
 * because its two full tables belong in the same drawer as the method and the summary has
 * to say so: a table that repeats a chart row for row is the same promise as the method
 * ("check this figure yourself") and being open by default is what made that screen
 * unreadable. Two hundred rows of it at 365 days.
 *
 * `deferred` is built the first time the drawer is opened and never again. A closed
 * disclosure draws nothing, but its content is still nodes to build, to lay out and to
 * keep: at 365 days the Overview's two tables were 2,158 of the screen's nodes, on a page
 * whose reader had asked for a chart. Nothing is lost by waiting, because nothing the
 * reader can see depends on it.
 *
 * @param {{ summary: string, body: Element[], deferred?: () => Element[] }} options
 * @returns {HTMLElement}
 */
export function disclosure({ summary, body, deferred }) {
  const how = el("details", { class: "method" });
  how.appendChild(el("summary", { text: summary }));
  for (const node of body) how.appendChild(node);
  if (deferred) {
    let built = false;
    how.addEventListener("toggle", () => {
      if (built) return;
      built = true;
      for (const node of deferred()) how.appendChild(node);
    });
  }
  return how;
}

/**
 * A card: a title, one sentence of plain method for a reader, the body, and the view and
 * column names folded away behind a disclosure.
 *
 * The split is principle 3 read properly. The method has to be stated, but stating it as
 * `alive_30d / measured_30d ... from app_outcomes_by_week` states it to whoever wrote the
 * query. The sentence says what is counted and over what; the disclosure says where to go
 * and check.
 *
 * `method` is either a string, which is put in the disclosure, or an element, which is
 * appended as it is: a review's own notes are several paragraphs the engine wrote and
 * arrive already built.
 *
 * @param {{ title: string, note?: string, body: Element,
 *           extra?: Element|null, method?: string|Element|null }} options
 */
export function panel({ title, note, body, extra, method }) {
  const head = el("div", { class: "panel-head" }, [el("h2", { text: title })]);
  if (extra) head.appendChild(extra);

  const card = el("div", { class: "card panel" }, [head]);
  if (note) card.appendChild(el("p", { class: "panel-note", text: note }));
  card.appendChild(body);

  if (typeof method === "string" && method) {
    card.appendChild(
      disclosure({ summary: t("chart.method"), body: [el("p", { text: method })] })
    );
  } else if (method) {
    card.appendChild(/** @type {Element} */ (method));
  }
  return card;
}

/* --- what a run is doing ---------------------------------------------------------------
 *
 * One component, drawn on the panel, in the window's toolbar and status row, and in the
 * Repositories screen's batch bar: the same run can be watched from any of them, and two
 * bars would be two things to keep in step. It is fluid, so each place gets the width it
 * has with no second rule anywhere, and `is-compact` drops the step line where a place has
 * one line of room.
 *
 * **Determinate per step, and never smoother than the engine is.** The engine walks eleven
 * steps and counts within each one; the bar fills for the step it is on and starts again
 * at the next. Nothing is animated between events, because an ingest's `parse` step counts
 * one session at a time and a bar gliding on its own between two of them would be the app
 * inventing progress it has not been told about. A step that reports no total yet draws an
 * empty track: that is what "it has started and has nothing to count yet" looks like.
 *
 * Colour is the accent and means nothing but "this is the thing moving": a progress bar is
 * not a verdict, so there is no second colour for a slow step or a long one.
 */

/**
 * The step's own name, in the reader's language.
 *
 * The eleven steps are a closed list the engine walks in order, so each one has a key.
 * A step this build has never heard of falls back to the engine's own `label`, which is
 * English and is at least true; the same rule the Review screen's headers keep.
 *
 * @param {{ step?: string, label?: string }} progress
 */
function stepName(progress) {
  const key = `engine.step.${String(progress.step ?? "")}`;
  const said = t(key);
  return said === key ? String(progress.label ?? "") : said;
}

/** The unit the engine counted in, in the reader's language, or the engine's own word. */
function unitName(unit) {
  const key = `engine.unit.${String(unit ?? "")}`;
  const said = t(key);
  return said === key ? String(unit ?? "") : said;
}

/**
 * One progress event, drawn.
 *
 * @param {{ step?: string, stepIndex?: number, steps?: number, current?: number,
 *           total?: number, unit?: string, label?: string }} progress
 * @returns {HTMLElement}
 */
export function runProgress(progress) {
  const current = Number(progress.current ?? 0);
  const total = Number(progress.total ?? 0);
  const fraction = total > 0 ? Math.min(Math.max(current / total, 0), 1) : 0;

  const name = stepName(progress);
  const counted = total > 0 ? t("engine.progress.count", count(current), count(total), unitName(progress.unit)) : "";

  const fill = el("span", { class: "progress-fill" });
  fill.style.width = `${fraction * 100}%`;

  const track = el("div", { class: "progress-track", role: "progressbar" }, [fill]);
  track.setAttribute("aria-valuemin", "0");
  track.setAttribute("aria-valuemax", String(total));
  track.setAttribute("aria-valuenow", String(current));
  track.setAttribute("aria-label", name);

  const node = el("div", { class: "progress" }, [
    el("div", { class: "progress-head" }, [
      el("span", { class: "progress-label", text: name }),
      el("span", { class: "progress-count", text: counted }),
    ]),
    track,
  ]);

  const steps = Number(progress.steps ?? 0);
  const index = Number(progress.stepIndex ?? 0);
  if (steps > 0 && index > 0) {
    node.appendChild(
      el("div", {
        class: "progress-step",
        text: t("engine.progress.step", count(index), count(steps)),
      })
    );
  }
  return node;
}

/**
 * One row of choices, one of them ticked.
 *
 * The Settings screen's General and Model tabs set the app's own settings with it, and
 * the Repositories screen puts one in a table cell for each repository's level. Whatever
 * holds it, the ticked choice is the one the shell answered with.
 *
 * `disabled` is for a control whose answer is still on its way: a second click before the
 * first one has landed is how a control ends up disagreeing with what it controls.
 *
 * A choice may carry a `title`: the Repositories table shows "Meta" where the General tab
 * would have room for "Metadata only", and a label shortened to fit a column still has to
 * say what it means to a pointer and to a screen reader.
 *
 * @param {{ label: string, choices: {value: any, label: string, title?: string}[], chosen: any,
 *           onChoose: (value: any) => void, disabled?: boolean }} options
 * @returns {HTMLElement}
 */
export function segmented({ label, choices, chosen, onChoose, disabled }) {
  const group = el("div", { class: "segmented", role: "radiogroup", "aria-label": label });
  for (const choice of choices) {
    const button = el("button", { type: "button", role: "radio", text: choice.label });
    button.setAttribute("aria-checked", String(choice.value === chosen));
    if (choice.title) {
      button.setAttribute("title", choice.title);
      button.setAttribute("aria-label", choice.title);
    }
    if (disabled) /** @type {any} */ (button).disabled = true;
    button.addEventListener("click", () => onChoose(choice.value));
    group.appendChild(button);
  }
  return group;
}

/** A sub-heading inside a card, for a block with its own caption and its own note: the
 *  fact versions on the Engine tab, the platform on About, and the two groups of the
 *  Repositories screen. */
export function subhead(title, note) {
  return el("div", { class: "subhead" }, [el("h3", { text: title }), el("p", { text: note })]);
}

/** Nothing to show, and why. Never a blank area: an empty screen is a question. */
export function emptyState(title, detail) {
  return el("div", { class: "empty" }, [
    el("div", { class: "empty-title", text: title }),
    el("div", { class: "empty-detail", text: detail ?? "" }),
  ]);
}
