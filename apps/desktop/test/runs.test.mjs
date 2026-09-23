/* The engine's run records on the window: the status row's note about the last ingest,
 * the Engine tab's Recent runs, and the diagnosis.
 *
 * The records are `fixtures/runs.jsonl`, the same file `src-tauri/src/runlog.rs` is tested
 * against: a finished ingest with two warnings and a failed check, an ingest that never
 * finished, a clean review, and half a line still being written. The shell's half (reading
 * the file from its end, the half line, a run completed by a second line) is tested there;
 * what this file guards is what the window says about the records it is handed.
 *
 *     pnpm test
 */

import { test, afterEach } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { installDom } from "./dom.mjs";

installDom();

const here = dirname(fileURLToPath(import.meta.url));
const app = join(here, "..");

const Str = await import("../src/text/strings.js");
const Runs = await import("../src/store/runs.js");
const { ACTIVITY, statusRow, take } = /** @type {any} */ (await import("../src/ui/activity.js"));
const { RUNS, engineRuns, forget } = /** @type {any} */ (await import("../src/ui/engine-runs.js"));

for (const language of Str.LANGUAGES) {
  Str.load(
    language,
    JSON.parse(readFileSync(join(app, `src/text/strings.${language}.json`), "utf8"))
  );
}
Str.setLang("en");

const settled = () => new Promise(setImmediate);

const IDLE = { running: null, outside: false, progress: null, outcome: null };

/** The fixture's whole lines, newest first, which is what the shell hands over. */
const RECORDS = readFileSync(join(app, "fixtures/runs.jsonl"), "utf8")
  .split("\n")
  .filter((line) => line.endsWith("}"))
  .map((line) => JSON.parse(line))
  .reverse();
const [REVIEW, INTERRUPTED, WARNED] = RECORDS;

afterEach(() => {
  if (ACTIVITY.lapse) clearTimeout(ACTIVITY.lapse);
  ACTIVITY.lapse = null;
  ACTIVITY.now = { ...IDLE };
  ACTIVITY.sayUntil = 0;
  ACTIVITY.port = null;
  ACTIVITY.runs = null;
  ACTIVITY.mounts.clear();
  RUNS.port = null;
  forget();
  Str.setLang("en");
});

/** A toolbar port whose run log is `records`, counting how often it was read. */
function activityPort(records) {
  const asked = { runs: 0, activity: null };
  ACTIVITY.port = {
    read: () => Promise.resolve(IDLE),
    onActivity: (handler) => {
      asked.activity = handler;
      return Promise.resolve(() => {});
    },
    onProgress: () => Promise.resolve(() => {}),
    run: () => Promise.resolve({ ok: true }),
    runs: () => {
      asked.runs += 1;
      return Promise.resolve({ runs: records, unreadable: 0 });
    },
  };
  return asked;
}

const TODAY = { status: { last_ingest_at: new Date(Date.now() - 13 * 3600 * 1000).toISOString() } };

/* --- what a record says ------------------------------------------------------------------ */

test("the fixture is the three records the shell reads from it, newest first", () => {
  assert.deepEqual(
    RECORDS.map((run) => run.run_id),
    ["r3", "r2", "r1"]
  );
});

test("a failed check is counted once, from the checks, and a check_failed warning is not", () => {
  // Two unreadable lines and one unknown record type, and one failed check.
  assert.equal(Runs.warningCount(WARNED), 4);
  const restated = {
    ...WARNED,
    warnings: [...WARNED.warnings, { kind: "check_failed", count: 1, sample: { name: "x" } }],
  };
  assert.equal(Runs.warningCount(restated), 4);
  assert.equal(Runs.warningCount(REVIEW), 0);
  // A check with no verdict is not one this app may call failed.
  assert.equal(Runs.failedChecks({ checks: [{ name: "x", numbers: {} }] }).length, 0);
});

test("a record reads its command past the executable, its files, and its length", () => {
  assert.equal(Runs.commandName(WARNED), "ingest");
  assert.equal(Runs.commandName({ command: ["/Users/x/.local/bin/prudence", "review"] }), "review");
  assert.equal(Runs.commandLine(WARNED), "ingest --json --progress");
  assert.deepEqual(Runs.files(WARNED), { parsed: 14, skipped: 480 });
  assert.equal(Runs.files(REVIEW), null);
  assert.equal(Runs.seconds(WARNED), 192);
  assert.equal(Runs.seconds(INTERRUPTED), null);
});

test("the status row's note is about the newest ingest, and never while a run goes", () => {
  assert.deepEqual(Runs.statusNote(RECORDS, false), { kind: "interrupted" });
  assert.equal(Runs.statusNote(RECORDS, true), null, "a run going now is not an interruption");
  assert.deepEqual(Runs.statusNote([REVIEW, WARNED], false), { kind: "warnings", count: 4 });
  assert.equal(Runs.statusNote([REVIEW], false), null, "a review is not the last ingest");
  const clean = { ...WARNED, warnings: [], checks: [] };
  assert.equal(Runs.statusNote([clean, INTERRUPTED], false), null, "only the newest ingest");
  assert.equal(Runs.statusNote([], false), null, "an engine with no run log says nothing");
});

