/* When a page redraws, and when it must not.
 *
 * The defect these pin is measured and repeatable, not hypothetical: asking the engine
 * whether a review is ready checkpoints the store's write-ahead log, the watcher sees the
 * two files move, it announces, and both pages rebuilt themselves whole to draw figures
 * that had not changed. `src/store/drawn.js` carries the story; this is the rule.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { forget, nowDrawn, worthDrawing } from "../src/store/drawn.js";
import { readPayload } from "../src/store/payload.js";

const here = dirname(fileURLToPath(import.meta.url));

test("a first payload is always worth drawing", () => {
  forget();
  assert.equal(worthDrawing({ revision: 7 }), true);
});

test("the revision already drawn is not worth drawing again", () => {
  forget();
  const payload = { revision: 7 };
  assert.equal(worthDrawing(payload), true);
  nowDrawn(payload);
  // The watcher announced because a reader checkpointed the log. Same figures, same
  // revision: rebuilding the page here is the whole cost this rule removes.
  assert.equal(worthDrawing({ revision: 7 }), false);
});

test("a revision that moved is drawn", () => {
  forget();
  nowDrawn({ revision: 7 });
  assert.equal(worthDrawing({ revision: 8 }), true);
});

test("a setting is forced through, because it changes the page without changing the store", () => {
  forget();
  nowDrawn({ revision: 7 });
  // Choosing a language rewrites every string on the page and moves no figure at all.
  assert.equal(worthDrawing({ revision: 7 }, { force: true }), true);
});

test("a shell that stamps no revision is drawn every time", () => {
  forget();
  // An older shell under a newer page. Drawing too often is the safe end of that.
  const payload = { revision: null };
  assert.equal(worthDrawing(payload), true);
  nowDrawn(payload);
  assert.equal(worthDrawing({ revision: null }), true);
});

test("the payload carries the shell's revision through to the rule", () => {
  forget();
  const payload = readPayload({ revision: 4, usage: [], commits: [] });
  assert.equal(payload.revision, 4);
  assert.equal(worthDrawing(payload), true);
  nowDrawn(payload);
  assert.equal(worthDrawing(readPayload({ revision: 4 })), false);
});

/* The two halves have to stay joined: the rule is only worth anything if the shell really
 * stamps what it hands over, and the shell's own test cannot see this file. */

test("the shell stamps the revision the page compares against", () => {
  const source = readFileSync(join(here, "../src-tauri/src/store.rs"), "utf8");
  assert.match(
    source,
    /object\.insert\("revision"\.into\(\), json!\(revision\)\)/,
    "store.rs no longer puts a revision in the payload, so no page would ever skip a redraw"
  );
  const watcher = readFileSync(join(here, "../src-tauri/src/watcher.rs"), "utf8");
  assert.match(
    watcher,
    /store::invalidate\(\)/,
    "the watcher no longer invalidates the snapshot, so an ingest would not reach the page"
  );
});

test("a setting change is the one redraw that is forced", () => {
  const boot = readFileSync(join(here, "../src/boot.js"), "utf8");
  assert.match(
    boot,
    /draw\(page, root, next, \{ force: true \}\)/,
    "the settings path no longer forces a redraw, so choosing a language would change nothing"
  );
});
