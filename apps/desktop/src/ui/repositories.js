/* Repositories: which ones the engine found on this machine, which of them it records, and
 * what the store holds about each.
 *
 * It answers the founder's own question about this app: "why are only three repositories
 * recorded?" Because recording is opt-in per repository, which is the first thing the
 * screen says and the reason the list is split in two. It was a tab of Settings until the
 * founder moved it into the sidebar (2026-09-23): a repository is something the reader
 * looks at, not only something they configure.
 *
 * ## Where each figure comes from
 *
 * The list is `prudence init --scan --json`, as the engine printed it: the path, the
 * sessions found, the first and the last of them, whether it is recorded and at what
 * level. The two figures the scan does not carry are the store's, through
 * `store/repositories.js`: tokens by what each reply did, and what was still there thirty
 * days on, each over all time and each keyed by the scan's own `repoKey`. A repository
 * that is not recorded has neither, and says so with a dash rather than a zero.
 *
 * ## The filter
 *
 * A recorded repository the store has sessions from is the same thing the project picker
 * offers, so clicking its row sets the window's one project filter to it, the one every
 * screen reads, and clicking it again clears it. The row stays quietly marked while it is
 * the filter, and a line above the list says what every screen is now showing.
 *
 * ## The page contract, and the one thing kept between renders
 *
 * It is handed everything, returns one element and computes no figure. A running batch is
 * kept in `BATCH` below rather than in a render's closure, for the reason given there.
 */

import { miniStack } from "../design/charts.js";
import { BUCKETS, bucketColour } from "../design/buckets.js";
import { disclosure, emptyState, runProgress, segmented, subhead } from "../design/components.js";
import { el } from "../design/dom.js";
import { REPOSITORY_SCAN } from "../store/asked.js";
import { aliveOf, projectOf, scanCounts, tokensOf } from "../store/repositories.js";
import {
  bucket,
  count,
  isoDay,
  lines,
  list,
  percent,
  sessions as sessionPhrase,
  tokenPhrase,
} from "../text/fmt.js";
import { t } from "../text/strings.js";

/**
 * What the screen asks the shell: the scan, and a change to one repository's level.
 * `ui/wiring.js` fills it in; a test sets a fake one.
 *
 * @typedef {{
 *   scan: () => Promise<any>,
 *   level: (key: string, level: string) => Promise<any>,
 * }} RepositoriesPort
 *
 * @type {{ port: RepositoriesPort | null }}
 */
export const REPOSITORIES = { port: null };

/** Off, and the engine's two levels. The words that reach the command line are checked
 *  again in `src-tauri/src/repositories.rs`, so nothing this file sends can be an
 *  argument on its own.
 *
 *  The labels are the **short** ones, and the reason is the column: three segments in a
 *  hundred and seventy points have room for a word each, and "Metadata only" against
 *  "仅元数据" is what wrapped a segment onto two lines in the founder's screenshot. The
 *  full name is on the segment's `title`, and the recorded group's note spells both levels
 *  out in a sentence. */
function levelChoices() {
  return [
    { value: "off", label: t("settings.choice.off") },
    {
      value: "metadata-only",
      label: t("repositories.level.metadataOnly.short"),
      title: t("repositories.level.metadataOnly"),
    },
    { value: "full", label: t("repositories.level.full") },
  ];
}

/** What the control is set to: the engine's level, or off where it records nothing. */
function levelOf(row) {
  return row.enabled && row.level ? String(row.level) : "off";
}

/**
 * Which agents' sessions this repository holds.
 *
 * Recording is per repository and covers **every** AI coding agent that worked in it; a
 * session carries its own source. The scan does not print that list yet, so this answers
 * with the one source Prudence reads today. It is one function rather than a constant at
 * the call site so that the engine's future field drops in without a change to the page:
 * `repositories.rs` already decodes `sources`, and the day it is written the rows show it.
 *
 * @param {any} row one row of the engine's scan
 * @returns {string[]} source keys, never empty
 */
