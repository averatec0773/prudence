/* Start-up: ask the shell for the store, hand it to the frontend the mockups already
   speak, draw the panel, then tell the shell how tall it turned out to be.

   The vendor scripts read `window.PRUDENCE_DATA` as they are evaluated, which is the one
   thing that forces an order here: the payload has to exist before they load, so they are
   injected rather than listed in the HTML. That is the whole of the wiring change; the
   files themselves are byte-for-byte the mockups'. */

(function (global) {
  "use strict";

  var VENDOR = [
    "vendor/i18n.js",
    "vendor/brand.js",
    "vendor/derive.js",
    "vendor/charts.js",
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

  function applyAppearance() {
    var dark = global.matchMedia && global.matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
  }

  /* The material attribute is the shell's answer, not a guess. `glass` is the mockups'
     own value and turns on the frosted control layer; `app.css` then keeps the popover
     surface out of the way, because on a real window the surface material is native. */
  function applyMaterial(info) {
    var native = info && info.material && info.material.kind !== "none";
    document.documentElement.setAttribute("data-material", native ? "glass" : "standard");
  }

  function dropFocus() {
    var active = document.activeElement;
    if (active && active !== document.body && active.blur) active.blur();
  }

  function failure(message, detail) {
    var wrap = document.createElement("div");
    wrap.className = "popover";
    var body = document.createElement("div");
    body.className = "pop-body startup-error";
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
    var root = document.getElementById("root");
    root.innerHTML = "";
    root.appendChild(wrap);
  }

  /* The panel is as tall as what is in it. `.popover` is stretched to the window so the
     footer sits at the bottom when the window is the taller of the two, which also means
     its measured height is the window's; the stretch is lifted for one frame to read the
     content's own height. */
  function fitWindow(node) {
    if (!global.Bridge.attached()) return;
    var stretch = node.style.minHeight;
    node.style.minHeight = "0";
    var height = Math.ceil(node.getBoundingClientRect().height);
    node.style.minHeight = stretch;
    if (height > 0) {
      global.Bridge.fitTo(360, height)
        .then(function () {
          global.Bridge.log("fitted to 360x" + height);
        })
        .catch(function (error) {
          global.Bridge.log("fit failed: " + error);
        });
    }
    return height;
  }

  /* What the page actually resolved, held beside what the shell said it did. */
  function report(info, height) {
    var root = document.documentElement;
    var style = global.getComputedStyle(document.querySelector(".popover"));
    global.Bridge.log(
      "material=" + (info && info.material ? info.material.kind : "?") +
        " data-material=" + root.getAttribute("data-material") +
        " data-theme=" + root.getAttribute("data-theme") +
        " popover-bg=" + style.backgroundColor +
        " content-height=" + height +
        " window-height=" + global.innerHeight +
        " tray-highlight=" + (info ? info.tray_highlight : "?")
    );
    var primary = document.querySelector(".btn.primary");
    if (primary) {
      var pstyle = global.getComputedStyle(primary);
      global.Bridge.log(
        "primary-button bg=" + pstyle.backgroundColor +
          " backdrop=" + (pstyle.backdropFilter || pstyle.webkitBackdropFilter)
      );
    }
  }

  function start() {
    applyAppearance();
    if (global.matchMedia) {
      global.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyAppearance);
    }

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && global.Bridge.attached()) global.Bridge.hidePanel();
    });

    if (!global.Bridge.attached()) {
      failure("No shell", "This page is the panel of the Prudence desktop app.");
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
        return loadAll(VENDOR);
      })
      .then(function () {
        if (info && info.language) global.I18N.setLang(info.language);
        var node = global.Panel.render(document.getElementById("root"));
        /* Showing the window focuses the webview, which focuses the first control it
           finds and draws a ring on it. A popover opens with nothing selected; Tab from
           there still moves focus, which is the only way the ring should ever appear. */
        global.addEventListener("focus", dropFocus);
        dropFocus();
        var height = fitWindow(node);
        report(info, height);
      })
      .catch(function (error) {
        failure("Prudence could not read its store", String(error && error.message ? error.message : error));
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})(window);
