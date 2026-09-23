/* Settings: four tabs of controls, and the provenance of what they control.
 *
 * ## What changed and why
 *
 * This screen used to be an information display. It reported the language, the appearance
 * and the store, said in so many words that it could change none of them, and carried the
 * record's whole promise as prose. The founder's reading of it: "it is an information
 * display, not a settings screen; I do not need the what-is-recorded and never-recorded
 * prose there; I need real settings, with top tabs, and the options the earlier app had."
 *
 * So the prose is gone, the controls are real, and the screen is four tabs:
 *
 * - **General**: the app's own four settings, each one a segmented control.
 * - **Engine**: where `prudence` is, what version, the actions, the Install button, and
 *   where the store it reads is kept.
 * - **Model**: what `prudence config model` prints, and the one field of it this app may
 *   set. The app never calls a model itself, and the tab says so.
 * - **Repositories**: which repositories the engine found on this machine, which of them
 *   it records, and the control that changes that.
 * - **About**: what is running, on what, under what licence, and where to go next.
 *
 * ## The page contract, and the one thing this screen keeps between renders
 *
 * It is handed everything, returns one element and computes no figure. The exception is
 * `openTab`: which tab is open is navigation, not data, and a screen rebuilt because an
 * ingest landed must not throw the reader back to General while they are half way through
 * changing the appearance. The four panes are built together and shown by a class, so a
 * tab change redraws nothing at all.
 *
 * ## Why the controls go through a port
 *
 * A screen may not call the bridge. `SETTINGS.port` is filled in by `ui/wiring.js`, the
 * same way the engine block's is, which is also what lets the whole screen be driven
 * against a fake shell in `test/settings.test.mjs`.
 */

import { emptyState, panel, runProgress } from "../design/components.js";
import { el } from "../design/dom.js";
import { MODEL_ANSWER, REPOSITORY_SCAN } from "../store/asked.js";
import { engineSection } from "./engine-section.js";
import {
  count,
  fromDay,
  list,
  relative,
  sessions as sessionPhrase,
  stamp,
} from "../text/fmt.js";
import { t } from "../text/strings.js";

/**
 * What the four tabs ask the shell.
 *
 * @typedef {{
 *   read: () => Promise<any>,
 *   language: (code: string) => Promise<any>,
 *   appearance: (code: string) => Promise<any>,
 *   openAtLogin: (on: boolean) => Promise<any>,
 *   timedIngest: (minutes: number) => Promise<any>,
 *   model: () => Promise<any>,
 *   modelLanguage: (code: string) => Promise<any>,
 *   repositories: () => Promise<any>,
 *   repositoryLevel: (key: string, level: string) => Promise<any>,
 *   link: (name: string) => Promise<any>,
 * }} SettingsPort
 *
 * @type {{ port: SettingsPort | null }}
 */
export const SETTINGS = { port: null };

/** The tabs, left to right. The key is not a display string. */
export const TABS = /** @type {const} */ ([
  { key: "general", label: "settings.tab.general" },
  { key: "engine", label: "settings.tab.engine" },
  { key: "model", label: "settings.tab.model" },
  { key: "repositories", label: "settings.tab.repositories" },
  { key: "about", label: "settings.tab.about" },
]);

/** Which tab is open. See the note at the top of the file: navigation, not data. */
let openTab = "general";

/** The licence in the repository's own `LICENSE`, by its SPDX name. Not translated. */
const LICENCE = "Apache-2.0";

/** The founder's own account name. A handle is not translated, and it is not a catalogue
 *  key for the same reason `PRODUCT_NAME` is not one. */
const DEVELOPER = "averatec0773";

/**
 * A language's name in its own language. Not catalogue keys: an autonym reads the same
 * whatever language is in force, which is the whole point of one, and a key whose two
 * values are identical is what `strings.test.mjs` refuses.
 */
const LANGUAGE_NAMES = { en: "English", "zh-Hans": "简体中文" };

/** The variable `lib.rs` reads when a screenshot run forces a language. A variable name
 *  is not translated. */
const FORCE_LANGUAGE = "PRUDENCE_FORCE_LANGUAGE";

/** The `app_status` columns that carry a version, in the order the engine runs them. */
const VERSIONS = [
  ["parser_version", "settings.version.parser"],
  ["bucket_rule_version", "settings.version.bucketRule"],
  // Still the rule behind a stored review's activity table and an observation split on a
  // purpose, so it stays listed until the engine drops the label.
  ["purpose_rule_version", "settings.version.purposeRule"],
  ["commit_fact_version", "settings.version.commit"],
  ["attribution_fact_version", "settings.version.attribution"],
  ["outcome_fact_version", "settings.version.outcome"],
  ["observation_fact_version", "settings.version.observation"],
  ["hook_fact_version", "settings.version.hook"],
];