export function sourcesOf(row) {
  const said = Array.isArray(row?.sources) ? row.sources.filter(Boolean).map(String) : [];
  return said.length ? said : ["claude-code"];
}

/**
 * An agent's name, as it writes it.
 *
 * Not catalogue keys, for the reason `LANGUAGE_NAMES` in `ui/settings.js` is not one: a
 * product's name is the same in both languages, and a key whose two values are identical
 * is what `strings.test.mjs` refuses. A key Prudence has not learned yet is drawn as the
 * engine wrote it rather than hidden.
 */
const SOURCE_NAMES = { "claude-code": "Claude Code" };

function sourceNames(row) {
  return list(sourcesOf(row).map((key) => SOURCE_NAMES[key] ?? key));
}

/** The last path component, which is what a person calls the project. */
function basename(path) {
  const parts = String(path).split("/").filter(Boolean);
  return parts.length ? parts[parts.length - 1] : String(path);
}

/** How many path components under the name are enough to tell two checkouts apart. Two,
 *  measured rather than guessed: three read `…/CODING/github/b…` in the founder's own
 *  layout, which spends the column on the part every row shares and cuts the part that
 *  identifies the row. */
const PATH_PARTS = 2;

/**
 * The end of a path, which is the part that identifies it.
 *
 * A path cut by CSS from the left reads `/Users/averatec…`, which is the part every path
 * on the machine has in common and says nothing; the last two components are what two
 * checkouts of one repository differ in. The whole path is on the element's `title`.
 */
function shortPath(path) {
  const parts = String(path).split("/").filter(Boolean);
  if (parts.length <= PATH_PARTS) return String(path);
  return `…/${parts.slice(-PATH_PARTS).join("/")}`;
}

/**
 * A box that is ticked or not, with its name only to a screen reader.
 *
 * The list's own control, and the only one in the app: a column header of "Select" over a
 * column of boxes would be a word the reader does not need, and the row the box belongs to
 * is what says what is being selected.
 *
 * @param {{ label: string, checked: boolean, onChange: (checked: boolean) => void,
 *           disabled?: boolean }} options
 */
function tick({ label, checked, onChange, disabled }) {
  const box = el("input", { class: "tick", type: "checkbox", "aria-label": label });
  /** @type {any} */ (box).checked = checked;
  if (disabled) /** @type {any} */ (box).disabled = true;
  // The state at build time, inverted: the row is redrawn on every change, so what the
  // box holds after the event is not what the next draw reads from.
  box.addEventListener("change", () => onChange(!checked));
  return box;
}

/**
 * Two lines in one cell, each on one line: a figure and what qualifies it.
 *
 * @param {string} top
 * @param {string} under
 */
function stacked(top, under) {
  return [el("div", { text: top }), el("div", { class: "repo-sub", text: under })];
}

/**
 * Tokens by what each reply did, as one bar in the fixed bucket order, or a dash where the
 * store has none for this repository. The shares and the total are in the caption, which
 * is on the pointer and read by a screen reader.
 */
function tokensCell(data, repoKey) {
  const tokens = tokensOf(data, repoKey);
  if (!tokens.total) return [el("div", { class: "repo-sub", text: t("common.dash") })];
  const caption = t(
    "repositories.tokens.caption",
    tokenPhrase(tokens.total),
    list(tokens.shares.map((part) => `${bucket(part.bucket)} ${percent(part.share)}`))
  );
  const bar = miniStack({
    parts: BUCKETS.map((key) => ({ value: tokens.byBucket[key], colour: bucketColour(key) })),
    // The whole, so tokens in a bucket this build does not know stay as unfilled track
    // rather than being shared out among the four.
    total: tokens.total,
    height: 6,
    caption,
  });
  bar.title = caption;
  return [bar];
}

