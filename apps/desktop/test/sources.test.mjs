import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { installDom } from "./dom.mjs";
installDom();

import * as Str from "../src/text/strings.js";
import { SOURCES, sources } from "../src/ui/sources.js";
import { SOURCE_ANSWER, REPOSITORY_SCAN } from "../src/store/asked.js";

const app = join(dirname(fileURLToPath(import.meta.url)), "..");
for (const language of Str.LANGUAGES) {
  Str.load(language, JSON.parse(readFileSync(join(app, `src/text/strings.${language}.json`), "utf8")));
}
const settled = () => new Promise(setImmediate);

test("source capture changes redraw from the engine answer and refresh repository scan", async () => {
  Str.setLang("en");
  SOURCE_ANSWER.forget();
  REPOSITORY_SCAN.forget();
  const data = { status: { last_ingest_at: "2026-09-23" }, reviews: [] };
  let rows = [
    { id: "claude", kind: "claude_code", label: "Claude Code", home: "/tmp/claude", enabled: true, exists: true },
    { id: "codex", kind: "codex", label: "Codex", home: "/tmp/codex", enabled: false, exists: true },
  ];
  const changed = [];
  SOURCES.port = {
    read: async () => rows,
    add: async () => ({ sources: rows, repositories: [] }),
    set: async (id, enabled) => {
      changed.push([id, enabled]);
      rows = rows.map((row) => row.id === id ? { ...row, enabled } : row);
      return { sources: rows, repositories: [{ repoKey: "repo", sources: ["codex"] }] };
    },
  };
  const tree = /** @type {any} */ (sources({ data }));
  await settled();
  assert.match(tree.textContent, /Claude Code/);
  assert.match(tree.textContent, /Codex/);
  const codex = tree.findAll(".source-row")[1];
  const button = codex.findAll("button").find((one) => one.textContent === "Resume capture");
  assert.ok(button);
  button.fire("click");
  await settled();
  assert.deepEqual(changed, [["codex", true]]);
  assert.match(tree.findAll(".source-row")[1].textContent, /Pause capture/);
  assert.deepEqual(await REPOSITORY_SCAN.ask(data, async () => []), [{ repoKey: "repo", sources: ["codex"] }]);
});

test("a typed additional home requires name and path before it reaches the shell", async () => {
  Str.setLang("en");
  SOURCE_ANSWER.forget();
  let added = null;
  SOURCES.port = {
    read: async () => [],
    add: async (...args) => { added = args; return { sources: [], repositories: [] }; },
    set: async () => ({ sources: [], repositories: [] }),
  };
  const tree = /** @type {any} */ (sources({ data: { status: {}, reviews: [] } }));
  await settled();
  tree.find(".source-add-toggle").fire("click");
  const form = tree.find(".source-add-form");
  form.find("button").fire("click");
  assert.equal(added, null);
  const inputs = form.findAll("input");
  inputs[0].value = "Another Codex";
  inputs[1].value = "/tmp/another-codex";
  form.find("button").fire("click");
  await settled();
  assert.deepEqual(added, ["codex", "Another Codex", "/tmp/another-codex"]);
});