/* --- the pieces this screen is built from ------------------------------------------- */

/**
 * One fact: its caption above it, its value under that, and any qualification below.
 *
 * Caption **above**, not in a left column. `DESIGN.md` records the founder's
 * clarification that a block carries its caption above it rather than reading as a title
 * on the left and a value on the right, which is also the only layout a ninety-character
 * path fits in.
 *
 * @param {string} caption
 * @param {string} value
 * @param {string[]} [notes]
 * @param {{ path?: boolean }} [options] a path or a URL is selectable, so it can be copied
 * @returns {HTMLElement}
 */
function fact(caption, value, notes, options) {
  const block = el("div", { class: "fact" }, [
    el("div", { class: "fact-label", text: caption }),
    el("div", { class: options?.path ? "fact-value is-path" : "fact-value", text: value }),
  ]);
  const said = (notes ?? []).filter(Boolean);
  if (said.length) {
    block.appendChild(
      el(
        "div",
        { class: "notes fact-notes" },
        said.map((line) => el("div", { text: line }))
      )
    );
  }
  return block;
}

/** A sub-heading inside a card, for a block with its own caption and its own note. */
function subhead(title, note) {
  return el("div", { class: "settings-subhead" }, [
    el("h3", { text: title }),
    el("p", { text: note }),
  ]);
}

/** Name and value, a row at a time, with the name as the row's own header. */
function pairs(rows) {
  const body = el("tbody");
  for (const [name, value] of rows) {
    body.appendChild(
      el("tr", {}, [el("th", { scope: "row", text: name }), el("td", { text: value })])
    );
  }
  return el("table", { class: "data settings-pairs" }, [body]);
}

/**
 * The control itself: one row of choices, one of them ticked.
 *
 * Its own function because the Repositories tab puts one in a table cell, where the label
 * and the note a setting carries would be a second copy of the column header. Whatever
 * holds it, the ticked choice is the one the shell answered with.
 *
 * `disabled` is for a control whose answer is still on its way: a second click before the
 * first one has landed is how a control ends up disagreeing with what it controls.
 *
 * A choice may carry a `title`: the Repositories table shows "Meta" where the General tab
 * would have room for "Metadata only", and a label shortened to fit a column still has to
 * say what it means to a pointer and to a screen reader.
 *
 * @param {{ label: string, choices: {value: any, label: string, title?: string}[], chosen: any,
 *           onChoose: (value: any) => void, disabled?: boolean }} options
 * @returns {HTMLElement}
 */
function segmented({ label, choices, chosen, onChoose, disabled }) {
  const group = el("div", { class: "segmented", role: "radiogroup", "aria-label": label });
  for (const choice of choices) {
    const button = el("button", { type: "button", role: "radio", text: choice.label });
    button.setAttribute("aria-checked", String(choice.value === chosen));
    if (choice.title) {
      button.setAttribute("title", choice.title);
      button.setAttribute("aria-label", choice.title);
    }
    if (disabled) /** @type {any} */ (button).disabled = true;
    button.addEventListener("click", () => onChoose(choice.value));
    group.appendChild(button);
  }
  return group;
}

/**
 * A box that is ticked or not, with its name only to a screen reader.
 *
 * The Repositories table's own control, and the only one in the app: a column header of
 * "Select" over a column of boxes would be a word the reader does not need, and the row
 * the box belongs to is what says what is being selected.
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
 * One setting: its name, a segmented control, and a line under it.
 *
 * **Every control on this screen is this one.** Four settings in four shapes is four
 * things to learn; a segmented control says what the choices are without being opened,
 * which is what a settings screen with six visible rows wants. It is also the control the
 * window's own range picker already uses, so the app has one of them and not two.
 *
 * The control is set from the value that came back from the shell, never from what was
 * asked for: `settings_open_at_login` in particular can be refused by the system, and a
 * control that ticks itself on a refusal is a control that lies.
 *
 * @param {{ label: string, note?: string, choices: {value: any, label: string}[],
 *           chosen: any, onChoose: (value: any) => void, foot?: Element|null }} options
 */
function setting({ label, note, choices, chosen, onChoose, foot }) {
  const group = segmented({ label, choices, chosen, onChoose });

  const row = el("div", { class: "setting" }, [
    el("div", { class: "setting-head" }, [
      el("div", { class: "setting-label", text: label }),
      group,
    ]),
  ]);
  if (note) row.appendChild(el("div", { class: "setting-note", text: note }));
  if (foot) row.appendChild(foot);
  return row;
}

/* --- General ------------------------------------------------------------------------ */

/** The three words every language control on this screen offers. The app's own and the
 *  engine's are the same three, which is not a coincidence: they are the same question
 *  asked of two programs. */
