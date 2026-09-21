/* Start-up, for both pages.
 *
 * There were two of these and 106 of their lines were identical. One file now, with the
 * page passed in: the panel and the window differ in what they draw and in nothing else.
 *
 * The order is: ask the shell what it is, read the store, load both string tables, then
 * draw. Modules made the old sequential script injector unnecessary; `import` is the
 * dependency order.
 */

import * as Bridge from "./bridge.js";
import { readPayload } from "./store/payload.js";
import { setLang, loadAll, t } from "./text/strings.js";
import { el } from "./design/dom.js";

/** Neither the appearance nor the language needs a relaunch: both tables are loaded and
 *  every string goes through one runtime. The Swift app needs one for the language and
 *  says so on its own settings screen. */
function applyAppearance() {
  const dark = globalThis.matchMedia?.("(prefers-color-scheme: dark)").matches;
  document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
}

/** The shell decides the material and tells the page; the page does not guess. `glass`
 *  is the mockups' own value and turns on the frosted control layer. */
function applyMaterial(info) {
  const native = info?.material && info.material.kind !== "none";
  document.documentElement.setAttribute("data-material", native ? "glass" : "standard");
}

function chooseLanguage(info) {
  if (info?.language) return info.language;
  return String(globalThis.navigator?.language ?? "en").toLowerCase().startsWith("zh")
    ? "zh-Hans"
    : "en";
}

/** Showing a window focuses its webview, which focuses the first control it finds and
 *  draws a ring on it. A surface opens with nothing selected; Tab from there still moves
 *  focus, which is the only way the ring should ever appear. */
function dropFocus() {
  const active = document.activeElement;
  if (active && active !== document.body && "blur" in active) {
    /** @type {HTMLElement} */ (active).blur();
  }
}

/**
 * What went wrong, said precisely.
 *
 * Every failure used to read "Prudence could not read its store", including a missing
 * script and a typo in a renderer. The store's own errors are sentences a user can act
 * on (`store.rs`), so they are shown as they come; everything else says what it was.
 */
function failure(container, title, detail, note) {
  container.innerHTML = "";
  const shell = el("div", { class: "startup-error" });
  shell.appendChild(el("div", { class: "headline", text: title }));
  if (detail) shell.appendChild(el("div", { class: "obs-line", text: detail }));
  // `store.rs` names both contract versions and says which side to update; this is the
  // sentence that says why the app draws nothing rather than drawing half a schema.
  if (note) shell.appendChild(el("div", { class: "coverage-chip", text: note }));
  container.appendChild(shell);
}

function message(error) {
  return error instanceof Error ? error.message : String(error);
}

/**
 * Read the store and draw. Called at start-up and again whenever the shell says an
 * ingest has landed.
 */
async function draw(page, root, info) {
  const payload = readPayload(await Bridge.readStore());
  page.render(root, { info, data: payload });
  dropFocus();
}

/**
 * @param {{ render: (root: HTMLElement, context: any) => void, name: string }} page
 */
export async function boot(page) {
  applyAppearance();
  globalThis
    .matchMedia?.("(prefers-color-scheme: dark)")
    .addEventListener("change", applyAppearance);

  const root = /** @type {HTMLElement} */ (document.getElementById("root"));

  if (!Bridge.attached()) {
    failure(root, "No shell", `This page is the ${page.name} of the Prudence desktop app.`);
    return;
  }

  let info;
  try {
    info = await Bridge.info();
    applyMaterial(info);
  } catch (error) {
    failure(root, "The shell did not answer", message(error));
    return;
  }

  try {
    await loadAll();
  } catch (error) {
    failure(root, "The interface's strings did not load", message(error));
    return;
  }

  setLang(chooseLanguage(info));

  try {
    await draw(page, root, info);
  } catch (error) {
    // `store.rs` writes sentences that name both contract versions and say which side
    // to update, so where the store is the cause its message is the whole message.
    failure(root, t("contract.title"), message(error), t("contract.note"));
    Bridge.log(`${page.name} failed to draw: ${message(error)}`);
    return;
  }

  globalThis.addEventListener("focus", dropFocus);

  /* An ingest that lands while the app is open redraws the page. A failure here is not
     a failure of the app: the store was readable a moment ago and will be again, so the
     old numbers stay on screen and the shell's log says what happened. */
  Bridge.onStoreChanged(() => {
    draw(page, root, info).catch((error) => {
      Bridge.log(`${page.name} could not follow the store: ${message(error)}`);
    });
  });

  // The shell's log is the only place an agent or a founder can see that the page got
  // all the way to the end, since a menu-bar app has no console anybody is watching.
  Bridge.log(`${page.name} drawn: material=${info?.material?.kind ?? "?"}, language=${chooseLanguage(info)}`);
}
