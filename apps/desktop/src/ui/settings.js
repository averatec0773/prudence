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
 * - **Engine**: where `prudence` is, what version, the Install or Update button, the
 *   engine's recent runs with a diagnosis (`ui/engine-runs.js`), and where the store it
 *   reads is kept. Configuration only: the two actions that run the engine
 *   are in the window's toolbar, on every screen.
 * - **Model**: what `prudence config model` prints, and the one field of it this app may
 *   set. The app never calls a model itself, and the tab says so.
 * - **About**: what is running, on what, under what licence, and where to go next.
 *
 * Which repositories are recorded was a fifth tab until the founder gave it a screen of
 * its own in the sidebar (`ui/repositories.js`, 2026-09-23).
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

import { panel, segmented, subhead } from "../design/components.js";
import { el } from "../design/dom.js";
import { MODEL_ANSWER } from "../store/asked.js";
import { engineRuns } from "./engine-runs.js";
import { engineSection } from "./engine-section.js";
import { list, relative, stamp } from "../text/fmt.js";
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
  { key: "about", label: "settings.tab.about" },
]);

/** Which tab is open. See the note at the top of the file: navigation, not data. */
let openTab = "general";

/**
 * Open a tab the next time the screen is drawn. The window's status row sends the reader
 * to the Engine tab, where the engine's run records are listed; a key this screen does not
 * have is refused rather than stored, as a tab clicked here would be.
 *
 * @param {string} key
 */
export function openSettingsTab(key) {
  if (TABS.some((tab) => tab.key === key)) openTab = key;
}

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
    // version and the Install button, and owns its presentation with them, so it is
    // placed bare.
    engineSection(state),
    // What the engine recorded about its last runs, and the diagnosis. Its own module, on
    // the same seam: the run log is the shell's to read and this screen only places it.
    ...engineRuns(state),
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
  // and the four panes are all built whichever tab is open, so asking on every draw was
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

const PANES = { general, engine, model, about };

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
