/* One list of purposes, and it is the engine's.
 *
 * The list existed in four places with no tie between them, and the three that rendered
 * it disagreed about what to do with a label they did not recognise. This reads the
 * engine's own source and asserts the interface agrees with it.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { PURPOSES, emptyBuckets, known } from "../src/design/purposes.js";

const here = dirname(fileURLToPath(import.meta.url));
const ENGINE = join(here, "../../../src/prudence/facts/purpose.py");

test("the interface's purposes are the engine's purposes", () => {
  const source = readFileSync(ENGINE, "utf8");
  // `PURPOSES = (CONVERSATION, RESEARCH, ...)`: a tuple of constants, so the constants
  // have to be resolved before the list means anything.
  const constants = Object.fromEntries(
    [...source.matchAll(/^([A-Z][A-Z_]*)\s*=\s*"([a-z_]+)"$/gm)].map((m) => [m[1], m[2]])
  );
  const block = /^PURPOSES[^=]*=\s*\(([^)]*)\)/m.exec(source);
  assert.ok(block, "could not find PURPOSES in facts/purpose.py");
  const engine = block[1]
    .split(",")
    .map((name) => name.trim())
    .filter(Boolean)
    .map((name) => {
      assert.ok(constants[name], `PURPOSES names ${name}, which is not a string constant`);
      return constants[name];
    });
  assert.deepEqual([...PURPOSES].sort(), engine.slice().sort(), "the two lists differ");
});

/* The order is fixed and never sorted by size: a chart whose colours move is a chart two
   screenshots a week apart cannot be compared across. */
test("the order is the one every surface draws in", () => {
  assert.deepEqual(
    [...PURPOSES],
    ["development", "research", "debugging", "conversation", "mixed", "unknown"]
  );
});

/* One answer to the question the three call sites used to answer three ways. A token
   that went somewhere has to stay in the total, or the shares stop summing to a hundred
   and nothing says why. */
test("a purpose this build has never heard of folds into other, and is never dropped", () => {
  assert.equal(known("something_the_engine_grew"), "unknown");
  assert.equal(known("development"), "development");
  const buckets = emptyBuckets();
  buckets[known("something_the_engine_grew")] += 500;
  const total = Object.values(buckets).reduce((a, b) => a + b, 0);
  assert.equal(total, 500, "the tokens are still in the total");
});
