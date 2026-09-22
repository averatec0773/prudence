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
    const how = el("details", { class: "method" });
    how.appendChild(el("summary", { text: t("chart.method") }));
    how.appendChild(el("p", { text: method }));
    card.appendChild(how);
  } else if (method) {
    card.appendChild(/** @type {Element} */ (method));
  }
  return card;
}

/** Nothing to show, and why. Never a blank area: an empty screen is a question. */
export function emptyState(title, detail) {
  return el("div", { class: "empty" }, [
    el("div", { class: "empty-title", text: title }),
    el("div", { class: "empty-detail", text: detail ?? "" }),
  ]);
}
