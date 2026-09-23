/* One list of buckets, and it is the engine's.
 *
 * The same guard `purposes.test.mjs` keeps for the purposes: the app draws the four in a
 * fixed order and colours each one, so a bucket the engine grows or renames has to fail
 * here rather than turn up on a screen as tokens in no colour.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { BUCKETS, emptyMix, known } from "../src/design/buckets.js";

const here = dirname(fileURLToPath(import.meta.url));
const ENGINE = join(here, "../../../src/prudence/store/buckets.py");

test("the interface's buckets are the engine's, in the engine's order", () => {
  const source = readFileSync(ENGINE, "utf8");
  const constants = Object.fromEntries(
    [...source.matchAll(/^([A-Z][A-Z_]*)\s*=\s*"([a-z_]+)"$/gm)].map((m) => [m[1], m[2]])
  );
  const block = /^BUCKETS[^=]*=\s*\(([^)]*)\)/m.exec(source);
  assert.ok(block, "could not find BUCKETS in store/buckets.py");
  const engine = block[1]
    .split(",")
    .map((name) => name.trim())
    .filter(Boolean)
    .map((name) => {
      assert.ok(constants[name], `BUCKETS names ${name}, which is not a string constant`);
      return constants[name];
    });
  // Not sorted before comparing: the order is the engine's precedence order and the one
  // `prudence usage` prints, and it is the stacking order here.
  assert.deepEqual([...BUCKETS], engine);
  assert.deepEqual([...BUCKETS], ["change", "run", "read", "talk"]);
});

test("a bucket this build has never heard of is none of the four", () => {
  assert.equal(known("change"), "change");
  assert.equal(known("something_the_engine_grew"), null);
  assert.deepEqual(emptyMix(), { change: 0, run: 0, read: 0, talk: 0 });
});
