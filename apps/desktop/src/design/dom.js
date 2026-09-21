/* Building DOM, and nothing else.
 *
 * This was inside the mockups' chart module, which meant every page in the app imported
 * a chart library to create a `<div>`. It is its own module now so that the chart layer
 * can be rewritten, or replaced, without the rest of the app noticing.
 */

const SVG_NS = "http://www.w3.org/2000/svg";

/**
 * @param {string} name
 * @param {Record<string, string | number | null | undefined>} [attrs]
 *   `class` and `text` are shorthands; everything else becomes an attribute.
 * @param {Element[]} [children]
 * @returns {HTMLElement}
 */
export function el(name, attrs, children) {
  const node = document.createElement(name);
  if (attrs) {
    for (const [key, value] of Object.entries(attrs)) {
      if (value === null || value === undefined) continue;
      if (key === "class") node.className = String(value);
      else if (key === "text") node.textContent = String(value);
      else node.setAttribute(key, String(value));
    }
  }
  for (const child of children || []) node.appendChild(child);
  return node;
}

/**
 * @param {string} name
 * @param {Record<string, string | number | null | undefined>} [attrs]
 * @param {Element[]} [children]
 * @returns {SVGElement}
 */
export function svgEl(name, attrs, children) {
  const node = document.createElementNS(SVG_NS, name);
  if (attrs) {
    for (const [key, value] of Object.entries(attrs)) {
      if (value === null || value === undefined) continue;
      node.setAttribute(key, String(value));
    }
  }
  for (const child of children || []) node.appendChild(child);
  return node;
}

/**
 * A chart, with the same numbers in words beside the picture.
 *
 * Every chart in this app is wrapped in one of these. A picture that a screen reader
 * cannot read is a figure the reader cannot check, which is what principle 3 is about,
 * and a `<figcaption>` is also what makes a chart checkable in a screenshot.
 *
 * @param {SVGElement} svg
 * @param {string} caption text carrying the same numbers the picture has
 * @param {{ visuallyHidden?: boolean }} [options]
 * @returns {HTMLElement}
 */
export function figure(svg, caption, options) {
  const fig = el("figure", { class: "chart" });
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", caption);
  fig.appendChild(svg);
  fig.appendChild(el("figcaption", { class: options?.visuallyHidden ? "sr" : "", text: caption }));
  return fig;
}
