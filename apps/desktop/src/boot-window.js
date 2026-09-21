/* Start-up for the window, the counterpart of `boot.js`.

   Same order and the same reason: the design scripts read `window.PRUDENCE_DATA` as they
   are evaluated, so the payload has to exist before they load. The window does not draw a
   figure yet, but it will, and having two different start-up orders in one app is how the
   two drift. */

(function (global) {
  "use strict";

  var DESIGN = [
    // `strings.js` first and `fmt.js` second: `Fmt` reads `Str` as it is evaluated, and
    // everything after them reads both.
    "design/strings.js",
    "design/fmt.js",
    "design/i18n.js",
    "design/brand.js",
    "design/derive.js",
    "design/charts.js",
  ];


  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var node = document.createElement("script");
      node.src = src;
      node.onload = resolve;
      node.onerror = function () {
        reject(new Error("could not load " + src));
      };
      document.head.appendChild(node);
    });
  }

  function loadAll(list) {
    return list.reduce(function (chain, src) {
      return chain.then(function () {
        return loadScript(src);
      });
    }, Promise.resolve());
  }

  /* One language for both dictionaries while `i18n.js` still has two callers. The shell
     answers with the screenshot hook's choice, or null, in which case the reader's own
     system language decides between the two the app ships. */
  function setLanguage(info) {
    var wanted =
      (info && info.language) ||
      (String(global.navigator.language || "en").toLowerCase().indexOf("zh") === 0
        ? "zh-Hans"
        : "en");
    global.Str.setLang(wanted);
    global.I18N.setLang(wanted);
  }

  function applyAppearance() {
    var dark = global.matchMedia && global.matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
  }

  function applyMaterial(info) {
    var native = info && info.material && info.material.kind !== "none";
    document.documentElement.setAttribute("data-material", native ? "glass" : "standard");
  }

  function dropFocus() {
    var active = document.activeElement;
    if (active && active !== document.body && active.blur) active.blur();
  }

  function failure(message, detail) {
    var root = document.getElementById("root");
    root.innerHTML = "";
    var wrap = document.createElement("div");
    wrap.className = "window";
    var body = document.createElement("div");
    body.className = "screen startup-error";
    var head = document.createElement("div");
    head.className = "headline";
    head.textContent = message;
    body.appendChild(head);
    if (detail) {
      var note = document.createElement("div");
      note.className = "obs-line";
      note.textContent = detail;
      body.appendChild(note);
    }
    wrap.appendChild(body);
    root.appendChild(wrap);
  }

  function start() {
    applyAppearance();
    if (global.matchMedia) {
      global.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyAppearance);
    }

    if (!global.Bridge.attached()) {
      failure("No shell", "This page is the main window of the Prudence desktop app.");
      return;
    }

    var info = null;
    global.Bridge.info()
      .then(function (answer) {
        info = answer;
        applyMaterial(info);
        return global.Bridge.readStore();
      })
      .then(function (payload) {
        global.PRUDENCE_DATA = payload;
        return loadAll(DESIGN);
      })
      .then(function () {
        return global.Str.loadAll();
      })
      .then(function () {
        setLanguage(info);
        global.WindowScreen.render(document.getElementById("root"), info);
        /* Showing a window focuses its webview, which focuses the first control it finds
           and draws a ring on it. A window opens with nothing selected; Tab from there
           still moves focus, which is the only way the ring should ever appear. */
        global.addEventListener("focus", dropFocus);
        dropFocus();
        global.Bridge.log(
          "window drawn, section=" +
            ((info && info.section) || "overview") +
            " material=" +
            ((info && info.material && info.material.kind) || "?")
        );
      })
      .catch(function (error) {
        failure(
          "Prudence could not read its store",
          String(error && error.message ? error.message : error)
        );
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})(window);