/* --- the status row ---------------------------------------------------------------------- */

/* Under the age, not after it: the row has 148 points of text, and the age alone takes most
   of them. Found in the first screenshot, where "Last ing..." was all that was left. */
test("idle after an ingest with warnings, the row says how many under the age, in both languages", async () => {
  const lines = {};
  for (const language of Str.LANGUAGES) {
    Str.setLang(language);
    activityPort([REVIEW, WARNED]);
    const opened = [];
    const row = statusRow(TODAY, () => opened.push("engine"));
    await settled();
    const stacked = row.find(".status-lines");
    assert.ok(stacked, `${language}: no note`);
    lines[language] = stacked.children.map((node) => node.textContent);
    assert.equal(stacked.children[0].className, "run-outcome is-idle", "the age is not first");
    const note = row.find(".status-note");
    note.fire("click");
    assert.deepEqual(opened, ["engine"], "the note does not open the Engine tab");
  }
  assert.deepEqual(lines.en, ["Last ingest 13h ago", "4 warnings"]);
  assert.equal(lines["zh-Hans"][1], "4 条警告");
});

test("idle after an interrupted ingest, the row says so in place of the age", async () => {
  for (const language of Str.LANGUAGES) {
    Str.setLang(language);
    activityPort(RECORDS);
    const row = statusRow(TODAY, () => {});
    await settled();
    assert.equal(row.textContent, Str.t("activity.interrupted"));
    assert.equal(row.find(".run-outcome"), null, "the age dates an ingest that never finished");
  }
  assert.equal(Str.tIn("zh-Hans", "activity.interrupted"), "上次采集被中断");
});

test("a clean last ingest and an engine with no run log both leave the row as it was", async () => {
  for (const records of [[{ ...WARNED, warnings: [], checks: [] }], []]) {
    activityPort(records);
    const row = statusRow(TODAY, () => {});
    await settled();
    assert.equal(row.find(".status-note"), null);
    assert.equal(row.children.length, 1);
  }
});

test("while a run goes the row shows the run, and its end reads the records again", async () => {
  const asked = activityPort(RECORDS);
  const row = statusRow(TODAY, () => {});
  await settled();
  const before = asked.runs;
  take({ ...IDLE, running: "ingest" });
  assert.equal(row.find(".status-note"), null, "an open record is the run in hand");
  take({ ...IDLE });
  await settled();
  assert.equal(asked.runs, before + 1, "a run's end did not read its record");
});

/* --- Recent runs --------------------------------------------------------------------- */

function runsPort(answer, diagnose) {
  const asked = { reveal: [], diagnose: 0 };
  RUNS.port = {
    runs: () => Promise.resolve(answer),
    diagnose: () => {
      asked.diagnose += 1;
      return typeof diagnose === "function" ? diagnose() : Promise.resolve(diagnose);
    },
    reveal: (name) => {
      asked.reveal.push(name);
      return Promise.resolve();
    },
  };
  return asked;
}

const INFO = { info: { logs: "/tmp/copy/logs" } };

test("Recent runs lists each run with its length or interruption, files, warnings and checks", async () => {
  runsPort({ runs: RECORDS, unreadable: 0 });
  const [runs] = engineRuns(INFO);
  await settled();
  assert.equal(runs.hidden, false);
  const rows = runs.findAll(".run-entry");
  assert.equal(rows.length, 3);
  const took = rows.map((row) => row.find(".run-took").textContent);
  assert.deepEqual(took, ["2.0 s", Str.t("runs.interrupted"), "3 min 12 s"]);
  assert.equal(rows[0].find(".run-command").textContent, "review --json --no-explain");
  assert.deepEqual(
    rows[2].find(".run-facts").children.map((node) => node.textContent),
    ["14 files parsed, 480 skipped", "4 warnings", "1 failed check"]
  );
  assert.equal(rows[0].find(".run-facts"), null, "a clean review has no counts to say");
});

test("a run opens onto its warnings, its failed checks and its error as the engine wrote them", async () => {
  const failed = {
    ...INTERRUPTED,
    run_id: "r9",
    ended_at: "2026-09-23T07:10:04+00:00",
    error: { type: "DatabaseError", message: "database disk image is malformed" },
  };
  runsPort({ runs: [failed, WARNED], unreadable: 0 });
  const [runs] = engineRuns(INFO);
  await settled();
  const [errored, warned] = runs.findAll(".run-entry");
  const text = warned.find(".run-recorded").textContent;
  for (const expected of [
    "unreadable_line",
    '{"file":"session-a.jsonl","line":41,"bytes":812}',
    "unknown_record_type",
    "token_totals_agree",
    '{"usage":18234000,"response":18233112,"bucket_view":18234000}',
  ]) {
    assert.ok(text.includes(expected), `missing ${expected}`);
  }
  assert.equal(text.includes("every_response_has_a_turn"), false, "a passing check is listed");
  assert.equal(
    errored.find(".run-error").textContent,
    "DatabaseError: database disk image is malformed"
  );
});

