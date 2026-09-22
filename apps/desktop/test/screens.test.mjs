/* The route table and the shared components.
 *
 * These three files were written by the agent that merged two screens, not by either
 * screen's author, and a review found they had no test at all. Everything here is a rule
 * the merge introduced: which pickers a screen declares, that the shell asks again on
 * every change of screen, and that the remembered section is restored once.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { installDom } from "./dom.mjs";

installDom();

const { SCREENS, screenExists, screenFor } = await import("../src/ui/screens.js");
// `any`, deliberately, as in the other screen tests: the tree these return is the
// shim's, and asking it for `find` is the whole point of the shim. Typing it as
// `Element` would be a lie.
const { emptyState, panel, statCard } = /** @type {any} */ (
  await import("../src/design/components.js")
);
const { setLang } = await import("../src/text/strings.js");

setLang("en");

/* --- the route table ------------------------------------------------------------------ */

test("every screen declares which pickers it reads, and nothing else", () => {
  for (const screen of SCREENS) {
    assert.ok(Array.isArray(screen.scope), `${screen.key} does not declare its pickers`);
    for (const picker of screen.scope) {
      assert.ok(
        ["project", "range"].includes(picker),
        `${screen.key} asks for a picker that does not exist: ${picker}`
      );
    }
  }
});

/* The reason `scope` stopped being a boolean. A stored review carries its own two
   windows and an observation has no date window at all, so a range control above either
   would change nothing, and a control that changes nothing is worse than no control. */
test("only the Overview reads the range", () => {
  const reads = (key) => screenFor(key).scope;
  assert.deepEqual(reads("overview"), ["project", "range"]);
  assert.deepEqual(reads("review"), ["project"]);
  assert.deepEqual(reads("observations"), ["project"]);
  assert.deepEqual(reads("settings"), []);
});

test("an unknown section falls back to the first screen rather than throwing", () => {
  assert.equal(screenExists("nonesuch"), false);
  assert.equal(screenFor("nonesuch").key, SCREENS[0].key);
  assert.equal(screenFor(undefined).key, SCREENS[0].key);
});

/* Cmd-1 to Cmd-4 are the table's order, so the table's order is the sidebar's order and
   a screen inserted in the middle moves the shortcuts with it. */
test("the table is the order the sidebar and the keyboard use", () => {
  assert.deepEqual(
    SCREENS.map((screen) => screen.key),
    ["overview", "review", "observations", "settings"]
  );
});

test("a screen that gives no subtitle gives none, rather than repeating its own name", () => {
  // The heading already says "Settings"; a subtitle reading "Settings" under it was the
  // first thing this rule was written for.
  assert.equal(screenFor("settings").subtitle, undefined);
});

/* --- the shared components ------------------------------------------------------------ */

test("a card with no note has no note element, and one with a note has it", () => {
  const body = () => emptyState("t", "d");
  const without = panel({ title: "T", body: body() });
  assert.equal(without.find(".panel-note"), null);

  const with_ = panel({ title: "T", note: "why", body: body() });
  assert.equal(with_.find(".panel-note").textContent, "why");
});

test("a method given as a string is folded away, and one given as an element is not", () => {
  const asText = panel({ title: "T", body: emptyState("t"), method: "app_x.y" });
  const details = asText.find(".method");
  assert.ok(details, "a string method is not behind a disclosure");
  assert.equal(details.localName, "details", "the disclosure is not a details element");
  assert.ok(details.textContent.includes("app_x.y"));

  const node = emptyState("the engine's own notes");
  const asNode = panel({ title: "T", body: emptyState("t"), method: node });
  assert.equal(asNode.find(".method"), null, "an element was wrapped");
  assert.ok(asNode.textContent.includes("the engine's own notes"));
});

test("a stat card with no detail still has the element, so a row of them lines up", () => {
  const card = statCard("caption", "42");
  assert.equal(card.find(".value").textContent, "42");
  assert.equal(card.find(".foot").textContent, "");
});

test("an empty state always says why, and never only a title", () => {
  const state = emptyState("No observations yet", "because the floors are not cleared");
  assert.ok(state.textContent.includes("No observations yet"));
  assert.ok(state.textContent.includes("because the floors are not cleared"));
});
