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

/**
 * Light or dark on the page itself.
 *
 * Neither the appearance nor the language needs a relaunch: both string tables are loaded
 * and every string goes through one runtime, and this is one attribute on the root.
 *
 * **Two halves make a dark window.** The shell pins its windows' own theme, which is what
 * changes the titlebar, the scrollbars and the native material; this is what changes
 * everything inside them. Setting only one leaves a light page in a dark frame. `system`
 * is the media query, which is also what an unset setting means.
 *
 * @param {string} [setting] `system`, `light` or `dark`
 */
function applyAppearance(setting) {
  const dark =
    setting === "dark" ||
    (setting !== "light" && globalThis.matchMedia?.("(prefers-color-scheme: dark)").matches);
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
  // Before the shell has answered, so the page is not white for one frame on a dark
  // machine. The setting arrives a moment later and is applied again.
  applyAppearance();

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

  // The media query still matters, and only while the setting is `system`: a machine that
  // switches to dark at sunset should take the page with it. A page pinned to light must
  // not move, which is why the listener reads the setting rather than the query alone.
  globalThis
    .matchMedia?.("(prefers-color-scheme: dark)")
    .addEventListener("change", () => applyAppearance(info?.settings?.appearance));
  applyAppearance(info?.settings?.appearance);

  try {
    await loadAll();
  } catch (error) {
    failure(root, "The interface's strings did not load", message(error));
    return;
  }

  setLang(chooseLanguage(info));

  /* An ingest that lands while the app is open redraws the page. A failure here is not
     a failure of the app: the store was readable a moment ago and will be again, so the
     old numbers stay on screen and the shell's log says what happened.

     **Subscribed before the first draw, not after it.** This used to sit below the early
     return, so the one case the watcher exists for was the one case it was not listening
     for: no store yet, the page shows "Run `prudence ingest` first", the founder runs it
     in a terminal, and nothing happens until they relaunch. */
  Bridge.onStoreChanged(() => {
    draw(page, root, info).catch((error) => {
      Bridge.log(`${page.name} could not follow the store: ${message(error)}`);
    });
  });

  /* A setting changed, in this window or in the other one. Both pages listen, which is
     what makes a language chosen in the window's General tab reach the panel: the panel
     has no settings screen of its own and would otherwise stay in the old language until
     it was relaunched.

     The whole of `shell_info` is asked for again rather than only the settings, because
     the drawn state is a function of `info` and holding two versions of it is how a page
     ends up half in one language. */
  Bridge.onSettingsChanged(() => {
    Bridge.info()
      .then((next) => {
        info = next;
        applyAppearance(next?.settings?.appearance);
        setLang(chooseLanguage(next));
        return draw(page, root, next);
      })
      .catch((error) => {
        Bridge.log(`${page.name} could not follow a setting: ${message(error)}`);
      });
  });

  globalThis.addEventListener("focus", dropFocus);

  try {
    await draw(page, root, info);
  } catch (error) {
    // `store.rs` writes sentences that name both contract versions and say which side
    // to update, so where the store is the cause its message is the whole message.
    failure(root, t("contract.title"), message(error), t("contract.note"));
    Bridge.log(`${page.name} failed to draw: ${message(error)}`);
    return;
  }

  // The shell's log is the only place an agent or a founder can see that the page got
  // all the way to the end, since a menu-bar app has no console anybody is watching.
  Bridge.log(`${page.name} drawn: material=${info?.material?.kind ?? "?"}, language=${chooseLanguage(info)}`);
}