test("a record still open is running when it is the newest and a run goes, and never otherwise", async () => {
  ACTIVITY.now = { ...IDLE, running: "ingest" };
  runsPort({ runs: [INTERRUPTED, INTERRUPTED], unreadable: 0 });
  const [runs] = engineRuns(INFO);
  await settled();
  assert.deepEqual(
    runs.findAll(".run-took").map((node) => node.textContent),
    [Str.t("runs.running"), Str.t("runs.interrupted")]
  );
});

test("no run log draws no card and says nothing; unreadable lines are counted", async () => {
  runsPort({ runs: [], unreadable: 0 });
  const [empty] = engineRuns(INFO);
  await settled();
  assert.equal(empty.hidden, true);
  assert.equal(empty.textContent, "");

  runsPort({ runs: [REVIEW], unreadable: 2 });
  const [counted] = engineRuns(INFO);
  await settled();
  assert.ok(counted.textContent.includes(Str.t("runs.unreadable", "2")));
});

test("an open row stays open when the screen is rebuilt", async () => {
  runsPort({ runs: RECORDS, unreadable: 0 });
  const [first] = engineRuns(INFO);
  await settled();
  const row = first.findAll(".run-entry")[2];
  row.open = true;
  row.fire("toggle");
  const [again] = engineRuns(INFO);
  await settled();
  assert.deepEqual(
    again.findAll(".run-entry").map((node) => Boolean(node.open)),
    [false, false, true]
  );
});

/* --- the diagnosis ------------------------------------------------------------------- */

function press(tree, label) {
  const button = tree.findAll("button").find((node) => node.textContent === label);
  assert.ok(button, `no ${label}`);
  button.fire("click");
}

test("Diagnose runs once, shows the folder it wrote, and reveals it by name", async () => {
  const asked = runsPort({ runs: [], unreadable: 0 }, { path: "/tmp/copy/diagnose/20260923T090000" });
  const [, card] = engineRuns(INFO);
  assert.ok(card.textContent.includes(Str.t("diagnose.logs", "/tmp/copy/logs")));
  press(card, Str.t("diagnose.action"));
  assert.ok(card.textContent.includes(Str.t("diagnose.running")));
  press(card, Str.t("diagnose.action"));
  await settled();
  assert.equal(asked.diagnose, 1, "a second press started a second diagnosis");
  assert.ok(card.textContent.includes("/tmp/copy/diagnose/20260923T090000"));
  press(card, Str.t("diagnose.reveal"));
  press(card, Str.t("diagnose.revealLogs"));
  assert.deepEqual(asked.reveal, ["diagnose", "logs"]);
});

/* `prudence diagnose` reads the store, the store's files move, and the screen is rebuilt
   while it runs. The answer has to land in the card on screen, not the one it started in. */
test("a diagnosis that ends after the screen was rebuilt is shown in the new card", async () => {
  let finish = (_value) => {};
  runsPort({ runs: [], unreadable: 0 }, () => new Promise((resolve) => (finish = resolve)));
  const [, first] = engineRuns(INFO);
  press(first, Str.t("diagnose.action"));
  const [, rebuilt] = engineRuns(INFO);
  assert.ok(rebuilt.textContent.includes(Str.t("diagnose.running")));
  finish({ path: "/tmp/copy/diagnose/20260923T090001" });
  await settled();
  assert.ok(rebuilt.textContent.includes("/tmp/copy/diagnose/20260923T090001"));
});

test("a diagnosis that failed says so, in the engine's own words, and an old engine is named", async () => {
  runsPort(
    { runs: [], unreadable: 0 },
    { errorKind: "failed", error: "Error: No such command 'diagnose'." }
  );
  const [, card] = engineRuns(INFO);
  press(card, Str.t("diagnose.action"));
  await settled();
  const said = card.find(".diagnose-said").textContent;
  assert.ok(said.includes(Str.t("diagnose.failed")));
  assert.ok(said.includes(Str.t("engine.error.failed")));
  assert.ok(said.includes("No such command 'diagnose'."));

  forget();
  runsPort({ runs: [], unreadable: 0 }, { errorKind: "noBundle" });
  const [, older] = engineRuns(INFO);
  press(older, Str.t("diagnose.action"));
  await settled();
  assert.ok(older.textContent.includes(Str.t("diagnose.noBundle")));

  forget();
  runsPort({ runs: [], unreadable: 0 }, () => Promise.reject(new Error("the shell went away")));
  const [, gone] = engineRuns(INFO);
  press(gone, Str.t("diagnose.action"));
  await settled();
  assert.ok(gone.textContent.includes("the shell went away"), "a rejection was swallowed");
});

test("with no shell behind the page there is nothing to list and nothing to run", () => {
  RUNS.port = null;
  assert.deepEqual(engineRuns(INFO), []);
});
