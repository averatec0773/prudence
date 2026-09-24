import { panel } from "../design/components.js";
import { el } from "../design/dom.js";
import { REPOSITORY_SCAN, SOURCE_ANSWER } from "../store/asked.js";
import { t } from "../text/strings.js";

export const SOURCES = { port: null };

function field(label, value = "", type = "text") {
  const input = /** @type {HTMLInputElement} */ (el("input", { type, value, "aria-label": label }));
  input.value = value;
  return el("label", { class: "source-field" }, [el("span", { text: label }), input]);
}

function sourceRow(row, onSet) {
  const body = el("div", { class: "source-row" });
  const heading = el("div", { class: "source-heading" });
  heading.appendChild(el("strong", { text: row.label }));
  const kind = row.kind === "codex" ? "Codex" : "Claude Code";
  if (row.label !== kind) heading.appendChild(el("span", { class: "source-kind", text: kind }));
  body.appendChild(heading);
  body.appendChild(el("div", { class: "source-home", text: row.home, title: row.home }));
  if (!row.exists) body.appendChild(el("p", { class: "source-note", text: t("sources.missing") }));
  body.appendChild(el("p", { class: "source-note", text: t(row.enabled ? "sources.recording" : "sources.paused") }));

  const actions = el("div", { class: "source-actions" });
  const toggle = el("button", { class: "btn", type: "button", text: t(row.enabled ? "sources.pause" : "sources.resume") });
  toggle.addEventListener("click", () => onSet(row.id, !row.enabled));
  actions.appendChild(toggle);
  const edit = el("button", { class: "btn plain", type: "button", text: t("sources.edit") });
  edit.setAttribute("aria-expanded", "false");
  actions.appendChild(edit);
  body.appendChild(actions);

  const editor = el("div", { class: "source-edit" });
  editor.hidden = true;
  const name = field(t("sources.name"), row.label);
  const home = field(t("sources.home"), row.home);
  const save = el("button", { class: "btn", type: "button", text: t("sources.save") });
  save.addEventListener("click", () => {
    const nextName = /** @type {HTMLInputElement} */ (name.children[1]).value;
    const nextHome = /** @type {HTMLInputElement} */ (home.children[1]).value;
    if (!nextName.trim() || !nextHome.trim()) return;
    onSet(row.id, row.enabled, nextName, nextHome);
  });
  editor.appendChild(name);
  editor.appendChild(home);
  editor.appendChild(save);
  body.appendChild(editor);
  edit.addEventListener("click", () => {
    editor.hidden = !editor.hidden;
    edit.setAttribute("aria-expanded", String(!editor.hidden));
  });
  return body;
}

export function sources(state) {
  const body = el("div", { class: "source-list" });
  const card = panel({ title: t("sources.title"), note: t("sources.note"), body });
  if (!SOURCES.port) {
    body.appendChild(el("p", { class: "source-note", text: t("settings.noShell") }));
    return card;
  }

  let busy = false;
  const message = el("p", { class: "source-message" });
  const list = el("div", { class: "source-rows" });
  body.appendChild(message);
  body.appendChild(list);

  const draw = (rows) => {
    list.innerHTML = "";
    if (!Array.isArray(rows) || !rows.length) {
      list.appendChild(el("p", { class: "source-note", text: t("sources.empty") }));
    } else {
      for (const row of rows) list.appendChild(sourceRow(row, set));
    }
  };

  const apply = (answer) => {
    SOURCE_ANSWER.keep(state.data, answer.sources);
    REPOSITORY_SCAN.keep(state.data, answer.repositories);
    busy = false;
    message.textContent = "";
    draw(answer.sources);
  };

  const fail = (error) => {
    busy = false;
    const detail = String(error?.message ?? error);
    message.textContent = detail === "notFound"
      ? t("sources.engineMissing")
      : `${t("sources.error")} ${detail}`;
  };

  function set(id, enabled, name = null, home = null) {
    if (busy) return;
    busy = true;
    message.textContent = t("sources.saving");
    SOURCES.port.set(id, enabled, name, home).then(apply).catch(fail);
  }

  const addToggle = el("button", { class: "btn source-add-toggle", type: "button", text: t("sources.add") });
  addToggle.setAttribute("aria-expanded", "false");
  const form = el("div", { class: "source-add-form" });
  form.hidden = true;
  const kindField = el("label", { class: "source-field" }, [el("span", { text: t("sources.kind") })]);
  const kind = /** @type {HTMLSelectElement} */ (el("select", { "aria-label": t("sources.kind") }, [
    el("option", { value: "codex", text: "Codex" }),
    el("option", { value: "claude_code", text: "Claude Code" }),
  ]));
  kind.value = "codex";
  kindField.appendChild(kind);
  const name = field(t("sources.name"));
  const home = field(t("sources.home"));
  const add = el("button", { class: "btn", type: "button", text: t("sources.add.confirm") });
  add.addEventListener("click", () => {
    if (busy) return;
    const nextName = /** @type {HTMLInputElement} */ (name.children[1]).value.trim();
    const nextHome = /** @type {HTMLInputElement} */ (home.children[1]).value.trim();
    if (!nextName || !nextHome) {
      message.textContent = t("sources.required");
      return;
    }
    busy = true;
    message.textContent = t("sources.saving");
    SOURCES.port.add(kind.value, nextName, nextHome).then((answer) => {
      apply(answer);
      form.hidden = true;
      addToggle.setAttribute("aria-expanded", "false");
    }).catch(fail);
  });
  form.appendChild(kindField);
  form.appendChild(name);
  form.appendChild(home);
  form.appendChild(add);
  addToggle.addEventListener("click", () => {
    form.hidden = !form.hidden;
    addToggle.setAttribute("aria-expanded", String(!form.hidden));
  });
  body.appendChild(addToggle);
  body.appendChild(form);

  message.textContent = t("menu.engineChecking");
  SOURCE_ANSWER.ask(state.data, () => SOURCES.port.read()).then((rows) => {
    message.textContent = "";
    draw(rows);
  }).catch(fail);
  return card;
}
