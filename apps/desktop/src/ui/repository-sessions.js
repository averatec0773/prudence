import { el } from "../design/dom.js";
import { isoDay, tokenPhrase } from "../text/fmt.js";
import { t } from "../text/strings.js";

function array(value) {
  if (Array.isArray(value)) return value.map(String);
  if (typeof value !== "string") return [];
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch {
    return [];
  }
}

function sourcePairs(row) {
  const ids = array(row.source_ids);
  const labels = array(row.source_labels);
  if (ids.length) return ids.map((id, index) => [id, labels[index] || id]);
  const kind = String(row.source ?? "");
  return kind ? [[kind, kind === "codex" ? "Codex" : kind === "claude_code" ? "Claude Code" : kind]] : [];
}

export function repositorySessions(sessions, project) {
  const rows = (Array.isArray(sessions) ? sessions : [])
    .filter((row) => !project || row.project === project)
    .slice()
    .sort((a, b) => String(b.started_at ?? "").localeCompare(String(a.started_at ?? "")));
  const sources = new Map();
  const models = new Set();
  for (const row of rows) {
    for (const [id, label] of sourcePairs(row)) sources.set(id, label);
    for (const model of array(row.models)) models.add(model);
  }

  const details = el("details", { class: "card repository-sessions" });
  details.appendChild(el("summary", { text: t("repositories.sessions.title") }));
  details.appendChild(el("p", { class: "panel-note", text: t("repositories.sessions.note") }));
  const controls = el("div", { class: "repository-session-filters" });
  const source = /** @type {HTMLSelectElement} */ (el("select", { "aria-label": t("repositories.sessions.source") }, [
    el("option", { value: "", text: t("repositories.sessions.allSources") }),
    ...[...sources].map(([id, label]) => el("option", { value: id, text: label })),
  ]));
  const model = /** @type {HTMLSelectElement} */ (el("select", { "aria-label": t("repositories.sessions.model") }, [
    el("option", { value: "", text: t("repositories.sessions.allModels") }),
    ...[...models].sort().map((name) => el("option", { value: name, text: name })),
  ]));
  controls.appendChild(source);
  controls.appendChild(model);
  details.appendChild(controls);
  const list = el("div", { class: "repository-session-list" });
  details.appendChild(list);

  const draw = () => {
    list.innerHTML = "";
    const shown = rows.filter((row) =>
      (!source.value || sourcePairs(row).some(([id]) => id === source.value)) &&
      (!model.value || array(row.models).includes(model.value))
    ).slice(0, 20);
    if (!shown.length) {
      list.appendChild(el("p", { class: "panel-note", text: t("repositories.sessions.empty") }));
    }
    for (const row of shown) {
      const sourceText = sourcePairs(row).map(([, label]) => label).join(", ");
      const modelText = array(row.models).join(", ");
      list.appendChild(el("div", { class: "repository-session" }, [
        el("div", { class: "repository-session-main" }, [
          el("span", { text: String(row.project ?? t("common.dash")) }),
          el("span", { text: isoDay(row.started_at) }),
          el("span", { text: row.total_tokens == null ? t("common.dash") : tokenPhrase(Number(row.total_tokens)) }),
        ]),
        el("div", { class: "repository-session-meta", text: [sourceText, modelText].filter(Boolean).join(" · ") }),
      ]));
    }
  };
  source.addEventListener("change", draw);
  model.addEventListener("change", draw);
  draw();
  return details;
}