function languageChoices() {
  return [
    { value: "system", label: t("settings.choice.system") },
    { value: "en", label: LANGUAGE_NAMES.en },
    { value: "zh-Hans", label: LANGUAGE_NAMES["zh-Hans"] },
  ];
}

/** Off, and the four intervals. The minutes are the shell's own list (`ui_state.rs`,
 *  `INGEST_INTERVALS`), and a value outside it is refused there.
 *
 *  Off is `settings.choice.off`, the same word the other three settings use. It asked for
 *  `settings.interval.off` before, which is in neither table, so the control drew the key
 *  itself: found on 2026-09-22 in a screenshot of the General tab, not by a test, because
 *  nothing asserts that a key a screen asks for exists. */
function intervalChoices() {
  return [
    { value: 0, label: t("settings.choice.off") },
    { value: 15, label: t("settings.interval.15m") },
    { value: 30, label: t("settings.interval.30m") },
    { value: 60, label: t("settings.interval.1h") },
    { value: 360, label: t("settings.interval.6h") },
  ];
}

/**
 * The app's own settings.
 *
 * Every control writes through the shell and then **redraws from the answer**, which is
 * how a refused login item shows as refused. The shell also announces the change to both
 * pages, so the panel follows a language chosen here without being relaunched.
 */
function general(state) {
  const port = SETTINGS.port;
  const body = el("div", { class: "setting-list" });

  if (!port) {
    // The page is open in a browser, which is a real thing to do while working on layout.
    // It says so rather than drawing four controls that would do nothing.
    body.appendChild(el("p", { class: "setting-note", text: t("settings.noShell") }));
    return panel({ title: t("settings.tab.general"), note: t("settings.general.note"), body });
  }

  const now = state.info?.settings ?? {};

  // Ask the shell, and let it say when the answer is in.
  //
  // **Not `state.redraw()`.** A redraw here would rebuild this screen from the `info` the
  // page was booted with, which is exactly the thing that has just changed, so the control
  // would snap back to the old value for as long as it took the event to arrive. The shell
  // announces every setting change to both pages, `boot.js` asks for the whole of
  // `shell_info` again and draws from that, and this screen comes back with the answer in
  // it. The same event is what carries a language chosen here to the panel.
  //
  // A rejection is a defect in the bridge rather than a refusal: the shell answers `Ok`
  // with what is actually in force even when the system says no. `ui/wiring.js` reports
  // one on the shell's standard error, which is where a screen's failures have to go,
  // because a screen may not call the bridge itself.
  const after = (promise) => {
    void promise;
  };

  body.appendChild(
    setting({
      label: t("settings.language"),
      note: state.info?.language && now.language === "system"
        ? t("settings.language.forced", FORCE_LANGUAGE)
        : t("settings.language.note"),
      choices: languageChoices(),
      chosen: now.language ?? "system",
      onChoose: (value) => after(port.language(value)),
    })
  );

  body.appendChild(
    setting({
      label: t("settings.appearance"),
      note: t("settings.appearance.note"),
      choices: [
        { value: "system", label: t("settings.choice.system") },
        { value: "light", label: t("settings.appearance.light") },
        { value: "dark", label: t("settings.appearance.dark") },
      ],
      chosen: now.appearance ?? "system",
      onChoose: (value) => after(port.appearance(value)),
    })
  );

  body.appendChild(
    setting({
      label: t("settings.openAtLogin"),
      note: t("settings.openAtLogin.note"),
      choices: [
        { value: false, label: t("settings.choice.off") },
        { value: true, label: t("settings.choice.on") },
      ],
      chosen: Boolean(now.openAtLogin),
      onChoose: (value) => after(port.openAtLogin(value)),
      // The system's own words for why it would not register the login item, under the
      // app's sentence for it. English, like every other message from something that is
      // not this app.
      foot: now.loginError
        ? el("div", { class: "notes fact-notes" }, [
            el("div", { text: t("settings.openAtLogin.refused") }),
            el("div", { text: String(now.loginError) }),
          ])
        : null,
    })
  );

  body.appendChild(
    setting({
      label: t("settings.timedIngest"),
      note: t("settings.timedIngest.note"),
      choices: intervalChoices(),
      chosen: Number(now.ingestEveryMinutes ?? 0),
      onChoose: (value) => after(port.timedIngest(value)),
    })
  );

  return panel({ title: t("settings.tab.general"), note: t("settings.general.note"), body });
}

/* --- Engine ------------------------------------------------------------------------- */

