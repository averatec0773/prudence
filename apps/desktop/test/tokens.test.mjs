/* The token table, rewritten for this stack.
 *
 * `TokenTests.thePaletteDrawsTheValuesTheDocumentPrints` in the Swift app resolves every
 * colour and compares it with the table `apps/mac/DESIGN.md` prints, so a token table
 * nobody checks cannot drift from what is drawn. `tokens.css` is the source the Swift
 * theme was transcribed from, and in this stack it *is* the theme, so the same test has to
 * exist here: the document below, and the file, read against each other.
 *
 *     node --test test/
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const app = join(here, "..");

const tokensCss = readFileSync(join(app, "src/vendor/tokens.css"), "utf8");
const appCss = readFileSync(join(app, "src/app.css"), "utf8");

/** Custom properties declared in one selector's block, by exact selector text. */
function declarations(css, selector) {
  const at = css.indexOf(`\n${selector} {`);
  assert.notEqual(at, -1, `no block for ${selector}`);
  const open = css.indexOf("{", at);
  const close = css.indexOf("\n}", open);
  const body = css.slice(open + 1, close);
  const out = {};
  for (const line of body.split("\n")) {
    const match = /^\s*(--[a-z0-9-]+)\s*:\s*([^;]+);/i.exec(line);
    if (match) out[match[1]] = match[2].trim();
  }
  return out;
}

const light = declarations(tokensCss, ":root");
const dark = declarations(tokensCss, ':root[data-theme="dark"]');

/** DESIGN.md, "Purpose palette". The order is the fixed stacking and legend order. */
const PURPOSE = [
  ["development", "#007aff", "#0a84ff"],
  ["research", "#30b0c7", "#40c8e0"],
  ["debugging", "#ff9500", "#ff9f0a"],
  ["conversation", "#af52de", "#bf5af2"],
  ["mixed", "#5856d6", "#7d7aff"],
  ["unknown", "#8e8e93", "#98989d"],
];

/** DESIGN.md, "Outcome colours" and "Surfaces and ink". */
const SURFACES = [
  ["--canvas", "#f2f2f4", "#1c1c1e"],
  ["--surface", "#ffffff", "#2c2c2e"],
  ["--surface-2", "#f7f7f9", "#242426"],
  ["--surface-sunken", "#ebebef", "#171719"],
  ["--sidebar", "#f6f6f8", "#232325"],
  ["--text", "#1c1c1e", "#f2f2f7"],
  ["--text-2", "#636366", "#aeaeb2"],
  ["--text-3", "#8e8e93", "#8e8e93"],
  ["--accent", "#007aff", "#0a84ff"],
  ["--o-alive", "#0a7d45", "#3ac07a"],
  ["--o-rework", "#8a5a00", "#e0a33a"],
];

test("the palette draws the values the document prints", () => {
  for (const [purpose, lightHex, darkHex] of PURPOSE) {
    assert.equal(light[`--p-${purpose}`], lightHex, `light --p-${purpose}`);
    assert.equal(dark[`--p-${purpose}`], darkHex, `dark --p-${purpose}`);
  }
  for (const [token, lightHex, darkHex] of SURFACES) {
    assert.equal(light[token], lightHex, `light ${token}`);
    assert.equal(dark[token], darkHex, `dark ${token}`);
  }
});

test("every purpose has a colour in both appearances, and no two share one", () => {
  const seen = new Map();
  for (const [purpose] of PURPOSE) {
    for (const [name, table] of [
      ["light", light],
      ["dark", dark],
    ]) {
      const value = table[`--p-${purpose}`];
      assert.ok(value, `${name} --p-${purpose} is missing`);
      const key = `${name}:${value}`;
      assert.equal(seen.has(key), false, `${name} ${value} is used by two purposes`);
      seen.set(key, purpose);
    }
  }
});

test("no outcome colour is a purpose colour", () => {
  for (const table of [light, dark]) {
    const purposes = PURPOSE.map(([purpose]) => table[`--p-${purpose}`]);
    for (const outcome of ["--o-alive", "--o-rework"]) {
      assert.equal(
        purposes.includes(table[outcome]),
        false,
        `${outcome} is also a purpose colour`
      );
    }
  }
});

/* Design decisions live in the design system, not in the app's own stylesheet. `app.css`
   may say where a surface goes and what a control's *token* is; the moment it declares a
   token of its own, two files disagree about what the product's blue is. */
test("app.css declares no token of its own", () => {
  const declared = [...appCss.matchAll(/^\s*(--[a-z0-9-]+)\s*:/gim)].map((m) => m[1]);
  assert.deepEqual(declared, [], `app.css declares ${declared.join(", ")}`);
});

/* Colour never means good or bad, and the quiet actions are quiet. Batch 3 settled the
   plain button as `Ink.secondary` with the accent only under the pointer; `tokens.css`
   still carries the mockups' earlier reading, so the override has to be here and has to
   stay here. */
test("the plain button is quiet ink, and the accent only under the pointer", () => {
  assert.match(appCss, /\.btn\.plain\s*\{[^}]*color:\s*var\(--text-2\)/);
  assert.match(appCss, /\.btn\.plain:hover\s*\{[^}]*color:\s*var\(--accent\)/);
});

/* Glass is the control and navigation layer, never the content layer. In this app the
   surface material is native, so `app.css` takes the popover's own tint away; it must not
   take it away from anything that is content. */
test("app.css clears the material only from the popover surface", () => {
  const cleared = [...appCss.matchAll(/^:root\[data-material="glass"\]\s+([^{]+)\{/gm)].map(
    (m) => m[1].trim()
  );
  assert.deepEqual(cleared.sort(), ["body", ".popover"].sort());
});
