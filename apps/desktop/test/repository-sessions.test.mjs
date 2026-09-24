import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { installDom } from "./dom.mjs";

installDom();
import * as Str from "../src/text/strings.js";
import { repositorySessions } from "../src/ui/repository-sessions.js";

const app = join(dirname(fileURLToPath(import.meta.url)), "..");
for (const language of Str.LANGUAGES) {
  Str.load(language, JSON.parse(readFileSync(join(app, `src/text/strings.${language}.json`), "utf8")));
}

const sessions = [
  { session_id: "one", project: "A", started_at: "2026-09-23T12:00:00Z", total_tokens: 123,
    source: "claude_code", source_ids: '["claude"]', source_labels: '["Claude Code"]', models: '["Sonnet"]' },
  { session_id: "two", project: "A", started_at: "2026-09-23T11:00:00Z", total_tokens: 234,
    source: "codex", source_ids: '["codex-extra"]', source_labels: '["Extra Codex"]', models: '["GPT"]' },
  { session_id: "three", project: "B", started_at: "2026-09-23T10:00:00Z", total_tokens: 345,
    source: "codex", source_ids: '["codex"]', source_labels: '["Codex"]', models: '["GPT"]' },
];

test("repository session filters scope rows only and distinguish named homes", () => {
  Str.setLang("en");
  const tree = /** @type {any} */ (repositorySessions(sessions, "A"));
  assert.match(tree.textContent, /These filters change session rows only/);
  assert.equal(tree.findAll(".repository-session").length, 2);
  const source = tree.findAll("select")[0];
  source.value = "codex-extra";
  source.fire("change");
  assert.equal(tree.findAll(".repository-session").length, 1);
  assert.match(tree.textContent, /Extra Codex/);
  assert.doesNotMatch(tree.find(".repository-session").textContent, /Sonnet/);
  const model = tree.findAll("select")[1];
  model.value = "Sonnet";
  model.fire("change");
  assert.equal(tree.findAll(".repository-session").length, 0);
});
