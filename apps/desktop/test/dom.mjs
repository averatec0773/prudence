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
    this.id = "";
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

  /**
   * Clearing, and the one place markup is set wholesale.
   *
   * The screens only ever clear. `design/brand.js` sets the mark's paths as a string,
   * because an SVG of eleven paths written through `createElementNS` would be forty lines
   * of builder for artwork that never changes. The shim keeps that string **off**
   * `textContent`: it is not text, and a test asking what a surface says must not be
   * handed a path's `d` attribute.
   */
  set innerHTML(value) {
    this.children = [];
    this.own = "";
    this.markup = String(value);
  }

  get innerHTML() {
    return this.markup ?? "";
  }

  get classList() {
    return {
      add: (name) => {
        this.className = `${this.className} ${name}`.trim();
      },
      remove: (name) => {
        this.className = this.className
          .split(/\s+/)
          .filter((one) => one && one !== name)
          .join(" ");
      },
      contains: (name) => this.className.split(/\s+/).includes(name),
    };
  }

  /* The two geometry questions the panel asks of itself while it measures its own height.
     They answer zero, which is what a node in no document is: `Bridge.attached()` is
     false under the test, so the measurement is never sent anywhere. They are here so the
     panel can be rendered at all, which is what makes its buttons pressable. */
  getBoundingClientRect() {
    return { width: 0, height: 0, top: 0, left: 0, bottom: 0, right: 0 };
  }

  get offsetWidth() {
    return 0;
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
  // The engine's activity strip is put on the page rather than inside a screen, because a
  // run outlives the screen it was started on, so the wiring has a body to append to.
  const body = new Node_("body", null);
  /** @type {any} */ (globalThis).document = {
    createElement: (tag) => new Node_(tag, null),
    createElementNS: (ns, tag) => new Node_(tag, ns),
    createTextNode: (value) => new Text_(value),
    documentElement: new Node_("html", null),
    body,
    // The panel writes its one status line by id, which is how a run started from a
    // button reaches the line under it. Walked rather than registered, because the shim
    // has no notion of a node being in a document.
    getElementById: (id) => {
      for (const node of body.walk()) {
        if (node.id === id) return node;
      }
      return null;
    },
    // Both pages listen for Escape on the document. Nothing in a test presses one, and a
    // missing method would stop the page from rendering at all.
    addEventListener: () => {},
  };
  // The panel listens for the window regaining focus, which is how it knows it was shown.
  // Node has no `addEventListener` on the global object.
  if (typeof (/** @type {any} */ (globalThis).addEventListener) !== "function") {
    /** @type {any} */ (globalThis).addEventListener = () => {};
  }
}