/** What was still there thirty days on, over the lines it is measured over. */
function aliveCell(data, repoKey) {
  const alive = aliveOf(data, repoKey);
  if (!alive) return [el("div", { class: "repo-sub", text: t("common.dash") })];
  return stacked(percent(alive.share), t("repositories.alive.over", lines(alive.measured)));
}

/**
 * One group of the list: a heading, its note, and a row per repository.
 *
 * **The columns are declared, not discovered.** An automatic table sizes every column from
 * its contents, and in Chinese the header "会话数" and a day written the reader's way both
 * break between any two characters, so the layout wrapped the count and both dates. The
 * `<colgroup>` below plus `table-layout: fixed` in `repositories.css` is the fix: every
 * column but the name's has a width, and every cell is one line or two stacked lines that
 * do not wrap. Only the path may lose characters, to an ellipsis, with the whole of it on
 * the element's `title`.
 *
 * @param {{ title: string, note: string, rows: any[], data: any, filter: string|null,
 *           change: (row: any, level: string) => void, busy: boolean, picked: Set<string>,
 *           pick: (key: string, on: boolean) => void,
 *           pickAll: (keys: string[], on: boolean) => void,
 *           filterBy: (project: string) => void }} block
 */
function repositoryTable({ title, note, rows, data, filter, change, busy, picked, pick, pickAll, filterBy }) {
  const keys = rows.map((row) => String(row.repoKey));
  const all = keys.length > 0 && keys.every((key) => picked.has(key));

  const columns = el("colgroup", {}, [
    el("col", { class: "c-pick" }),
    el("col", { class: "c-name" }),
    el("col", { class: "c-sessions" }),
    el("col", { class: "c-seen" }),
    el("col", { class: "c-tokens" }),
    el("col", { class: "c-alive" }),
    el("col", { class: "c-level" }),
  ]);

  const aliveHead = el("th", { class: "n nowrap", text: t("repositories.column.alive") });
  aliveHead.title = t("repositories.alive.help");
  const head = el("thead", {}, [
    el("tr", {}, [
      el("th", { class: "repo-pick" }, [
        tick({
          label: t("repositories.selectAll"),
          checked: all,
          onChange: (on) => pickAll(keys, on),
          disabled: busy,
        }),
      ]),
      el("th", { text: t("scope.project") }),
      el("th", { class: "n nowrap", text: t("repositories.column.sessions") }),
      el("th", { class: "nowrap", text: t("repositories.column.seen") }),
      el("th", { class: "nowrap", text: t("repositories.column.tokens") }),
      aliveHead,
      el("th", { class: "nowrap repo-level", text: t("repositories.column.level") }),
    ]),
  ]);

  const body = el("tbody");
  for (const row of rows) {
    const key = String(row.repoKey);
    const shortName = basename(row.path);
    // The name the rest of the window knows this repository by, if the store has any
    // session from it. Only such a row can be the filter: the picker offers nothing else.
    const project = row.enabled ? projectOf(data, key) : null;
    const chosen = project !== null && project === filter;

    const name = project
      ? el("button", {
          class: "repo-name is-filter",
          type: "button",
          text: shortName,
          title: t(chosen ? "repositories.filter.clear" : "repositories.filter.set"),
        })
      : el("div", { class: "repo-name", text: shortName, title: String(row.path) });
    if (project) {
      name.setAttribute("aria-pressed", String(chosen));
      name.addEventListener("click", () => filterBy(project));
    }
    // The path under the name, as the line that says which one this is: two checkouts of
    // the same repository have the same last component.
    const where = el("div", { class: "repo-path", text: shortPath(row.path), title: String(row.path) });
    const cell = el("td", { class: "repo-what" }, [name, where]);
    // A repository that is on record and no longer on disk is still on record, and a
    // reader looking for it has to be told which of the two states it is in.
    if (!row.exists) {
      cell.appendChild(el("div", { class: "repo-gone", text: t("repositories.gone") }));
    }

    const sources = sourceNames(row);
    const sessionsCell = el("td", { class: "n nowrap" }, stacked(count(Number(row.sessions ?? 0)), sources));
    sessionsCell.title = sources;

    const line = el("tr", { class: chosen ? "is-filtered" : "" }, [
      el("td", { class: "repo-pick" }, [
        tick({
          label: t("repositories.select", shortName),
          checked: picked.has(key),
          onChange: (on) => pick(key, on),
          disabled: busy,
        }),
      ]),
      cell,
      sessionsCell,
      el("td", { class: "nowrap repo-when" }, stacked(isoDay(row.firstAt), isoDay(row.lastAt))),
      el("td", { class: "nowrap repo-tokens" }, tokensCell(data, key)),
      el("td", { class: "n nowrap" }, aliveCell(data, key)),
      el("td", { class: "nowrap repo-level" }, [
        segmented({
          label: t("repositories.column.level"),
          choices: levelChoices(),
          chosen: levelOf(row),
          onChoose: (value) => change(row, value),
          disabled: busy,
        }),
      ]),
    ]);
    // Anywhere on the row is the name's own click, except the two controls that are
    // something else: the box and the level. The name is the button, so the keyboard
    // reaches the same thing the pointer does.
    if (project) {
      line.classList.add("is-pickable");
      line.addEventListener("click", (event) => {
        const target = /** @type {any} */ (event)?.target;
        if (target?.closest?.("button, input")) return;
        filterBy(project);
      });
    }
    body.appendChild(line);
  }

  return el("div", { class: "repo-group" }, [
    subhead(title, note),
    el("table", { class: "data repo-table" }, [columns, head, body]),
  ]);
}