/** Where the store is, when it was last written, and what produced what is in it. */
function whereItIsKept(data, info) {
  const status = data.status;
  const unread = t("settings.store.unread");
  const ingest = status?.last_ingest_at;
  const contract = status?.app_contract_version;
  const supported = Array.isArray(info?.supported_contract) ? info.supported_contract : [];

  const body = el("div", { class: "fact-list" }, [
    fact(
      t("settings.databasePath"),
      info?.database ?? unread,
      [t("settings.databasePath.resolved")],
      { path: true }
    ),
    fact(
      t("menu.lastIngest"),
      ingest ? t("common.dateWithRelative", stamp(ingest), relative(ingest)) : t("menu.never")
    ),
    fact(
      t("settings.store.contract"),
      contract && supported.length
        ? t(
            "settings.store.contract.value",
            String(contract),
            list(supported.map((one) => String(one)))
          )
        : unread
    ),
  ]);

  // A store whose row lacks a column, because the engine that wrote it predates that
  // fact, leaves the step out rather than printing a dash: a missing version means "this
  // step has not run here", which the row's absence says and a dash does not.
  const present = VERSIONS.filter(
    ([column]) => status?.[column] !== null && status?.[column] !== undefined
  );
  if (present.length) {
    const table = el("table", { class: "data" }, [
      el("thead", {}, [
        el("tr", {}, [
          el("th", { text: t("settings.versions.column.step") }),
          el("th", { class: "n", text: t("settings.versions.column.version") }),
        ]),
      ]),
    ]);
    const rows = el("tbody");
    for (const [column, label] of present) {
      rows.appendChild(
        el("tr", {}, [
          el("td", { text: t(label) }),
          // A version is an identifier and not a quantity, so it is not grouped.
          el("td", { class: "n", text: String(status[column]) }),
        ])
      );
    }
    table.appendChild(rows);
    body.appendChild(
      el("div", { class: "fact-block" }, [
        subhead(t("settings.versions"), t("settings.versions.note")),
        table,
      ])
    );
  }

  return panel({
    title: t("settings.store"),
    note: t("settings.store.note"),
    body,
    method: t("settings.store.method"),
  });
}

function engine(state) {
  return el("div", { class: "tab-body" }, [
    // The seam with the CLI wiring. That module owns where the executable is, its own
    // version, the actions and the Install button, and owns its presentation with them,
    // so it is placed bare.
    engineSection(state),
    whereItIsKept(state.data, state.info),
  ]);
}

/* --- Model -------------------------------------------------------------------------- */

/**
 * What the engine would send to a model, and the one thing this app may change about it.
 *
 * Every row is a line `prudence config model` printed, read in `src-tauri/src/model.rs`.
 * The key is a **variable name** and never a value, which is a property of the CLI's own
 * output and is kept by adding nothing to it.
 */
function model(state) {
  const port = SETTINGS.port;
  const { data } = state;
  const body = el("div", { class: "setting-list" });
  const card = panel({
    title: t("settings.tab.model"),
    note: t("settings.model.note"),
    body,
    method: t("settings.model.method"),
  });

  if (!port) {
    body.appendChild(el("p", { class: "setting-note", text: t("settings.noShell") }));
    return el("div", { class: "tab-body" }, [card]);
  }

  // Asked for when the tab is drawn, and filled when the engine answers: it is a
  // subprocess, and a blank area while it runs would say nothing about the one question
  // this tab is for.
  //
  // Through `store/asked.js`, which decides when the engine is asked at all. This screen
  // is redrawn on every store change, an ingest announces itself eight times as it works,
  // and the five panes are all built whichever tab is open, so asking on every draw was
  // one `prudence config model` per announcement while the engine was busy.
  body.appendChild(el("p", { class: "setting-note", text: t("menu.engineChecking") }));
  MODEL_ANSWER.ask(data, () => port.model())
    .then((settings) => fillModel(body, settings, data))
    .catch(() => {
      body.innerHTML = "";
      body.appendChild(el("p", { class: "setting-note", text: t("settings.model.unread") }));
    });

  return el("div", { class: "tab-body" }, [card]);
}

/**
 * @param {any} body
 * @param {any} settings what `prudence config model` printed
 * @param {any} data the payload this render is drawing, so a change made here is
 *   remembered against it: setting the prose language writes the engine's own config file
 *   and moves no stamp.
 */
function fillModel(body, settings, data) {
  body.innerHTML = "";
  const port = SETTINGS.port;
  const rows = [
    [t("settings.model.backend"), settings?.backend],
    [t("settings.model.id"), settings?.modelId],
    [t("settings.model.key"), settings?.keyVariable],
    [t("settings.model.maxTokens"), settings?.maxTokens],
    [t("settings.model.explain"), settings?.explain],
  ].filter(([, value]) => value);

  if (rows.length) {
    body.appendChild(pairs(rows.map(([name, value]) => [name, String(value)])));
  }

  body.appendChild(
    setting({
      label: t("settings.model.language"),
      note: t("settings.model.language.note"),
      choices: languageChoices(),
      chosen: settings?.languageKey ?? "system",
      onChoose: (value) => {
        if (!port) return;
        port
          .modelLanguage(value)
          .then((next) => {
            MODEL_ANSWER.keep(data, next);
            fillModel(body, next, data);
          })
          .catch(() => fillModel(body, settings, data));
      },
    })
  );

  if (settings?.configPath) {
    body.appendChild(
      fact(t("settings.model.configPath"), String(settings.configPath), [], { path: true })
    );
  }
}

