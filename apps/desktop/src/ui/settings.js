/* Settings: what is recorded and where, what is never recorded, and what is running.
 *
 * **This screen is read-only, and says so where a control is missing.** There is no
 * bridge command that writes a setting: `bridge.js` reads the store, asks the shell
 * about itself, and moves windows. So every row here reports what is in force and where
 * it is changed, which is the CLI or `config.toml`. A screen of switches that silently
 * did nothing would be worse than this, because the reader would believe them.
 *
 * What it is for. Three of the four screens answer "what happened"; this one answers
 * "what does this thing know about me, and where does it keep it". That is why the
 * record's own promise is on it in full rather than only in the README, and why the fact
 * versions are here: they are the provenance of every figure the other screens draw.
 *
 * It keeps the page contract (`DESIGN.md`): handed everything, reaches for nothing,
 * returns one element, computes nothing. The one count it prints per row comes from
 * `store/settings.js`; everything else is a column of `app_status`, a field of
 * `shell_info` or a string.
 */

import { emptyState, panel } from "../design/components.js";
import { el } from "../design/dom.js";
import { recorded } from "../store/settings.js";
import { engineSection } from "./engine-section.js";
import { count, list, relative, sessions, stamp } from "../text/fmt.js";
import { lang, plural, t } from "../text/strings.js";

/**
 * Where the project is. Not a catalogue key, for the same reason `PRODUCT_NAME` is not
 * one: a URL is not translated. It is printed rather than linked because opening a link
 * needs the shell to hand it to the system browser and no bridge command does, and a
 * plain `<a href>` inside a Tauri webview navigates the app away from its own page.
 */
const PROJECT_URL = "https://github.com/averatec0773/prudence";

/** The licence in the repository's own `LICENSE`, by its SPDX name. Not translated. */
const LICENCE = "Apache-2.0";

/**
 * A language's name in its own language. Not catalogue keys: an autonym reads the same
 * whatever language is in force, which is the whole point of one, and a key whose two
 * values are identical is what `strings.test.mjs` refuses.
 */
const LANGUAGE_NAMES = { en: "English", "zh-Hans": "简体中文" };

/** The variable `lib.rs` reads when a screenshot run forces a language. A variable name
 *  is not translated, and it is named here so the row can say where the language came
 *  from rather than only which one is in force. */
const FORCE_LANGUAGE = "PRUDENCE_FORCE_LANGUAGE";

/** The `app_status` columns that carry a version, in the order the engine runs them. */
const VERSIONS = [
  ["parser_version", "settings.version.parser"],
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

/** A capture level in the reader's language, or the engine's own token for a level this
 *  build has not heard of. Ugly and readable, never blank: the same fallback the
 *  Observations screen uses for a behaviour it does not know. */
function levelName(level) {
  if (!level) return t("common.dash");
  const key = level === "metadata-only" ? "settings.level.metadataOnly" : `settings.level.${level}`;
  const found = t(key);
  return found === key ? level : found;
}

/* --- the cards ---------------------------------------------------------------------- */

/** What is recorded: one row per repository and level, and where it is changed. */
function whatIsRecorded(data) {
  const { rows } = recorded(data);
  const status = data.status;

  if (!rows.length) {
    return panel({
      title: t("settings.recorded"),
      note: t("settings.recorded.note"),
      body: emptyState(t("settings.recorded.empty.title"), t("settings.recorded.empty.detail")),
      method: t("settings.recorded.method"),
    });
  }

  const table = el("table", { class: "data" }, [
    el("thead", {}, [
      el("tr", {}, [
        el("th", { text: t("scope.project") }),
        el("th", { text: t("settings.column.level") }),
        el("th", { class: "n", text: t("settings.column.sessions") }),
      ]),
    ]),
  ]);
  const body = el("tbody");
  for (const row of rows) {
    body.appendChild(
      el("tr", {}, [
        el("td", { text: row.project || t("common.dash") }),
        el("td", { text: levelName(row.level) }),
        el("td", { class: "n", text: count(row.sessions) }),
      ])
    );
  }
  table.appendChild(body);

  // The total and the number of projects are the engine's own columns rather than this
  // screen's sum of the column above it: one source of truth per fact. Adding the column
  // up is how a reader checks the two against each other, which is what the method says.
  const footer = el("div", { class: "notes" });
  if (status) {
    const projects = Number(status.projects) || 0;
    footer.appendChild(
      el("div", {
        text: t(
          "settings.recorded.total",
          sessions(Number(status.sessions) || 0),
          plural("unit.projects", projects, count(projects))
        ),
      })
    );
  }
  footer.appendChild(el("div", { text: t("settings.recorded.readOnly") }));

  return panel({
    title: t("settings.recorded"),
    note: t("settings.recorded.note"),
    body: el("div", {}, [table, footer]),
    method: t("settings.recorded.method"),
  });
}

/** The promise. No figures, and none of it conditional on the store: somebody deciding
 *  whether to enable a repository has to know what each level means before there is
 *  anything recorded at it. */
function whatIsNeverRecorded() {
  const promises = [
    "settings.never.archive",
    "settings.never.derived",
    "settings.never.metadataOnly",
    "settings.never.upload",
    "settings.never.model",
    "settings.never.employer",
  ];
  return panel({
    title: t("settings.never"),
    note: t("settings.never.note"),
    body: el(
      "ul",
      { class: "settings-promise" },
      promises.map((key) => el("li", { text: t(key) }))
    ),
  });
}

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

/** Both follow the system, and neither can be changed from here. */
function languageAndAppearance(info) {
  const inForce = lang();
  const body = el("div", { class: "fact-list" }, [
    fact(t("settings.language"), LANGUAGE_NAMES[inForce] ?? inForce, [
      info?.language
        ? t("settings.language.forced", FORCE_LANGUAGE)
        : t("settings.language.fromSystem"),
      t("settings.language.note"),
      t("settings.language.systemSettings"),
    ]),
    fact(t("settings.appearance"), t("settings.appearance.system"), [
      t("settings.appearance.note"),
    ]),
  ]);
  return panel({
    title: t("settings.languageAndAppearance"),
    note: t("settings.languageAndAppearance.note"),
    body,
  });
}

/** Which pieces are running, and where the project is. */
function about(data, info) {
  const unread = t("settings.store.unread");
  const body = el("div", { class: "fact-list" }, [
    fact(t("settings.about.app"), info?.version ?? t("common.dash")),
    fact(t("settings.about.engine"), data.status?.engine_version ?? unread),
    fact(t("settings.about.licence"), LICENCE),
    fact(t("settings.about.project"), PROJECT_URL, [], { path: true }),
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

  return panel({
    title: t("settings.about"),
    note: t("settings.about.note"),
    body,
    method: t("settings.about.method"),
  });
}

/**
 * @param {import("./screens.js").ScreenState} state
 * @returns {Element}
 */
export function settings(state) {
  const { data, info } = state;
  return el("div", { class: "screen-body" }, [
    whatIsRecorded(data),
    whatIsNeverRecorded(),
    whereItIsKept(data, info),
    // The seam with the CLI wiring. That module owns where the executable is, its own
    // version and the four actions, and owns its presentation with them, so it is placed
    // bare: between where the record is kept and the settings that are not about it.
    engineSection(state),
    languageAndAppearance(info),
    about(data, info),
  ]);
}
