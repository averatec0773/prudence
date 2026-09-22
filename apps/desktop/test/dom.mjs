/* Enough of a DOM for a screen to be rendered under `node --test`.
 *
 * The frontend has no build step and no browser in the test run, so a screen module can
 * only be exercised if `document.createElement` answers. This is not a DOM: it is the
 * handful of operations `design/dom.js` and the screens actually use, which is why it
 * is forty lines rather than a dependency. A screen that reaches for something not here
 * fails loudly, which is the right answer.
 *
 * What a test may ask of a node: `tagName`, `className`, `textContent`, `attributes`,
 * `children`, `style`, and `find`/`findAll` by a class or tag name.
 */

class Node_ {
  constructor(tag, namespace) {
    this.tagName = String(tag).toUpperCase();
    this.localName = String(tag);
    this.namespace = namespace ?? null;
    this.children = [];
    this.attributes = {};
    this.style = {};
    this.dataset = {};
    this.className = "";
    this.listeners = {};
    this.hidden = false;
    this.value = "";
    this.title = "";
    this.own = "";
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }

  getAttribute(name) {
    return Object.hasOwn(this.attributes, name) ? this.attributes[name] : null;
  }

  appendChild(child) {
    this.children.push(child);
    return child;
  }

  addEventListener(name, handler) {
    (this.listeners[name] ??= []).push(handler);
  }

  /** Fire every handler registered for one event, as a click or a change would. */
  fire(name) {
    for (const handler of this.listeners[name] ?? []) handler({ type: name });
  }

  get textContent() {
    if (this.children.length === 0) return this.own;
    return this.own + this.children.map((child) => child.textContent).join("");
  }

  set textContent(value) {
    this.own = String(value);
    this.children = [];
  }

  /** The only bulk mutation the screens use, and only to clear. */
  set innerHTML(value) {
    if (value !== "") throw new Error("the shim only clears with innerHTML");
    this.children = [];
    this.own = "";
  }

  get classList() {
    return {
      add: (name) => {
        this.className = `${this.className} ${name}`.trim();
      },
      contains: (name) => this.className.split(/\s+/).includes(name),
    };
  }

  /** Depth first, this node included. */
  *walk() {
    yield this;
    for (const child of this.children) yield* child.walk();
  }

  /** Every node with this class, or with this tag when the selector has no dot. */
  findAll(selector) {
    const wanted = selector.startsWith(".") ? selector.slice(1) : null;
    const out = [];
    for (const node of this.walk()) {
      if (node === this) continue;
      const hit = wanted
        ? node.className.split(/\s+/).includes(wanted)
        : node.localName === selector;
      if (hit) out.push(node);
    }
    return out;
  }

  find(selector) {
    return this.findAll(selector)[0] ?? null;
  }
}

class Text_ {
  constructor(value) {
    this.own = String(value);
    this.children = [];
    this.className = "";
    this.localName = "#text";
  }

  get textContent() {
    return this.own;
  }

  *walk() {
    yield this;
  }
}

/** Install the shim on `globalThis`. Idempotent, so every test file may call it. */
export function installDom() {
  /** @type {any} */ (globalThis).document = {
    createElement: (tag) => new Node_(tag, null),
    createElementNS: (ns, tag) => new Node_(tag, ns),
    createTextNode: (value) => new Text_(value),
    documentElement: new Node_("html", null),
    // The engine's activity strip is put on the page rather than inside a screen,
    // because a run outlives the screen it was started on, so the wiring has a body to
    // append to. Nothing else in the frontend touches it.
    body: new Node_("body", null),
  };
}
