/* The token table, rewritten for this stack.
 *
 * `TokenTests.thePaletteDrawsTheValuesTheDocumentPrints` in the Swift app resolves every
 * colour and compares it with the table `apps/mac/DESIGN.md` prints, so a token table
 * nobody checks cannot drift from what is drawn. `tokens.css` is the source the Swift
 * theme was transcribed from, and in this stack it *is* the theme, so the same test has to
 * exist here: the document below, and the file, read against each other.
 *
 *     pnpm test
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const app = join(here, "..");

const tokensCss = readFileSync(join(app, "src/design/tokens.css"), "utf8");
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

/** DESIGN.md, "The project colour scale". Six, and none of them may be mistaken for a
    purpose or for a verdict. */
const PROJECT_SCALE = [
  ["#3e6ae1", "#6e9bff"],
  ["#a2845e", "#c8a579"],
  ["#b3358c", "#e36fc4"],
  ["#00786f", "#2fb3a6"],
  ["#7a5af8", "#a68bff"],
  // Dark is #B3B3BB and not the #98989D the document prints: that value is exactly
  // `--p-unknown` in dark, and the document's own rule forbids a project colour being a
  // purpose colour. The test below is what found it.
  ["#6e6e73", "#b3b3bb"],
];

test("the project scale is the six the document prints", () => {
  PROJECT_SCALE.forEach(([lightHex, darkHex], index) => {
    assert.equal(light[`--proj-${index}`], lightHex, `light --proj-${index}`);
    assert.equal(dark[`--proj-${index}`], darkHex, `dark --proj-${index}`);
  });
});

/* A project drawn in `development`'s blue would read as a purpose in a window where
   every other chart is coloured by purpose, and one drawn in the outcome pair would read
   as a verdict on the project. */
test("no project colour is a purpose colour or one of the outcome pair", () => {
  for (const [name, table] of [
    ["light", light],
    ["dark", dark],
  ]) {
    const taken = new Set([
      ...PURPOSE.map(([purpose]) => table[`--p-${purpose}`]),
      table["--o-alive"],
      table["--o-rework"],
    ]);
    PROJECT_SCALE.forEach((_, index) => {
      const colour = table[`--proj-${index}`];
      assert.equal(taken.has(colour), false, `${name} --proj-${index} (${colour}) is taken`);
    });
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

/* Design decisions live in the design system, not in any other stylesheet. A stylesheet
   may say where a surface goes and what a control's *token* is; the moment it declares a
   token of its own, two files disagree about what the product's blue is.

   Every stylesheet, found on disk rather than listed here, because the page contract lets
   a new screen add `ui/<screen>.css` without touching a shared file and the rule has to
   reach a file nobody remembered to add to a list. `window.css` is the exception it was
   already: `--paired-label` and friends are geometry the shell computes, and the earlier
   batch registered that in DESIGN.md. */
test("no stylesheet but the design system declares a token", () => {
  const sheets = readdirSync(join(app, "src"), { recursive: true })
    .map(String)
    .filter((name) => name.endsWith(".css"))
    .filter((name) => name !== join("design", "tokens.css"))
    .sort();

  assert.ok(sheets.length >= 6, `found only ${sheets.length} stylesheets`);
  assert.ok(sheets.includes("app.css"), "app.css is not in the list");
  assert.ok(sheets.includes(join("ui", "overview.css")), "the screen sheets are not in the list");

  const offenders = [];
  for (const name of sheets) {
    const text = readFileSync(join(app, "src", name), "utf8");
    for (const match of text.matchAll(/^\s*(--[a-z0-9-]+)\s*:/gim)) {
      if (name === "window.css") continue;
      offenders.push(`${name} declares ${match[1]}`);
    }
  }
  assert.deepEqual(offenders, []);
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
