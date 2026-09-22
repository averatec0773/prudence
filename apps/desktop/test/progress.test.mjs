/* The progress bar, drawn from the engine's own events.
 *
 * The events are **the recording**, not a stream written for this test:
 * `fixtures/ingest-progress.jsonl` is the standard error of one real
 * `prudence ingest --json --progress` against a copy of the founder's store. A stream
 * written by hand would agree with whatever the component expects, which is the thing
 * under test. `src-tauri/src/engine.rs` reads the same file, so the two halves of this
 * feature are asserted against one source.
 *
 * What is guarded here: that the label is the step said in the reader's language, that the
 * counter is the engine's two figures and its unit, that the bar's width is the ratio of
 * those two figures and nothing else, and that a step with no total yet draws an empty
 * track rather than a full one.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { installDom } from "./dom.mjs";

installDom();

const here = dirname(fileURLToPath(import.meta.url));
const app = join(here, "..");

import * as Str from "../src/text/strings.js";
import { count } from "../src/text/fmt.js";
const { runProgress } = /** @type {any} */ (await import("../src/design/components.js"));

for (const language of Str.LANGUAGES) {
  Str.load(
    language,
    JSON.parse(readFileSync(join(app, `src/text/strings.${language}.json`), "utf8"))
  );
}
Str.setLang("en");

/** The recorded run, as the page receives it: the shell sends camelCase. */
const RECORDED = readFileSync(join(app, "fixtures/ingest-progress.jsonl"), "utf8")
  .split("\n")
  .filter(Boolean)
  .map((line) => JSON.parse(line))
  .map((event) => ({
    step: event.step,
    stepIndex: event.step_index,
    steps: event.steps,
    current: event.current,
    total: event.total,
    unit: event.unit,
    label: event.label,
  }));

function drawn(event) {
  const node = runProgress(event);
  return {
    node,
    label: node.find(".progress-label").textContent,
    count: node.find(".progress-count").textContent,
    width: node.find(".progress-fill").style.width,
    step: node.find(".progress-step")?.textContent ?? "",
    track: node.find(".progress-track"),
  };
}

test("the bar draws the step, the two figures and the fraction of the one over the other", () => {
  // The fourth event of the recording: `archive`, part way through, with a real ratio.
  const event = RECORDED.find((one) => one.step === "archive" && one.current > 0);
  assert.ok(event, "the recording has no archive event with a count on it");

  const shown = drawn(event);
  assert.equal(shown.label, Str.t("engine.step.archive"));
  assert.equal(
    shown.count,
    Str.t("engine.progress.count", "1,421", "6,670", Str.t("engine.unit.files"))
  );
  assert.equal(shown.width, `${(event.current / event.total) * 100}%`);
  assert.equal(shown.step, Str.t("engine.progress.step", "2", "11"));

  // The same numbers for anything reading the page rather than looking at it.
  assert.equal(shown.track.getAttribute("aria-valuenow"), String(event.current));
  assert.equal(shown.track.getAttribute("aria-valuemax"), String(event.total));
});

test("every event of a recorded run draws, and never past its own track", () => {
  assert.equal(RECORDED.length, 116, "the recording is not the one committed");
  for (const event of RECORDED) {
    const shown = drawn(event);
    const width = Number(shown.width.replace("%", ""));
    assert.ok(width >= 0 && width <= 100, `${event.step} drew ${shown.width}`);
    assert.ok(shown.label.trim().length > 0, `${event.step} drew no label`);
    // Both figures, as the reader's locale groups them, over the engine's own unit.
    assert.equal(
      shown.count,
      Str.t(
        "engine.progress.count",
        count(event.current),
        count(event.total),
        Str.t(`engine.unit.${event.unit}`)
      ),
      `${event.step} drew ${shown.count}`
    );
    assert.equal(shown.step, Str.t("engine.progress.step", String(event.stepIndex), "11"));
  }
});

/* The first event of a step is the one that says it has started. It must not read as
   finished, and where the engine has not counted anything yet it must not read as full. */
test("a step that has counted nothing yet draws an empty track", () => {
  const first = RECORDED.find((one) => one.current === 0);
  assert.ok(first, "the recording has no first-of-step event");
  assert.equal(drawn(first).width, "0%");

  // And a step with no total at all draws nothing rather than a full bar: `total` is the
  // denominator, and a bar drawn without one would be a figure the engine never gave.
  const unknown = drawn({ step: "parse", stepIndex: 3, steps: 11, current: 0, total: 0, unit: "sessions", label: "Parsing" });
  assert.equal(unknown.width, "0%");
  assert.equal(unknown.count, "", "a counter was printed with no total behind it");
});

/* A step this build has never heard of is the engine's own English, which is at least
   true. Never the key, and never blank. */
test("a step with no name of its own falls back to the engine's own label", () => {
  const shown = drawn({
    step: "something_new",
    stepIndex: 12,
    steps: 12,
    current: 1,
    total: 2,
    unit: "widgets",
    label: "Doing something new",
  });
  assert.equal(shown.label, "Doing something new");
  // The unit, too: the engine's own word rather than a key nobody can read.
  assert.ok(shown.count.includes("widgets"), shown.count);
  assert.equal(shown.count.includes("engine.unit"), false, shown.count);
});

test("the bar draws in Chinese with no English left on it", () => {
  Str.setLang("zh-Hans");
  try {
    const event = RECORDED.find((one) => one.step === "parse" && one.current > 0);
    const shown = drawn(event);
    assert.equal(shown.label, Str.tIn("zh-Hans", "engine.step.parse"));
    assert.equal(shown.label.includes(Str.tIn("en", "engine.step.parse")), false);
    assert.ok(shown.count.includes(Str.tIn("zh-Hans", "engine.unit.sessions")), shown.count);
    // The engine's English label is not on the bar when the step has a name of its own.
    assert.equal(shown.node.textContent.includes(event.label), false, shown.node.textContent);
  } finally {
    Str.setLang("en");
  }
});
