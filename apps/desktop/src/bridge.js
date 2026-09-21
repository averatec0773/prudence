/* The one door between the page and the shell.

   Every Tauri API call in this app is in this file. Nothing under `panel.js` or
   `design/` knows what a Tauri is. That is deliberate and it is load bearing: if the
   webview under this frontend has to change, the shell is rewritten and this file is
   rewritten with it, and the rest of the frontend moves unchanged.

   The surface is four verbs: read the store, ask the shell about itself, resize the
   panel to its content, and close or quit. */

(function (global) {
  "use strict";

  function core() {
    var tauri = global.__TAURI__;
    if (!tauri || !tauri.core) {
      throw new Error("no shell: this page is running outside its host");
    }
    return tauri.core;
  }

  /* Whether there is a shell at all. Opening index.html in a browser is a real thing to
     do while working on the layout, and it should say so rather than throw. */
  function attached() {
    return Boolean(global.__TAURI__ && global.__TAURI__.core);
  }

  var Bridge = {
    attached: attached,

    /* One payload, the shape `derive.js` already reads: a status row, three column
       blocks and three row lists, every one of them an `app_*` view's own answer. */
    readStore: function () {
      return core().invoke("store_read");
    },

    /* What the shell is and what it managed to do: the version, the store it opened,
       which material the window got and whether the status item could be highlighted. */
    info: function () {
      return core().invoke("shell_info");
    },

    /* A line on the shell's standard error. The page has no console anybody can read
       while the app is running from a menu bar. */
    log: function (line) {
      return core().invoke("page_log", { line: String(line) });
    },

    hidePanel: function () {
      return core().invoke("panel_hide");
    },

    quit: function () {
      return core().invoke("app_quit");
    },

    /* A popover is as tall as what is in it. The page measures and reports; the shell
       owns the window, which is why this is a command and not a window API call: a
       resized panel also has to be anchored under its status item again. */
    fitTo: function (width, height) {
      return core().invoke("panel_fit", { width: width, height: height });
    },
  };

  global.Bridge = Bridge;
})(window);