/**
 * What to do with the rows that are ticked.
 *
 * At the foot of the card and only while something is selected: it is a control, so it
 * takes the frost where the platform has one, and it says how many rows it is about
 * before it offers to change them. While a batch runs it says which repository is being
 * changed and how far through the list that is, in the same bar `runProgress` draws for
 * an ingest: a determinate bar per repository, because the engine is run once per
 * repository and a bar that said nothing would look stuck on a list of twenty.
 *
 * `progress`'s row is **reserved, never revealed**: it is in the bar whether or not a
 * batch is running, empty when it is not, at the height its answer needs, so starting a
 * batch changes no height.
 *
 * @param {{ chosen: number, busy: boolean,
 *           progress: {name: string|null, current: number, total: number}|null,
 *           failure: {name: string, message: string}|null,
 *           onLevel: (level: string) => void }} options
 */
function batchBar({ chosen, busy, progress, failure, onLevel }) {
  const bar = el("div", { class: "repo-actions" });
  const line = el("div", { class: "repo-actions-line" }, [
    el("div", {
      class: "repo-actions-count",
      // While a batch runs, what it is doing is in the reserved row below instead: a
      // second sentence here would say the same thing twice.
      text: progress ? "" : t("repositories.batch.selected", count(chosen)),
    }),
  ]);

  const set = el("div", { class: "repo-actions-set" }, [
    el("span", { class: "repo-actions-label", text: t("repositories.batch.label") }),
  ]);
  for (const choice of levelChoices()) {
    const button = el("button", {
      class: "btn",
      type: "button",
      text: choice.label,
      title: choice.title ?? choice.label,
    });
    if (busy) /** @type {any} */ (button).disabled = true;
    button.addEventListener("click", () => onLevel(String(choice.value)));
    set.appendChild(button);
  }
  line.appendChild(set);
  bar.appendChild(line);

  const slot = el("div", { class: "repo-batch-progress" });
  if (progress) {
    slot.appendChild(
      runProgress({
        // No `step`: the batch is not one of the engine's steps, so `runProgress` falls
        // back to this label as it is, which is the one thing to say here, the
        // repository's own name.
        label: progress.name ?? "",
        current: progress.current,
        total: progress.total,
        unit: "repositories",
      })
    );
  }
  bar.appendChild(slot);

  // The engine's own words for what it refused, under the app's sentence for what that
  // left behind. English on a Chinese interface, like every other message from something
  // that is not this app.
  if (failure) {
    bar.appendChild(
      el("div", { class: "notes repo-notes" }, [
        el("div", { text: t("repositories.batch.failed", failure.name) }),
        el("div", { text: failure.message }),
      ])
    );
  }
  return bar;
}