/* --- Repositories ---------------------------------------------------------------------
 *
 * The tab that answers the founder's own question about this app: "why are only three
 * repositories recorded?" Because recording is opt-in per repository, which is the first
 * sentence on the tab and the reason the list is split in two. Everything on it is a field
 * of `prudence init --scan --json`; the app counts nothing and decides nothing.
 *
 * **The list is content**, so it is opaque like every other card. The tab strip above it
 * is the control layer and takes the frost; design rule 1.
 */

/** Off, and the engine's two levels. The words that reach the command line are checked
 *  again in `src-tauri/src/repositories.rs`, so nothing this file sends can be an
 *  argument on its own.
 *
 *  The labels are the **short** ones, and the reason is the column: three segments in a
 *  hundred and sixty points have room for a word each, and "Metadata only" against
 *  "仅元数据" is what wrapped a segment onto two lines in the founder's screenshot. The
 *  full name is on the segment's `title`, and the block's own note spells both levels out
 *  in a sentence. */
function levelChoices() {
  return [
    { value: "off", label: t("settings.choice.off") },
    {
      value: "metadata-only",
      label: t("settings.repositories.level.metadataOnly.short"),
      title: t("settings.repositories.level.metadataOnly"),
    },
    { value: "full", label: t("settings.repositories.level.full") },
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
 * Not catalogue keys, for the reason `LANGUAGE_NAMES` is not one: a product's name is the
 * same in both languages, and a key whose two values are identical is what
 * `strings.test.mjs` refuses. A key Prudence has not learned yet is drawn as the engine
 * wrote it rather than hidden.
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
 * The project column is the only one the table does not give a width to, so it is the one
 * that gets what the other six leave: about a hundred and forty points. A path cut by CSS
 * from the left reads `/Users/averatec…`, which is the part every path on the machine has
 * in common and says nothing; the last three components are what two checkouts of one
 * repository differ in. The whole path is on the element's `title` either way.
 */
function shortPath(path) {
  const parts = String(path).split("/").filter(Boolean);
  if (parts.length <= PATH_PARTS) return String(path);
  return `…/${parts.slice(-PATH_PARTS).join("/")}`;
}

/**
 * A day the scan carries, as `2026-05-14` in both languages.
 *
 * Numeric and fixed width, not the reader's own order. `2026年5月14日` is eleven
 * characters that break anywhere, which is what put two dates on two lines each in the
 * founder's screenshot, and a column of days that are being compared against each other
 * reads better aligned than idiomatic. The engine writes its timestamps in this order
 * already, so the day is its own first ten characters, checked through `fromDay` so that
 * something that is not a day is a dash rather than ten characters of anything.
 *
 * **This belongs in `text/fmt.js`**, beside `day` and `shortDay`, and goes there once the
 * batch that owns that file has landed.
 */
function scanDay(value) {
  if (value === null || value === undefined || value === "") return t("common.dash");
  const date = fromDay(String(value).slice(0, 10));
  if (!date) return t("common.dash");
  const pad = (part) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/**
 * One block of the list: a heading, its note, and a row per repository.
 *
 * **The columns are declared, not discovered.** The table was automatic before, which
 * means the browser sized every column from its contents: in Chinese the header
 * "发现的会话" and the date "2026年5月14日" both break between any two characters, so the
 * layout gave the count and the dates the narrowest width it could find a break at and
 * wrapped all three. The `<colgroup>` below plus `table-layout: fixed` in `settings.css`
 * is the fix: every column but the project's has a width, and every cell that carries a
 * figure, a day or a control is `nowrap`. Only the path may lose characters, to an
 * ellipsis, with the whole of it on the element's `title`.
 *
 * @param {{ title: string, note: string, rows: any[], change: (row: any, level: string) => void,
 *           busy: boolean, picked: Set<string>, pick: (key: string, on: boolean) => void,
 *           pickAll: (keys: string[], on: boolean) => void }} block
 */
function repositoryTable({ title, note, rows, change, busy, picked, pick, pickAll }) {
  const keys = rows.map((row) => String(row.repoKey));
  const all = keys.length > 0 && keys.every((key) => picked.has(key));

  const columns = el("colgroup", {}, [
    el("col", { class: "c-pick" }),
    el("col", { class: "c-name" }),
    el("col", { class: "c-sessions" }),
    el("col", { class: "c-sources" }),
    el("col", { class: "c-when" }),
    el("col", { class: "c-when" }),
    el("col", { class: "c-level" }),
  ]);

  const head = el("thead", {}, [
    el("tr", {}, [
      el("th", { class: "repo-pick" }, [
        tick({
          label: t("settings.repositories.selectAll"),
          checked: all,
          onChange: (on) => pickAll(keys, on),
          disabled: busy,
        }),
      ]),
      el("th", { text: t("scope.project") }),
      el("th", { class: "n nowrap", text: t("settings.repositories.column.sessions") }),
      el("th", { class: "nowrap", text: t("settings.repositories.column.sources") }),
      el("th", { class: "nowrap", text: t("settings.repositories.column.first") }),
      el("th", { class: "nowrap", text: t("settings.repositories.column.last") }),
      el("th", { class: "nowrap repo-level", text: t("settings.repositories.column.level") }),
    ]),
  ]);

  const body = el("tbody");
  for (const row of rows) {
    const shortName = basename(row.path);
    const name = el("div", { class: "repo-name", text: shortName, title: String(row.path) });
    // The full path under the name, as the sentence that says which one this is: two
    // checkouts of the same repository have the same last component. It is the one value
    // on the row allowed to lose characters, because it is the one value with a hundred
    // of them; the whole of it is on the `title` and it is still selectable.
    const where = el("div", {
      class: "repo-path",
      text: shortPath(row.path),
      title: String(row.path),
    });
    const cell = el("td", { class: "repo-what" }, [name, where]);
    // A repository that is on record and no longer on disk is still on record, and a
    // reader looking for it has to be told which of the two states it is in.
    if (!row.exists) {
      cell.appendChild(el("div", { class: "repo-gone", text: t("settings.repositories.gone") }));
    }

    const sources = sourceNames(row);
    body.appendChild(
      el("tr", {}, [
        el("td", { class: "repo-pick" }, [
          tick({
            label: t("settings.repositories.select", shortName),
            checked: picked.has(String(row.repoKey)),
            onChange: (on) => pick(String(row.repoKey), on),
            disabled: busy,
          }),
        ]),
        cell,
        el("td", { class: "n nowrap", text: count(Number(row.sessions ?? 0)) }),
        el("td", { class: "nowrap repo-sources", text: sources, title: sources }),
        el("td", { class: "nowrap repo-when", text: scanDay(row.firstAt) }),
        el("td", { class: "nowrap repo-when", text: scanDay(row.lastAt) }),
        el("td", { class: "nowrap repo-level" }, [
          segmented({
            label: t("settings.repositories.column.level"),
            choices: levelChoices(),
            chosen: levelOf(row),
            onChoose: (value) => change(row, value),
            disabled: busy,
          }),
        ]),
      ])
    );
  }

  return el("div", { class: "fact-block" }, [
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
 * changed and how far through the list that is, in the same bar `runProgress` draws on
 * the Engine tab and the panel: a determinate bar per repository, because the engine is
 * being run once per repository and a bar that said nothing would be a bar that looks
 * stuck on a list of twenty.
 *
 * `progress`'s row is **reserved, never revealed**: it is in the bar whether or not a
 * batch is running, empty when it is not, at the height its answer needs. Filling it
 * while the bar is already on screen (every button click that starts a batch) then
 * changes no node and no height, the same rule `app.css`'s `.pop-reserve` keeps for the
 * panel's own footer.
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
      text: progress ? "" : t("settings.repositories.batch.selected", count(chosen)),
    }),
  ]);

  const set = el("div", { class: "repo-actions-set" }, [
    el("span", { class: "repo-actions-label", text: t("settings.repositories.batch.label") }),
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
        // No `step`: the batch is not one of the engine's eleven, so `runProgress` falls
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
      el("div", { class: "notes fact-notes" }, [
        el("div", { text: t("settings.repositories.batch.failed", failure.name) }),
        el("div", { text: failure.message }),
      ])
    );
  }
  return bar;
}

/**
 * A batch level-change in flight, kept outside any screen's own tree.
 *
 * A switch to another screen throws the whole Settings tree away and rebuilds it from
 * nothing (`window.js`: `nodes.screen.innerHTML = ""`), which used to throw this away
 * too: the loop below kept running, because nothing had cancelled the promises it was
 * awaiting, but it drew into detached nodes nobody could see, and the tab it came back to
 * built a fresh closure that had never heard of it, with no bar and no disabled controls.
 * The founder's own instruction is that a batch **finishes** rather than stops, so what
 * it needs in order to keep saying what it is doing lives here instead, the way
 * `store/asked.js` keeps the engine's own answers against the store rather than in a
 * screen's closure. The Repositories tab reattaches to this on every render rather than
 * starting a batch of its own, and `startBatch` itself refuses to run two at once.
 *
 * Exported for the same reason `SETTINGS` is: a batch that outlives the screen it started
 * on also outlives one test's `fakePort()`, so `test/settings.test.mjs` resets it between
 * tests the same way it resets `SETTINGS.port` and the two memos in `store/asked.js`.
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
 * (`src-tauri/src/lib.rs`), so its own response already is a fresh scan; a row is drawn
 * from it the moment it lands rather than waiting for the whole run to finish, which is
 * also what lets a row flip to its new level as soon as its own change has, rather than
 * all of them flipping together at the end. The last call's answer already is the final
 * state, so the loop that used to read the whole list once more when it was done is gone:
 * that call cost exactly what every `repositoryLevel` call already costs, for nothing a
 * `repositoryLevel` call had not just answered.
 *
 * A refusal stops the run where it is. `BATCH.scan` is the last answer that landed, so
 * the repositories before the refusal are already drawn as changed and stay that way;
 * nothing after it touched `BATCH.scan` at all.
 *
 * @param {any} port
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
      const next = await port.repositoryLevel(key, String(level));
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
 * @param {{ change: (row: any, level: string) => void, busy: boolean, picked: Set<string>,
 *           pick: (key: string, on: boolean) => void,
 *           pickAll: (keys: string[], on: boolean) => void }} how
 */
function fillRepositories(body, rows, how) {
  body.innerHTML = "";
  const found = Array.isArray(rows) ? rows : [];
  // The group of sessions that belong to no repository arrives with no path. There is
  // nothing to enable for it, so it is a line rather than a row with a dead control on it.
  const known = found.filter((row) => row.path);
  const unassigned = found.find((row) => !row.path);

  if (!known.length) {
    body.appendChild(emptyState(t("settings.tab.repositories"), t("settings.repositories.empty")));
  }

  const recorded = known.filter((row) => row.enabled);
  const rest = known.filter((row) => !row.enabled);
  if (recorded.length) {
    body.appendChild(
      repositoryTable({
        title: t("settings.repositories.recorded"),
        note: t("settings.repositories.recorded.note"),
        rows: recorded,
        ...how,
      })
    );
  }
  if (rest.length) {
    body.appendChild(
      repositoryTable({
        title: t("settings.repositories.found"),
        note: t("settings.repositories.found.note"),
        rows: rest,
        ...how,
      })
    );
  }

  if (unassigned && Number(unassigned.sessions) > 0) {
    body.appendChild(
      el("div", { class: "notes fact-notes" }, [
        el("div", {
          text: t(
            "settings.repositories.unassigned",
            sessionPhrase(Number(unassigned.sessions))
          ),
        }),
      ])
    );
  }
}

function repositories(state) {
  const port = SETTINGS.port;
  const { data } = state;
  const body = el("div", { class: "fact-list repo-list" });
  const card = panel({
    title: t("settings.tab.repositories"),
    note: t("settings.repositories.note"),
    body,
    method: t("settings.repositories.method"),
  });

  if (!port) {
    body.appendChild(el("p", { class: "setting-note", text: t("settings.noShell") }));
    return el("div", { class: "tab-body" }, [card]);
  }

  // The scan in hand, what is ticked, and whether a single change is in flight. All of it
  // lives in this render's own closure rather than in the module: which tab is open is
  // navigation and is kept between renders, and none of this is. A running **batch** is
  // the one exception, kept in `BATCH` above rather than here, for the reason given there.
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
    body.appendChild(el("p", { class: "setting-note", text: t("settings.repositories.unread") }));
    actions.innerHTML = "";
  };

  const draw = () => {
    const running = BATCH.running;
    fillRepositories(body, scan, { change, busy: busy || running, picked, pick, pickAll });
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

  // Reattach to a batch that is already running, or one that finished while this tab was
  // on another screen, instead of starting this render's own idea of one: `BATCH.scan` is
  // the engine's own latest answer, so it is drawn the same way any other answer is. Only
  // the render mounted last is attached; an older one left holding this closure draws
  // into detached nodes, which costs nothing and is seen by nobody.
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
    if (busy || BATCH.running || !SETTINGS.port) return;
    busy = true;
    // The scan already in hand, drawn again with every control dead: the engine is being
    // asked, and a control that answers a second click before the first one has landed is
    // a control that can be left disagreeing with the config.
    draw();
    SETTINGS.port.repositoryLevel(String(row.repoKey), String(level))
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
   *  survives a screen switch; this is only the first line of defence, and the buttons
   *  being disabled while `BATCH.running` is the second: nothing offers a third click. */
  function beginBatch(level) {
    if (busy || BATCH.running || !SETTINGS.port) return;
    const keys = scan
      .filter((row) => row.path && picked.has(String(row.repoKey)))
      .map((row) => String(row.repoKey));
    if (!keys.length) return;
    void startBatch(SETTINGS.port, data, scan, keys, level);
  }

  // Asked for when the tab is drawn, and filled when the engine answers: it is a
  // subprocess that walks the machine's session history, and a blank area while it runs
  // would say nothing about the one question this tab is for.
  //
  // Through `store/asked.js`, for the reason on the Model tab above and more so here:
  // `init --scan` walks every repository on the machine, and it was being run once per
  // watcher announcement while an ingest was writing the store.
  body.appendChild(el("p", { class: "setting-note", text: t("menu.engineChecking") }));
  REPOSITORY_SCAN.ask(data, () => port.repositories()).then(show).catch(failed);

  return el("div", { class: "tab-body" }, [card]);
}

/* --- About -------------------------------------------------------------------------- */

/** A plain label that opens something in the system browser.
 *
 *  A `<a href>` inside a Tauri webview navigates the app away from its own page, so the
 *  shell opens the link. The page asks **by name**: `LINKS` in `lib.rs` holds the
 *  addresses, so nothing this page invents can be opened. */
function linkButton(label, name) {
  const button = el("button", { class: "btn plain", type: "button", text: label });
  button.addEventListener("click", () => SETTINGS.port?.link(name));
  return button;
}

function about(state) {
  const { data, info } = state;
  const unread = t("settings.store.unread");
  const body = el("div", { class: "fact-list" }, [
    fact(t("settings.about.app"), info?.version ?? t("common.dash")),
    fact(t("settings.about.engine"), data.status?.engine_version ?? unread),
    fact(t("settings.about.licence"), LICENCE),
    fact(t("settings.about.developer"), DEVELOPER),
  ]);

  // The shell's own description of this machine, in its own words. Pairs rather than
  // sentences: `NSAppKitVersionNumber` is a name a reader would quote in a bug report,
  // and translating it would make it useless for that.
  const described = Array.isArray(info?.platform) ? info.platform : [];
  if (described.length) {
    body.appendChild(
      el("div", { class: "fact-block" }, [
        subhead(t("settings.about.platform"), t("settings.about.platform.note")),
        pairs(described.map(([name, value]) => [String(name), String(value)])),
      ])
    );
  }

  // Three plain labels. "What is recorded" is the one thing left of the promise this
  // screen used to carry in full: the README says it better and stays true when the
  // engine changes, and a settings screen is not where a reader reads six paragraphs.
  body.appendChild(
    el("div", { class: "engine-actions" }, [
      linkButton(t("settings.about.project"), "project"),
      linkButton(t("settings.about.developerLink"), "developer"),
      linkButton(t("settings.about.recorded"), "recorded"),
    ])
  );

  return el("div", { class: "tab-body" }, [
    panel({
      title: t("settings.tab.about"),
      note: t("settings.about.note"),
      body,
      method: t("settings.about.method"),
    }),
  ]);
}

/* --- the screen --------------------------------------------------------------------- */

const PANES = { general, engine, model, repositories, about };

/**
 * @param {import("./screens.js").ScreenState} state
 * @returns {Element}
 */
export function settings(state) {
  const screen = el("div", { class: "screen-body settings-screen" });

  // The tab strip is control layer, so it takes the frost where the platform has one;
  // everything under it is opaque. That is design rule 1, and `settings.css` is where the
  // two halves are written.
  const strip = el("div", { class: "tabs", role: "tablist", "aria-label": t("settings.title") });
  const panes = el("div", { class: "tab-panes" });

  const shown = PANES[openTab] ? openTab : "general";
  const buttons = [];
  const built = [];

  for (const tab of TABS) {
    const button = el("button", { class: "tab", type: "button", role: "tab", text: t(tab.label) });
    button.setAttribute("aria-selected", String(tab.key === shown));
    const pane = el("div", { class: "tab-pane", role: "tabpanel" }, [PANES[tab.key](state)]);
    pane.hidden = tab.key !== shown;
    // The four panes are built together and shown by a flag, so choosing a tab redraws
    // nothing: a redraw would ask the shell for the model settings again and would lose
    // whatever the engine block had already reported.
    button.addEventListener("click", () => {
      openTab = tab.key;
      buttons.forEach((other, index) =>
        other.setAttribute("aria-selected", String(TABS[index].key === openTab))
      );
      built.forEach((other, index) => {
        other.hidden = TABS[index].key !== openTab;
      });
    });
    buttons.push(button);
    built.push(pane);
    strip.appendChild(button);
    panes.appendChild(pane);
  }

  screen.appendChild(strip);
  screen.appendChild(panes);
  return screen;
}