/**
 * A batch level-change in flight, kept outside any screen's own tree.
 *
 * A switch to another screen throws the whole tree away and rebuilds it from nothing
 * (`window.js`: `nodes.screen.innerHTML = ""`), which used to throw this away too: the
 * loop kept running, because nothing had cancelled the promises it was awaiting, but it
 * drew into detached nodes nobody could see, and the screen it came back to built a fresh
 * closure that had never heard of it, with no bar and no disabled controls. The founder's
 * instruction is that a batch **finishes** rather than stops, so what it needs in order to
 * keep saying what it is doing lives here instead, the way `store/asked.js` keeps the
 * engine's own answers. The screen reattaches to this on every render rather than starting
 * a batch of its own, and `startBatch` itself refuses to run two at once.
 *
 * Exported so `test/repositories.test.mjs` can reset it between tests, the way it resets
 * `REPOSITORIES.port` and the memo in `store/asked.js`.
 */
export const BATCH = {
  running: false,
  keys: /** @type {string[]} */ ([]),
  index: 0,
  name: /** @type {string | null} */ (null),
  scan: /** @type {any[] | null} */ (null),
  failure: /** @type {{ name: string, message: string } | null} */ (null),
  // Whichever render is currently mounted, if any: called after every step this batch
  // takes, so a mounted screen redraws from what just happened rather than from a poll.
  onChange: /** @type {(() => void) | null} */ (null),
};

/**
 * The same command, once per ticked repository, in the order the list is in.
 *
 * Sequential and not in parallel: `prudence init --enable` writes `config.toml`, and two
 * of them at once is two processes writing one file.
 *
 * **Each call is already the engine's whole answer, so there is no second read to make.**
 * `engine_repository_level` runs the change and then runs `init --scan --json` itself
 * (`src-tauri/src/lib.rs`), so a row is drawn from its answer the moment it lands, and a
 * row flips to its new level as soon as its own change has.
 *
 * A refusal stops the run where it is. `BATCH.scan` is the last answer that landed, so the
 * repositories before the refusal are already drawn as changed and stay that way.
 *
 * @param {RepositoriesPort} port
 * @param {any} data
 * @param {any[]} scan the list this batch started from, for the first step's own label
 * @param {string[]} keys
 * @param {string} level
 */
async function startBatch(port, data, scan, keys, level) {
  if (BATCH.running) return;
  BATCH.running = true;
  BATCH.keys = keys;
  BATCH.scan = scan;
  BATCH.failure = null;

  for (const [index, key] of keys.entries()) {
    BATCH.index = index;
    // Counted, and named, before the call rather than after it, so the bar and its label
    // name the repository being changed while it is being changed.
    const row = (BATCH.scan ?? []).find((one) => String(one.repoKey) === key);
    BATCH.name = row ? basename(row.path) : key;
    BATCH.onChange?.();
    try {
      const next = await port.level(key, String(level));
      if (Array.isArray(next)) {
        BATCH.scan = next;
        // `prudence init --enable` writes `config.toml`, which no store stamp sees, so
        // the engine's fresh answer is handed to the memo rather than left to expire.
        REPOSITORY_SCAN.keep(data, next);
      }
      BATCH.onChange?.();
    } catch (error) {
      BATCH.failure = {
        name: row ? basename(row.path) : key,
        message: String(/** @type {any} */ (error)?.message ?? error),
      };
      break;
    }
  }

  BATCH.running = false;
  BATCH.name = null;
  BATCH.onChange?.();
}

/**
 * The scan, drawn.
 *
 * Split in two because the two halves answer different questions: what is being recorded,
 * and what could be. One list of twenty-eight rows with a level control on each says
 * neither.
 *
 * @param {HTMLElement} body
 * @param {any[]} rows the engine's own scan
 * @param {Omit<Parameters<typeof repositoryTable>[0], "title"|"note"|"rows">} how
 */
function fillRepositories(body, rows, how) {
  body.innerHTML = "";
  const found = Array.isArray(rows) ? rows : [];
  // The group of sessions that belong to no repository arrives with no path. There is
  // nothing to enable for it, so it is a line rather than a row with a dead control on it.
  const listed = found.filter((row) => row.path);
  const unassigned = found.find((row) => !row.path);

  if (!listed.length) {
    body.appendChild(emptyState(t("section.repositories"), t("repositories.empty")));
  }

  const recorded = listed.filter((row) => row.enabled);
  const rest = listed.filter((row) => !row.enabled);
  if (recorded.length) {
    body.appendChild(
      repositoryTable({
        title: t("repositories.recorded"),
        note: t("repositories.recorded.note"),
        rows: recorded,
        ...how,
      })
    );
  }
  if (rest.length) {
    body.appendChild(
      repositoryTable({
        title: t("repositories.found"),
        note: t("repositories.found.note"),
        rows: rest,
        ...how,
      })
    );
  }

  if (unassigned && Number(unassigned.sessions) > 0) {
    body.appendChild(
      el("div", { class: "notes repo-notes" }, [
        el("div", {
          text: t("repositories.unassigned", sessionPhrase(Number(unassigned.sessions))),
        }),
      ])
    );
  }
}

/**
 * @param {import("./screens.js").ScreenState} state
 * @returns {Element}
 */
export function repositories(state) {
  const port = REPOSITORIES.port;
  const { data } = state;
  const screen = el("div", { class: "screen-body repositories-screen" });

  // The counts come from the scan, so the line is drawn empty and filled with it: a
  // sentence of two zeros while the engine is being asked would be two figures it has
  // not said.
  const summary = el("p", { class: "screen-summary", text: "" });
  screen.appendChild(summary);

  // What every screen is showing, when a row here set it. The picker above the other
  // screens says the same thing in its own place; here the row is the picker.
  if (state.project) {
    const back = el("button", { class: "btn", type: "button", text: t("repositories.filter.clear") });
    back.addEventListener("click", () => state.onProject(null));
    screen.appendChild(
      el("div", { class: "filter-note" }, [
        el("span", { text: t("repositories.filtered", state.project) }),
        back,
      ])
    );
  }

  const body = el("div", { class: "repo-list" });
  const card = el("div", { class: "card panel repo-card" }, [
    el("p", { class: "panel-note", text: t("repositories.note") }),
    body,
    disclosure({ summary: t("chart.method"), body: [el("p", { text: t("repositories.method") })] }),
  ]);
  screen.appendChild(card);

  if (!port) {
    // The page is open in a browser, which is a real thing to do while working on layout.
    body.appendChild(el("p", { class: "panel-note", text: t("settings.noShell") }));
    return screen;
  }

  // The scan in hand, what is ticked, and whether a single change is in flight. All of it
  // lives in this render's own closure: none of it is navigation and none of it is kept
  // between renders. A running **batch** is the one exception, kept in `BATCH` above.
  let scan = /** @type {any[]} */ ([]);
  let busy = false;
  /** @type {Set<string>} */
  const picked = new Set();

  // One node, kept between draws and emptied each time: it is at the foot of the card,
  // under the list and the method, and a node appended per draw would stack up.
  const actions = el("div", { class: "repo-actions-slot" });
  card.appendChild(actions);

  const failed = () => {
    body.innerHTML = "";
    body.appendChild(el("p", { class: "panel-note", text: t("repositories.unread") }));
    actions.innerHTML = "";
  };

  /** Set the window's project filter to this one, or clear it if it already is. */
  const filterBy = (project) => state.onProject(state.project === project ? null : project);

  const draw = () => {
    const running = BATCH.running;
    const counts = scanCounts(scan);
    summary.textContent = t("repositories.counts", count(counts.recorded), count(counts.found));
    fillRepositories(body, scan, {
      data,
      filter: state.project,
      change,
      busy: busy || running,
      picked,
      pick,
      pickAll,
      filterBy,
    });
    actions.innerHTML = "";
    if (picked.size || running || BATCH.failure) {
      actions.appendChild(
        batchBar({
          chosen: picked.size,
          busy: running,
          progress: running
            ? { name: BATCH.name, current: BATCH.index + 1, total: BATCH.keys.length }
            : null,
          failure: BATCH.failure,
          onLevel: (level) => beginBatch(level),
        })
      );
    }
  };

  const show = (rows) => {
    scan = Array.isArray(rows) ? rows : [];
    // A row the scan no longer carries cannot be acted on, so it is not counted either.
    const live = new Set(scan.map((row) => String(row.repoKey)));
    for (const key of [...picked]) if (!live.has(key)) picked.delete(key);
    draw();
  };

  // Reattach to a batch that is already running, or one that finished while this screen
  // was not shown, instead of starting this render's own idea of one. Only the render
  // mounted last is attached; an older one left holding this closure draws into detached
  // nodes, which costs nothing and is seen by nobody.
  BATCH.onChange = () => {
    if (BATCH.scan) show(BATCH.scan);
    else draw();
  };

  function pick(key, on) {
    if (busy || BATCH.running) return;
    if (on) picked.add(key);
    else picked.delete(key);
    // A refusal the reader has moved on from is not a refusal about this change.
    BATCH.failure = null;
    draw();
  }

  function pickAll(keys, on) {
    if (busy || BATCH.running) return;
    for (const key of keys) {
      if (on) picked.add(key);
      else picked.delete(key);
    }
    BATCH.failure = null;
    draw();
  }

  /** Ask the engine to change one repository, and redraw from **its** answer. */
  function change(row, level) {
    if (busy || BATCH.running || !REPOSITORIES.port) return;
    busy = true;
    // The scan already in hand, drawn again with every control dead: the engine is being
    // asked, and a control that answers a second click before the first one has landed is
    // a control that can be left disagreeing with the config.
    draw();
    REPOSITORIES.port.level(String(row.repoKey), String(level))
      .then((next) => {
        busy = false;
        // `prudence init --enable` writes `config.toml`, which no store stamp sees, so the
        // engine's fresh answer is handed to the memo rather than left to expire.
        REPOSITORY_SCAN.keep(data, next);
        show(next);
      })
      .catch(() => {
        busy = false;
        failed();
      });
  }

  /** Start a batch, unless one is already running. `startBatch` itself is the guard that
   *  survives a screen switch; the buttons being disabled while `BATCH.running` is the
   *  second: nothing offers a third click. */
  function beginBatch(level) {
    if (busy || BATCH.running || !REPOSITORIES.port) return;
    const keys = scan
      .filter((row) => row.path && picked.has(String(row.repoKey)))
      .map((row) => String(row.repoKey));
    if (!keys.length) return;
    void startBatch(REPOSITORIES.port, data, scan, keys, level);
  }

  // Asked for when the screen is drawn, and filled when the engine answers: it is a
  // subprocess that walks the machine's session history, and a blank area while it runs
  // would say nothing about the one question this screen is for.
  //
  // Through `store/asked.js`, which decides when the engine is asked at all: this screen
  // is redrawn on every store change and an ingest announces itself several times as it
  // works, and `init --scan` walks every repository on the machine.
  body.appendChild(el("p", { class: "panel-note", text: t("menu.engineChecking") }));
  REPOSITORY_SCAN.ask(data, () => port.scan()).then(show).catch(failed);

  return screen;
}
